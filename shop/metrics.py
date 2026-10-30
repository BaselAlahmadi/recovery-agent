"""Simple thread-safe counters shown at /metrics."""
import threading

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


def snapshot():
    with _lock:
        return dict(_counters)
