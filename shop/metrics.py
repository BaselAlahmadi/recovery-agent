"""Simple thread-safe counters shown at /metrics."""
import threading
import time
from collections import deque

_lock = threading.Lock()
_counters = {
    "checkout_requests": 0,   # every POST /checkout received
    "orders_saved": 0,        # orders actually written to the DB
    "payments_ok": 0,
    "payments_failed": 0,     # customers told "payment_failed"
    "payment_timeouts": 0,    # provider calls that timed out (retries counted too)
    "enqueued": 0,            # orders put on the fulfillment queue
    "processed": 0,           # orders the worker finished
}


def inc(name, n=1):
    with _lock:
        _counters[name] += n


WINDOW_S = 30
_outcomes = deque()   # (time, customer_was_told_ok) for recent checkouts


def record_outcome(ok):
    """Remember what the customer was told, to compute a recent failure rate."""
    with _lock:
        _outcomes.append((time.time(), ok))


def snapshot():
    with _lock:
        cutoff = time.time() - WINDOW_S
        while _outcomes and _outcomes[0][0] < cutoff:
            _outcomes.popleft()
        recent = {"checkout_last_30s": len(_outcomes), "failed_last_30s": sum(1 for _, ok in _outcomes if not ok)}
        return {**_counters, **recent}
