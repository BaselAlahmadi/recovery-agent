"""Saving orders, and replaying orders that were lost."""
import json
import threading
import time

from shop import db, metrics, payment, worker
from shop.config import LOG_DIR
from shop.logger import log

REPLAY_ATTEMPTS = 5          # the provider is flaky, so a replayed charge may need a few tries
_replay_lock = threading.Lock()


def save_order(o, replayed=False):
    """Insert the order, take stock, queue it for fulfillment.
    Returns False (and does nothing) if this order_id is already saved, so it never duplicates."""
    with db.connect(db.SOURCE_DB) as c:
        cur = c.execute("INSERT OR IGNORE INTO orders VALUES (?, ?, ?, ?, ?)",
                        (o["order_id"], o["sku"], o["qty"], o["amount"], time.time()))
        if cur.rowcount == 0:
            return False
        c.execute("UPDATE inventory SET stock = MAX(stock - ?, 0) WHERE sku = ?", (o["qty"], o["sku"]))
    metrics.inc("orders_saved")
    log("checkout", "order_saved", order_id=o["order_id"], replayed=replayed)
    worker.enqueue(o)
    return True


def _read_request_log():
    """Returns (requests, responses): order_id -> order fields, and order_id -> status we answered."""
    reqs, resps = {}, {}
    path = LOG_DIR / "requests.jsonl"
    if not path.exists():
        return reqs, resps
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:      # a line still being written
            continue
        if r["event"] == "checkout":
            reqs.setdefault(r["order_id"], {k: r[k] for k in ("order_id", "sku", "qty", "amount")})
        elif r["event"] == "response":
            resps[r["order_id"]] = r["status"]
    return reqs, resps


def replay_lost_orders():
    """Re-create orders the customer was told succeeded ("ok") but that were never saved.
    - Orders answered "payment_failed" are NOT replayed: the customer was told it failed.
    - Requests with no response yet (still in flight) are skipped.
    - Already-saved orders are skipped, so running this twice never duplicates anything."""
    if not _replay_lock.acquire(blocking=False):
        return {"error": "a replay is already running"}
    try:
        reqs, resps = _read_request_log()
        with db.connect(db.SOURCE_DB) as c:
            saved = {row[0] for row in c.execute("SELECT order_id FROM orders")}
        lost = [o for oid, o in reqs.items() if resps.get(oid) == "ok" and oid not in saved]
        replayed = failed = 0
        for o in lost:
            # the charge is looked up by order_id (idempotent), retried because the provider is flaky
            if any(payment.charge(o["order_id"], o["amount"]) == "ok" for _ in range(REPLAY_ATTEMPTS)):
                replayed += save_order(o, replayed=True)
            else:
                failed += 1
        log("shop", "replay_done", found_lost=len(lost), replayed=replayed, still_failed=failed)
        return {"found_lost": len(lost), "replayed": replayed, "still_failed": failed}
    finally:
        _replay_lock.release()
