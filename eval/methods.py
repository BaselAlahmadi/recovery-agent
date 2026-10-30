"""The things we compare. Each returns a record with the same fields as Agent.run().

  agent         full agent (LLM + invariant checks + verify step)
  no_invariants ablation: logs only, no invariant checks / verification (LLM)
  no_verify     ablation: no re-check after acting, no resolve gate (LLM)
  rules_only    baseline: fixed if-then rules over the same invariants, no LLM
  restart_all   baseline: "restart everything" script, no diagnosis, never escalates
"""
import json
import time

from agent import invariants, tools

VERIFY_WAIT_S = 5


def _record(actions, outcome, categories, summary, seconds):
    return {"outcome": outcome, "root_cause_categories": categories, "actions": actions, "summary": summary,
            "tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cache_write": 0, "turns": 0,
            "agent_seconds": round(seconds, 1)}


def restart_all():
    """The classic ops reflex: bounce the worker, kick the sync job, say 'fixed'. No checks."""
    t0, actions = time.time(), []
    for name in ("restart_worker", "requeue_stuck", "resync_replica"):
        actions.append({"action": name, "reason": "restart everything", "confidence": 1, "result": tools.call_action(name)})
    time.sleep(VERIFY_WAIT_S)
    return _record(actions, "RESOLVED", [], "Restarted everything.", time.time() - t0)


def rules_only():
    """If-then rules over the same invariants the agent sees. Strong but rigid: it can only
    do what its rules say, in the order they say."""
    t0, actions, causes = time.time(), [], []

    def act(name):
        actions.append({"action": name, "reason": "rule", "confidence": 1, "result": tools.call_action(name)})

    def add(cause):
        if cause not in causes:
            causes.append(cause)

    external = False
    for _ in range(2):                                   # act, verify, and at most one more round
        failing = {r["name"] for r in invariants.run_checks(tools.fetch_metrics) if not r["ok"]}
        if not failing:
            break
        config_changed = bool(json.loads(tools.fetch_config())["differs_from_last_known_good"])
        damage_failing = failing & {"requests_vs_saved", "queue_accounting", "no_dead_letters", "replica_checksum"}
        if config_changed and damage_failing:            # fix the cause first
            act("rollback_config")
        if "requests_vs_saved" in failing:
            act("replay_lost_orders"); add("payment_drop")
        if failing & {"queue_accounting", "no_dead_letters"}:
            act("requeue_unprocessed"); add("queue_loss")
        if "replica_checksum" in failing:
            act("resync_replica"); add("sync_corruption")
        if failing & {"oldest_in_progress_age", "worker_heartbeat", "no_parked_orders"}:
            if failing & {"oldest_in_progress_age", "worker_heartbeat"}:
                act("restart_worker")
            act("requeue_stuck"); add("stuck_worker")
        if "payment_success" in failing and not config_changed:
            external = True; add("external_provider")    # nothing in the shop explains it
        time.sleep(VERIFY_WAIT_S)

    final_failing = {r["name"] for r in invariants.run_checks(tools.fetch_metrics) if not r["ok"]}
    if external or (final_failing - {"payment_success"} and actions):
        outcome = "ESCALATED"
    else:
        outcome = "RESOLVED" if actions else "NO_INCIDENT"
    return _record(actions, outcome, causes, "rules fired: " + ", ".join(a["action"] for a in actions), time.time() - t0)


def run(method):
    if method == "restart_all":
        return restart_all()
    if method == "rules_only":
        return rules_only()
    from agent.agent import Agent
    flags = {"agent": {}, "no_invariants": {"use_invariants": False}, "no_verify": {"verify": False}}[method]
    return Agent(**flags).run()
