"""Unit tests for the invariant checker. Pure Python: no shop, no LLM, runs in about a second."""
import copy

from agent import invariants


def healthy():
    """Metrics from a shop that is working fine."""
    return {
        "checkout_requests": 100, "payments_failed": 0, "orders_saved": 100,
        "enqueued": 100, "processed": 90, "pending": 9, "in_progress": 1, "parked": 0,
        "oldest_in_progress_age_s": 0.1, "worker_heartbeat_age_s": 0.05,
        "sync": {"runs": 3, "copied_checksum": "abc", "replica_checksum": "abc"},
    }


def failing(m):
    return {r["name"] for r in invariants.check(m) if not r["ok"]}


def test_healthy_shop_passes_everything():
    results = invariants.check(healthy())
    assert invariants.all_ok(results)
    assert len(results) == 5 + 1  # six named checks


def test_silent_payment_drop_is_caught():
    m = healthy()
    m["checkout_requests"] = 130          # 30 requests answered ok but never saved (F1)
    assert failing(m) == {"requests_vs_saved"}


def test_honest_payment_failures_are_not_a_problem():
    m = healthy()
    m["checkout_requests"], m["payments_failed"] = 130, 30   # customers were told "failed"
    assert failing(m) == set()


def test_in_flight_requests_within_tolerance_are_ignored():
    m = healthy()
    m["checkout_requests"] += invariants.REQUEST_TOLERANCE
    assert failing(m) == set()
    m["checkout_requests"] += 1
    assert failing(m) == {"requests_vs_saved"}


def test_lost_queue_message_is_caught():
    m = healthy()
    m["enqueued"] = 105                    # 5 orders enqueued but nowhere to be found
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
