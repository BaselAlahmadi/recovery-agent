"""The agent's vital signs: business invariants checked in plain Python (no LLM).

Each check says "is the shop actually doing its job?", not "is there an error in the logs?".
"""
import time

SLA_S = 10             # an order in progress (or a silent worker) longer than this is a problem
MIN_CHECKOUTS = 10     # need at least this many checkouts in the last 30 s to judge the failure rate
MIN_RECENT = 5         # ... and at least this many in the last 5 s
MAX_FAIL_RATE = 0.25   # more than this share of checkouts failing = outage


def check(m):
    """m = /metrics dict."""
    out = []

    def add(name, ok, detail):
        out.append({"name": name, "ok": ok, "detail": detail})

    # 1. Every request must be answered "payment failed", saved as an order, or still be in flight.
    #    No tolerance: requests being handled right now are counted exactly (in_flight_requests),
    #    so any positive gap is a request that was answered "ok" but never saved.
    gap = m["checkout_requests"] - m["payments_failed"] - m["orders_saved"] - m["in_flight_requests"]
    add("requests_vs_saved", gap <= 0,
        f"requests={m['checkout_requests']} in_flight={m['in_flight_requests']} payments_failed={m['payments_failed']} "
        f"saved={m['orders_saved']} missing={max(gap, 0)}")

    # 2. Every enqueued order must be somewhere: done, waiting, being worked on, parked or dead-lettered.
    accounted = m["processed"] + m["pending"] + m["in_progress"] + m["parked"] + m["dead_letter"]
    gap = m["enqueued"] - accounted
    add("queue_accounting", gap == 0,
        f"enqueued={m['enqueued']} processed={m['processed']} pending={m['pending']} "
        f"in_progress={m['in_progress']} parked={m['parked']} dead_letter={m['dead_letter']} missing={gap}")

    # 3. Nothing may be in progress longer than the SLA, and the worker must show signs of life.
    add("oldest_in_progress_age", m["oldest_in_progress_age_s"] <= SLA_S,
        f"{m['oldest_in_progress_age_s']}s (SLA {SLA_S}s)")
    add("worker_heartbeat", m["worker_heartbeat_age_s"] <= SLA_S,
        f"last sign of life {m['worker_heartbeat_age_s']}s ago (SLA {SLA_S}s)")

    # 4. Orders taken from a stuck worker, or overflowed into the dead-letter list, must be requeued.
    add("no_parked_orders", m["parked"] == 0, f"parked={m['parked']}")
    add("no_dead_letters", m["dead_letter"] == 0, f"dead_letter={m['dead_letter']}")

    # 5. The replica must hold exactly what the last sync run copied.
    s = m["sync"]
    ok = s["runs"] == 0 or s["copied_checksum"] == s["replica_checksum"]
    add("replica_checksum", ok, f"copied={s['copied_checksum']} replica={s['replica_checksum']}")

    # 6. Customers must be able to check out. Honest failures keep the counters above consistent,
    #    so an outage (e.g. payment provider down) is only visible as a high recent failure rate.
    #    It must be high over the last 30 s (not a blip) AND over the last 5 s (still happening), so
    #    that a correct fix clears the alarm within ~5 s instead of waiting for old failures to age out.
    n30, k30, n5, k5 = m["checkout_last_30s"], m["failed_last_30s"], m["checkout_last_5s"], m["failed_last_5s"]
    persistent = n30 >= MIN_CHECKOUTS and k30 / n30 > MAX_FAIL_RATE
    current = n5 >= MIN_RECENT and k5 / n5 > MAX_FAIL_RATE
    add("payment_success", not (persistent and current),
        f"{k30} of {n30} checkouts failed in the last 30s, {k5} of {n5} in the last 5s (max {int(MAX_FAIL_RATE * 100)}%)")
    return out


def run_checks(fetch_metrics):
    """Fetch metrics and check them. If a counter invariant fails, re-sample once after
    0.5s so a momentary race between two counters is not reported as a failure."""
    results = check(fetch_metrics())
    if any(not r["ok"] for r in results if r["name"] in ("queue_accounting", "requests_vs_saved", "replica_checksum")):
        time.sleep(0.5)
        results = check(fetch_metrics())
    return results


def summarize(results):
    """Compact text for the LLM and the report."""
    lines = [("ok   " if r["ok"] else "FAIL ") + f"{r['name']}: {r['detail']}" for r in results]
    status = "ALL INVARIANTS OK" if all(r["ok"] for r in results) else "INVARIANTS FAILING"
    return status + "\n" + "\n".join(lines)


def all_ok(results):
    return all(r["ok"] for r in results)
