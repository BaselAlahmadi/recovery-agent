"""Saving orders, and replaying orders that were lost."""
import json
import queue
import random
import threading
import time

from shop import config, db, metrics, payment, worker
from shop.config import LOG_DIR
from shop.logger import log

REPLAY_ATTEMPTS = 8          # per order: the provider and the database may both fail a few times
REPLAY_BUDGET_S = 40         # stay under the caller's 60 s timeout; call again for the rest (safe to repeat)
_replay_lock = threading.Lock()


def save_order(o, replayed=False):
    """Insert the order, take stock, queue it for fulfillment.
    Returns False (and does nothing) if this order_id is already saved, so it never duplicates."""
    # FAULT F6: the write is silently lost. No error, no log line, the caller carries on as if it worked.
    if random.random() < config.get("f6_save_fail_rate"):
        return False
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


REQUEUE_GRACE_S = 5          # orders younger than this may simply be between "saved" and "queued"
_requeue_lock = threading.Lock()


def requeue_unprocessed():
    """Re-queue orders that were saved but never processed: dropped from a full queue, or
    sitting in the dead-letter list. Skips anything already shipped, queued, being worked on
    or parked, so it never creates duplicates and a second call finds nothing."""
    if not _requeue_lock.acquire(blocking=False):
        return {"error": "a requeue is already running"}
    try:
        worker.apply_capacity()     # the queue limit may just have been raised by a rollback
        from_dead_letter = 0
        while worker.dead_letter:
            try:
                worker.order_queue.put_nowait(worker.dead_letter[0])
            except queue.Full:
                break
            worker.dead_letter.pop(0)
            from_dead_letter += 1

        cutoff = time.time() - REQUEUE_GRACE_S

        def candidates():
            with db.connect(db.SOURCE_DB) as c:
                rows = c.execute("SELECT order_id, sku, qty, amount FROM orders WHERE created < ? AND order_id "
                                 "NOT IN (SELECT order_id FROM fulfillment WHERE step = 'ship')", (cutoff,)).fetchall()
            present = worker.present_ids()
            return {r[0]: dict(zip(("order_id", "sku", "qty", "amount"), r)) for r in rows if r[0] not in present}

        first = candidates()
        time.sleep(0.3)             # an order being handed from the queue to the worker is briefly in neither
        second = candidates()
        lost = [o for oid, o in second.items() if oid in first]
        requeued = 0
        for o in lost:
            try:
                worker.order_queue.put_nowait(o)
            except queue.Full:
                break
            requeued += 1
        log("shop", "requeue_done", from_dead_letter=from_dead_letter, lost_found=len(lost), requeued=requeued)
        return {"requeued_from_dead_letter": from_dead_letter, "lost_found": len(lost), "requeued_lost": requeued}
    finally:
        _requeue_lock.release()


def _is_saved(order_id):
    with db.connect(db.SOURCE_DB) as c:
        return c.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,)).fetchone() is not None


def replay_lost_orders():
    """Re-create orders the customer was told succeeded ("ok") but that were never saved.
    - Orders answered "payment_failed" are NOT replayed: the customer was told it failed.
    - Requests with no response yet (still in flight) are skipped.
    - Already-saved orders are skipped, so running this twice never duplicates anything.
    - Each order is retried (charge, then save, then check the database) until it exists or
      REPLAY_ATTEMPTS run out. Orders that still cannot be created are reported as
      "unrecoverable" instead of being silently dropped."""
    if not _replay_lock.acquire(blocking=False):
        return {"error": "a replay is already running"}
    try:
        time.sleep(1.0)     # let requests that are mid-flight (max ~0.6s) get their answer logged first
        reqs, resps = _read_request_log()
        with db.connect(db.SOURCE_DB) as c:
            saved = {row[0] for row in c.execute("SELECT order_id FROM orders")}
        lost = [o for oid, o in reqs.items() if resps.get(oid) == "ok" and oid not in saved]
        replayed = unrecoverable = 0
        deadline = time.time() + REPLAY_BUDGET_S
        for i, o in enumerate(lost):
            if time.time() > deadline:
                break
            done = False
            for _ in range(REPLAY_ATTEMPTS):
                if payment.charge(o["order_id"], o["amount"]) != "ok":   # looked up by order_id, so safe to repeat
                    continue
                save_order(o, replayed=True)
                if _is_saved(o["order_id"]):
                    done = True
                    break
            if done:
                replayed += 1
            else:
                unrecoverable += 1
                log("shop", "replay_unrecoverable", order_id=o["order_id"])
        not_attempted = len(lost) - replayed - unrecoverable
        log("shop", "replay_done", found_lost=len(lost), replayed=replayed, unrecoverable=unrecoverable,
            not_attempted=not_attempted)
        result = {"found_lost": len(lost), "replayed": replayed, "unrecoverable": unrecoverable,
                  "not_attempted": not_attempted}
        if unrecoverable or not_attempted:
            result["note"] = ("PARTIAL: some orders are still missing. not_attempted can be retried by calling again; "
                              "unrecoverable ones failed every attempt, so the cause is probably still active.")
        return result
    finally:
        _replay_lock.release()
