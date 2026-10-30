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
_in_flight = [0]              # checkouts being handled right now (received, not yet answered)


def inc(name, n=1):
    with _lock:
        _counters[name] += n


def begin_checkout():
    """Count a request and mark it in flight in one step, so the two never disagree."""
    with _lock:
        _counters["checkout_requests"] += 1
        _in_flight[0] += 1


def end_checkout():
    with _lock:
        _in_flight[0] -= 1


WINDOW_S = 30
_outcomes = deque()   # (time, customer_was_told_ok) for recent checkouts


def record_outcome(ok):
    """Remember what the customer was told, to compute recent failure rates."""
    with _lock:
        _outcomes.append((time.time(), ok))


def snapshot():
    with _lock:
        now = time.time()
        while _outcomes and _outcomes[0][0] < now - WINDOW_S:
            _outcomes.popleft()
        last5 = [ok for t, ok in _outcomes if t >= now - 5]
        recent = {"checkout_last_30s": len(_outcomes), "failed_last_30s": sum(1 for _, ok in _outcomes if not ok),
                  "checkout_last_5s": len(last5), "failed_last_5s": last5.count(False),
                  "in_flight_requests": _in_flight[0]}
        return {**_counters, **recent}
