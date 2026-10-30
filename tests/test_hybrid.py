"""Unit tests for the hybrid's rule matching (pure Python): who gets to act, the rules or the LLM."""
from eval.hybrid import matching_rules


def test_each_single_known_fault_matches_exactly_one_rule():
    assert matching_rules({"oldest_in_progress_age", "worker_heartbeat"}, False) == ["stuck_worker"]
    assert matching_rules({"requests_vs_saved"}, True) == ["lost_orders"]
    assert matching_rules({"queue_accounting"}, True) == ["queue_loss"]
    assert matching_rules({"no_dead_letters"}, False) == ["queue_loss"]
    assert matching_rules({"replica_checksum"}, True) == ["sync_corruption"]
    assert matching_rules({"payment_success"}, False) == ["provider_outage"]


def test_two_faults_at_once_is_a_conflict_so_more_than_one_rule_matches():
    assert len(matching_rules({"oldest_in_progress_age", "requests_vs_saved"}, True)) == 2
    assert len(matching_rules({"queue_accounting", "replica_checksum"}, True)) == 2


def test_a_payment_failure_next_to_a_config_change_matches_no_rule():
    # the rules only call it a provider outage when the config is unchanged, so a config-caused
    # payment problem is something no rule covers
    assert matching_rules({"payment_success"}, True) == []


def test_several_failing_checks_of_the_same_fault_still_count_as_one_rule():
    assert matching_rules({"oldest_in_progress_age", "worker_heartbeat", "no_parked_orders"}, False) == ["stuck_worker"]
    assert matching_rules({"queue_accounting", "no_dead_letters"}, True) == ["queue_loss"]


def test_nothing_failing_matches_no_rule():
    assert matching_rules(set(), False) == []     # run() treats this as the all-clear case before calling this
