"""Order queue + worker thread running the fulfillment workflow (reserve -> pack -> ship)."""
import queue
import random
import threading
import time

from shop import config, db, metrics, settings
from shop.logger import log

STEPS = ["reserve", "pack", "ship"]

order_queue = queue.Queue()  # size limit is applied live from the shop settings (apply_capacity)
in_progress = {}            # order_id -> {"started": time, "order": order} being worked on right now
parked = []                 # unfinished orders taken from a stuck worker, waiting to be requeued
dead_letter = []            # orders that did not fit in a full queue (healthy overflow policy)
heartbeat = {"ts": time.time()}  # worker updates this every loop; stale = worker is stuck/dead
state = {"gen": 0, "release": None}  # which worker thread is current (restart bumps "gen")


def apply_capacity():
    """Queue.maxsize is checked on every put, so changing it takes effect immediately."""
    order_queue.maxsize = settings.get("queue_capacity")


def enqueue(order):
    """Put an order on the queue. When it is full, the overflow policy decides what happens."""
    apply_capacity()
    try:
        order_queue.put_nowait(order)
    except queue.Full:
        metrics.inc("enqueued")
        if settings.get("queue_overflow_policy") == "drop":
            # BUG (bad config for fault F2): the order is thrown away, but it is still counted
            # as enqueued and nothing is logged.
            return True
        dead_letter.append(order)
        log("queue", "dead_lettered", order_id=order["order_id"])
        return True
    metrics.inc("enqueued")
    log("queue", "enqueued", order_id=order["order_id"])
    return True


def present_ids():
    """Every order id the shop currently 'knows about' as waiting or being worked on."""
    with order_queue.mutex:
        ids = {o["order_id"] for o in order_queue.queue}
    ids |= set(list(in_progress))
    ids |= {o["order_id"] for o in list(parked)}
    ids |= {o["order_id"] for o in list(dead_letter)}
    return ids


def _fulfill(order, started_at, release):
    """Run each workflow step. Returns False if the worker got stuck and was later retired."""
    for step in STEPS:
        time.sleep(config.get("step_delay") + config.get("f2_extra_delay"))
        # FAULT F4: a worker that was already running when the fault was switched on has a
        # "stale connection": its "pack" step sometimes never returns. No error, no log line.
        # A worker started AFTER that (e.g. by a restart) is healthy.
        poisoned = config.modified_at() > started_at
        if step == "pack" and poisoned and random.random() < config.get("f4_hang_rate"):
            release.wait()          # blocks until restart() sets the event
            return False
        with db.connect(db.SOURCE_DB) as c:
            c.execute("INSERT INTO fulfillment VALUES (?, ?, ?)", (order["order_id"], step, time.time()))
        heartbeat["ts"] = time.time()
    return True


def _run(gen, release, started_at):
    while gen == state["gen"]:
        heartbeat["ts"] = time.time()
        try:
            order = order_queue.get(timeout=1)
        except queue.Empty:
            continue
        if gen != state["gen"]:     # we were retired while waiting: hand the order back
            order_queue.put(order)
            return
        oid = order["order_id"]
        in_progress[oid] = {"started": time.time(), "order": order}
        log("worker", "started", order_id=oid)
        finished = _fulfill(order, started_at, release)
        if not finished or gen != state["gen"]:
            return                  # retired: restart() already parked this order
        in_progress.pop(oid, None)
        metrics.inc("processed")
        log("worker", "finished", order_id=oid)


def start():
    state["release"] = threading.Event()
    threading.Thread(target=_run, args=(state["gen"], state["release"], time.time()),
                     daemon=True, name=f"worker-{state['gen']}").start()


def restart():
    """Retire the current worker, park its unfinished orders, start a fresh worker."""
    state["gen"] += 1                       # old thread will exit as soon as it wakes up
    state["release"].set()                  # wake it if it is stuck
    moved = [v["order"] for v in in_progress.values()]
    parked.extend(moved)
    in_progress.clear()
    start()
    log("worker", "restarted", parked=len(moved))
    return {"restarted": True, "parked_orders": len(moved)}


def requeue_parked():
    """Move parked orders back onto the queue (they were already counted as enqueued)."""
    apply_capacity()
    n = 0
    while parked:
        try:
            order_queue.put_nowait(parked[0])
        except queue.Full:
            break
        parked.pop(0)
        n += 1
    log("worker", "requeued", count=n)
    return {"requeued": n, "still_parked": len(parked)}


def stats():
    now = time.time()
    oldest = max((now - v["started"] for v in list(in_progress.values())), default=0.0)
    return {
        "pending": order_queue.qsize(),
        "in_progress": len(in_progress),
        "parked": len(parked),
        "dead_letter": len(dead_letter),
        "oldest_in_progress_age_s": round(oldest, 2),
        "worker_heartbeat_age_s": round(now - heartbeat["ts"], 2),
    }
