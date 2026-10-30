"""Order queue + worker thread running the fulfillment workflow (reserve -> pack -> ship)."""
import queue
import threading
import time

from shop import config, db, metrics
from shop.logger import log

STEPS = ["reserve", "pack", "ship"]

order_queue = queue.Queue(maxsize=config.get("queue_capacity"))
in_progress = {}            # order_id -> time the worker started it
heartbeat = {"ts": time.time()}  # worker updates this every loop; stale = worker is stuck/dead


def enqueue(order):
    """Put an order on the queue. If full, reject loudly (silent drops come later as a fault)."""
    try:
        order_queue.put_nowait(order)
    except queue.Full:
        log("queue", "rejected_full", order_id=order["order_id"])
        return False
    metrics.inc("enqueued")
    log("queue", "enqueued", order_id=order["order_id"])
    return True


def _fulfill(order):
    """Run each workflow step and record it in the fulfillment table."""
    for step in STEPS:
        time.sleep(config.get("step_delay"))
        with db.connect(db.SOURCE_DB) as c:
            c.execute("INSERT INTO fulfillment VALUES (?, ?, ?)", (order["order_id"], step, time.time()))
        heartbeat["ts"] = time.time()


def _run():
    while True:
        heartbeat["ts"] = time.time()
        try:
            order = order_queue.get(timeout=1)
        except queue.Empty:
            continue
        in_progress[order["order_id"]] = time.time()
        log("worker", "started", order_id=order["order_id"])
        _fulfill(order)
        del in_progress[order["order_id"]]
        metrics.inc("processed")
        log("worker", "finished", order_id=order["order_id"])


def start():
    threading.Thread(target=_run, daemon=True, name="worker").start()


def stats():
    now = time.time()
    oldest = max((now - t for t in in_progress.values()), default=0.0)
    return {
        "pending": order_queue.qsize(),
        "in_progress": len(in_progress),
        "oldest_in_progress_age_s": round(oldest, 2),
        "worker_heartbeat_age_s": round(now - heartbeat["ts"], 2),
    }
