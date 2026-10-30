"""Inventory sync job: copies source inventory to the replica every few seconds."""
import threading
import time

from shop import config, db
from shop.logger import log

state = {"runs": 0, "last_run_ts": 0.0, "rows_synced": 0}


def sync_once():
    with db.connect(db.SOURCE_DB) as src:
        rows = src.execute("SELECT sku, stock FROM inventory").fetchall()
    with db.connect(db.REPLICA_DB) as rep:
        rep.executemany("INSERT OR REPLACE INTO inventory VALUES (?, ?)", rows)
    state["runs"] += 1
    state["last_run_ts"] = time.time()
    state["rows_synced"] = len(rows)
    log("sync", "run_done", rows=len(rows))


def _run():
    while True:
        time.sleep(config.get("sync_interval"))
        sync_once()


def start():
    threading.Thread(target=_run, daemon=True, name="sync").start()


def stats():
    """Checksums are computed live so a mismatch is visible. Small mismatches right after
    an order are normal (replica lags until the next run); a lasting mismatch is a problem."""
    age = time.time() - state["last_run_ts"] if state["runs"] else None
    return {
        "runs": state["runs"],
        "last_run_age_s": None if age is None else round(age, 2),
        "rows_synced": state["rows_synced"],
        "source_checksum": db.inventory_checksum(db.SOURCE_DB),
        "replica_checksum": db.inventory_checksum(db.REPLICA_DB),
    }
