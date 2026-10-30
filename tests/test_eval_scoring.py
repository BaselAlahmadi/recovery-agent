"""Unit tests for the eval's scoring helpers (pure Python)."""
from eval import scoring


def test_root_cause_f1_perfect_partial_and_wrong():
    assert scoring.root_cause_f1(["a", "b"], ["b", "a"]) == 1.0
    assert scoring.root_cause_f1(["a", "b"], ["a"]) == round(2 * 1.0 * 0.5 / 1.5, 3)   # precision 1, recall 0.5
    assert scoring.root_cause_f1(["a"], ["b"]) == 0.0
    assert scoring.root_cause_f1([], ["a"]) == 0.0           # inventing a cause on a healthy shop


def test_root_cause_f1_healthy_shop_naming_nothing_is_perfect():
    assert scoring.root_cause_f1([], []) == 1.0


def test_unnecessary_actions_on_healthy_shop_is_every_action():
    assert scoring.count_unnecessary(["restart_worker", "resync_replica"], []) == 2


def test_fix_actions_for_the_injected_fault_are_not_unnecessary():
    assert scoring.count_unnecessary(["rollback_config", "replay_lost_orders"], ["f1"]) == 0


def test_wrong_and_repeated_actions_are_unnecessary():
    names = ["rollback_config", "replay_lost_orders", "replay_lost_orders", "restart_worker"]
    assert scoring.count_unnecessary(names, ["f1"]) == 2     # the repeat and the unrelated restart


def test_shared_rollback_counts_once_across_combined_faults():
    assert scoring.count_unnecessary(["rollback_config", "requeue_unprocessed", "resync_replica"], ["f2", "f3"]) == 0


def test_f5_has_no_fix_so_any_action_for_it_is_unnecessary():
    assert scoring.count_unnecessary(["rollback_config"], ["f5"]) == 1


def test_recovered_exempts_payment_success_only_when_provider_is_down():
    checks = [{"name": "queue_accounting", "ok": True}, {"name": "payment_success", "ok": False}]
    assert scoring.recovered(checks, ["f4", "f5"]) is True
    assert scoring.recovered(checks, ["f4"]) is False
    checks[0]["ok"] = False
    assert scoring.recovered(checks, ["f5"]) is False       # other failures are never exempt


def test_cost_matches_the_price_table():
    # 1M uncached in + 1M out = $0.10 + $0.50
    assert scoring.cost_usd(1_000_000, 0, 0, 1_000_000) == 0.6
    assert scoring.cost_usd(0, 1_000_000, 0, 0) == 0.01
