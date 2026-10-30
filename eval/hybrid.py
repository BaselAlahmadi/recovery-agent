"""HYBRID method: cheap fixed rules first, the LLM agent only when the rules are not enough.

  1. Look at which invariants fail and which rules would match.
       - nothing failing        -> the all-clear rule matches
       - exactly ONE rule       -> run the existing rules (eval/methods.py rules_only), then verify independently
       - NO rule matches        -> hand over to the LLM agent (something fails that no rule covers)
       - SEVERAL rules match    -> hand over to the LLM agent (conflict: several faults at once)
  2. If the rules ran but the invariants still fail afterwards -> hand over to the LLM agent.
  3. If the rules ran and everything passes -> stop. No LLM call, no tokens.

The rules and the agent are used exactly as they are. This file only decides who acts.
"""
import json
import time

from agent import invariants, tools
from eval import methods


def matching_rules(failing, config_changed):
    """Which of the existing rules would fire. These triggers are the same conditions rules_only() uses
    (copied here only so we can COUNT matches before acting; the actions still come from rules_only itself).
    The rollback step is not a separate rule: it is part of the damage rules, as in rules_only()."""
    rules = []
    if failing & {"oldest_in_progress_age", "worker_heartbeat", "no_parked_orders"}:
        rules.append("stuck_worker")
    if "requests_vs_saved" in failing:
        rules.append("lost_orders")
    if failing & {"queue_accounting", "no_dead_letters"}:
        rules.append("queue_loss")
    if "replica_checksum" in failing:
        rules.append("sync_corruption")
    if "payment_success" in failing and not config_changed:
        rules.append("provider_outage")
    return rules


def run():
    t0 = time.time()
    failing = {r["name"] for r in invariants.run_checks(tools.fetch_metrics) if not r["ok"]}
    config_changed = bool(failing) and bool(json.loads(tools.fetch_config())["differs_from_last_known_good"])
    matched = matching_rules(failing, config_changed) if failing else ["all_clear"]

    rules_rec, reason = None, ""
    if len(matched) == 1:
        rules_rec = methods.rules_only()
        if invariants.all_ok(invariants.run_checks(tools.fetch_metrics)):       # independent verification
            return {**rules_rec, "agent_seconds": round(time.time() - t0, 1),
                    "handover": 0, "handover_reason": "", "matched_rules": matched[0]}
        reason = f"verification failed after rule '{matched[0]}'"
    elif not matched:
        reason = "no rule matches"
    else:
        reason = "rules conflict: " + "+".join(matched)

    from agent.agent import Agent
    rec = Agent().run()                      # the unchanged full agent takes over from the current state
    rec["actions"] = (rules_rec["actions"] if rules_rec else []) + rec["actions"]
    rec.update(handover=1, handover_reason=reason, matched_rules="+".join(matched),
               agent_seconds=round(time.time() - t0, 1))
    return rec
