"""Inventory sync job: copies source inventory to the replica every few seconds."""
import random
import threading
import time

from shop import config, db, settings
from shop.logger import log

state = {"runs": 0, "last_run_ts": 0.0, "rows_synced": 0, "copied_checksum": None}
_lock = threading.Lock()   # the scheduled run and a manual resync never overlap


def sync_once():
    with _lock:
        with db.connect(db.SOURCE_DB) as src:
            rows = src.execute("SELECT sku, stock FROM inventory").fetchall()
        to_write = rows
        # FAULT F3: with the bad "fast" sync mode, a few replica rows are silently written wrong
        # on every run. The log line below looks exactly the same as a healthy run.
        rate = config.get("f3_corrupt_rate")
        if settings.get("sync_mode") == "fast" and rate > 0:
            bad = set(random.sample(range(len(rows)), max(1, round(rate * len(rows)))))
            to_write = [(sku, stock + random.randint(1, 9)) if i in bad else (sku, stock)
                        for i, (sku, stock) in enumerate(rows)]
        with db.connect(db.REPLICA_DB) as rep:
            rep.executemany("INSERT OR REPLACE INTO inventory VALUES (?, ?)", to_write)
        state["runs"] += 1
        state["last_run_ts"] = time.time()
        state["rows_synced"] = len(rows)
        state["copied_checksum"] = db.rows_checksum(rows)  # what the replica SHOULD now contain
        log("sync", "run_done", rows=len(rows))


def resync():
    """Admin action: run a sync right now, using the shop's current sync settings."""
    sync_once()
    return {"resynced_rows": state["rows_synced"], "sync_mode": settings.get("sync_mode")}


def _run():
    while True:
        time.sleep(config.get("sync_interval"))
        sync_once()


def start():
    threading.Thread(target=_run, daemon=True, name="sync").start()


def stats():
    """copied_checksum = hash of the rows the last run copied from the source.
    replica_checksum = hash of what the replica really holds now.
    They must match. (Comparing against the LIVE source would false-alarm: new orders
    change the source constantly and the replica only catches up every few seconds.)"""
    age = time.time() - state["last_run_ts"] if state["runs"] else None
    return {
        "runs": state["runs"],
        "last_run_age_s": None if age is None else round(age, 2),
        "rows_synced": state["rows_synced"],
        "copied_checksum": state["copied_checksum"],
        "replica_checksum": db.inventory_checksum(db.REPLICA_DB),
    }
