"""The agent's vital signs: business invariants checked in plain Python (no LLM).

Each check says "is the shop actually doing its job?", not "is there an error in the logs?".
"""
import time

SLA_S = 10             # an order in progress (or a silent worker) longer than this is a problem
REQUEST_TOLERANCE = 3  # requests currently being handled (in flight) look like a small gap


def check(m):
    """m = /metrics dict."""
    out = []

    def add(name, ok, detail):
        out.append({"name": name, "ok": ok, "detail": detail})

    # 1. Every request that was paid for should end up as a saved order.
    gap = m["checkout_requests"] - m["payments_failed"] - m["orders_saved"]
    add("requests_vs_saved", gap <= REQUEST_TOLERANCE,
        f"requests={m['checkout_requests']} payments_failed={m['payments_failed']} saved={m['orders_saved']} gap={gap}")

    # 2. Every enqueued order must be somewhere: done, waiting, being worked on, or parked.
    accounted = m["processed"] + m["pending"] + m["in_progress"] + m["parked"]
    gap = m["enqueued"] - accounted
    add("queue_accounting", gap == 0,
        f"enqueued={m['enqueued']} processed={m['processed']} pending={m['pending']} "
        f"in_progress={m['in_progress']} parked={m['parked']} missing={gap}")

    # 3. Nothing may be in progress longer than the SLA, and the worker must show signs of life.
    add("oldest_in_progress_age", m["oldest_in_progress_age_s"] <= SLA_S,
        f"{m['oldest_in_progress_age_s']}s (SLA {SLA_S}s)")
    add("worker_heartbeat", m["worker_heartbeat_age_s"] <= SLA_S,
        f"last sign of life {m['worker_heartbeat_age_s']}s ago (SLA {SLA_S}s)")

    # 4. Orders taken from a stuck worker must be put back on the queue.
    add("no_parked_orders", m["parked"] == 0, f"parked={m['parked']}")

    # 5. The replica must hold exactly what the last sync run copied.
    s = m["sync"]
    ok = s["runs"] == 0 or s["copied_checksum"] == s["replica_checksum"]
    add("replica_checksum", ok, f"copied={s['copied_checksum']} replica={s['replica_checksum']}")
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
