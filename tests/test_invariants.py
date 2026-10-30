"""Unit tests for the invariant checker. Pure Python: no shop, no LLM, runs in about a second."""
import copy

from agent import invariants


def healthy():
    """Metrics from a shop that is working fine."""
    return {
        "checkout_requests": 100, "payments_failed": 0, "orders_saved": 98, "in_flight_requests": 2,
        "enqueued": 98, "processed": 88, "pending": 9, "in_progress": 1, "parked": 0, "dead_letter": 0,
        "oldest_in_progress_age_s": 0.1, "worker_heartbeat_age_s": 0.05,
        "checkout_last_30s": 40, "failed_last_30s": 1, "checkout_last_5s": 8, "failed_last_5s": 0,
        "sync": {"runs": 3, "copied_checksum": "abc", "replica_checksum": "abc"},
    }


def failing(m):
    return {r["name"] for r in invariants.check(m) if not r["ok"]}


def test_healthy_shop_passes_everything():
    results = invariants.check(healthy())
    assert invariants.all_ok(results)
    assert len(results) == 8  # eight named checks


def test_silent_payment_drop_is_caught():
    m = healthy()
    m["checkout_requests"] = 130          # 30 requests answered ok but never saved (F1 / F6)
    assert failing(m) == {"requests_vs_saved"}


def test_honest_payment_failures_are_not_a_problem():
    m = healthy()
    m["checkout_requests"], m["payments_failed"] = 130, 30   # customers were told "failed"
    assert failing(m) == set()


def test_requests_in_flight_are_counted_exactly_not_tolerated():
    m = healthy()
    m["checkout_requests"] += 7
    m["in_flight_requests"] += 7          # seven more requests being handled right now: fine
    assert failing(m) == set()


def test_a_single_lost_order_is_caught_there_is_no_tolerance():
    m = healthy()
    m["checkout_requests"] += 1           # one request answered ok, never saved, not in flight
    assert failing(m) == {"requests_vs_saved"}


def test_lost_queue_message_is_caught():
    m = healthy()
    m["enqueued"] = 103                    # 5 orders enqueued but nowhere to be found
    assert failing(m) == {"queue_accounting"}


def test_hung_worker_is_caught():
    m = healthy()
    m["oldest_in_progress_age_s"] = invariants.SLA_S + 1
    m["worker_heartbeat_age_s"] = invariants.SLA_S + 1
    assert failing(m) == {"oldest_in_progress_age", "worker_heartbeat"}


def test_just_inside_the_sla_is_fine():
    m = healthy()
    m["oldest_in_progress_age_s"] = invariants.SLA_S
    assert failing(m) == set()


def test_parked_orders_are_flagged_but_still_accounted_for():
    m = healthy()
    m["pending"], m["parked"] = 8, 1       # one order moved from the queue to "parked"
    assert failing(m) == {"no_parked_orders"}   # not queue_accounting: nothing is missing


def test_silently_dropped_queue_orders_are_caught():
    m = healthy()
    m["enqueued"] = 138                    # F2: 40 orders counted as enqueued, then thrown away
    assert failing(m) == {"queue_accounting"}


def test_dead_lettered_orders_are_accounted_for_but_flagged():
    m = healthy()
    m["pending"], m["dead_letter"] = 4, 5  # 5 orders overflowed into the dead-letter list
    assert failing(m) == {"no_dead_letters"}


def test_payment_outage_is_caught_even_though_counters_balance():
    m = healthy()
    m.update(checkout_last_30s=40, failed_last_30s=40, checkout_last_5s=8, failed_last_5s=8)   # F5
    assert failing(m) == {"payment_success"}


def test_few_recent_checkouts_are_not_judged():
    m = healthy()
    n = invariants.MIN_CHECKOUTS - 1
    m.update(checkout_last_30s=n, failed_last_30s=n, checkout_last_5s=n, failed_last_5s=n)
    assert failing(m) == set()             # not enough data to call it an outage


def test_failure_rate_boundary():
    m = healthy()
    m.update(checkout_last_30s=40, failed_last_30s=10, checkout_last_5s=20, failed_last_5s=5)   # exactly 25%
    assert failing(m) == set()
    m.update(failed_last_30s=11, failed_last_5s=6)
    assert failing(m) == {"payment_success"}


def test_payment_alarm_clears_once_the_last_10s_are_healthy_after_a_fix():
    """Old failures still sit in the 30 s window right after a correct fix. They must not keep the alarm on."""
    m = healthy()
    m.update(checkout_last_30s=40, failed_last_30s=18, checkout_last_5s=20, failed_last_5s=1)
    assert failing(m) == set()


def test_a_short_blip_is_not_an_outage():
    m = healthy()
    m.update(checkout_last_30s=60, failed_last_30s=6, checkout_last_5s=20, failed_last_5s=6)   # 10% over 30 s
    assert failing(m) == set()


def test_replica_corruption_is_caught():
    m = healthy()
    m["sync"]["replica_checksum"] = "zzz"
    assert failing(m) == {"replica_checksum"}


def test_no_checksum_complaint_before_first_sync():
    m = healthy()
    m["sync"] = {"runs": 0, "copied_checksum": None, "replica_checksum": "abc"}
    assert failing(m) == set()


def test_run_checks_ignores_a_momentary_counter_race():
    """A counter invariant that fails once but passes on the re-sample is not reported."""
    bad = healthy()
    bad["enqueued"] = 101                  # transient: counters read a moment apart
    samples = [bad, healthy()]
    results = invariants.run_checks(lambda: copy.deepcopy(samples.pop(0)))
    assert invariants.all_ok(results)


def test_run_checks_reports_a_persistent_failure():
    bad = healthy()
    bad["enqueued"] = 101
    results = invariants.run_checks(lambda: copy.deepcopy(bad))
    assert not invariants.all_ok(results)


def test_summary_text_says_what_failed():
    m = healthy()
    m["checkout_requests"] = 130
    text = invariants.summarize(invariants.check(m))
    assert text.startswith("INVARIANTS FAILING")
    assert "FAIL requests_vs_saved" in text
