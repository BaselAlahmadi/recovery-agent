"""Pure scoring helpers for the eval (no shop, no network), so they can be unit-tested."""

# Actions that are a legitimate part of the fix for each injected fault.
FIX_ACTIONS = {
    "f1": {"rollback_config", "replay_lost_orders"},
    "f2": {"rollback_config", "requeue_unprocessed"},
    "f3": {"rollback_config", "resync_replica"},
    "f4": {"restart_worker", "requeue_stuck"},
    "f5": set(),   # unfixable: no action helps
}

# Haiku 5.5 list prices in $ per million tokens (prompts up to 100K tokens).
# Cache read ~0.1x and cache write ~1.25x of the input price.
PRICE_PER_M = {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125}


def root_cause_f1(expected, predicted):
    """F1 overlap between expected and predicted root-cause sets (1.0 = identical).
    Both empty (healthy shop, nothing to name) counts as a perfect 1.0."""
    e, p = set(expected), set(predicted)
    if not e and not p:
        return 1.0
    hit = len(e & p)
    if hit == 0:
        return 0.0
    precision, recall = hit / len(p), hit / len(e)
    return round(2 * precision * recall / (precision + recall), 3)


def count_unnecessary(action_names, fault_ids):
    """Actions that were not part of the fix for the injected faults, plus repeats of an action
    that was already taken. On a healthy shop every action is unnecessary."""
    allowed = set().union(*(FIX_ACTIONS[f] for f in fault_ids)) if fault_ids else set()
    seen, n = set(), 0
    for a in action_names:
        if a not in allowed or a in seen:
            n += 1
        seen.add(a)
    return n


def recovered(checks, fault_ids):
    """Did the shop end up healthy? `checks` = list of {"name","ok"}. If the payment provider is
    down (f5) the payment_success check is expected to keep failing, so it is exempt."""
    exempt = {"payment_success"} if "f5" in fault_ids else set()
    return all(c["ok"] for c in checks if c["name"] not in exempt)


def cost_usd(tokens_in, cache_read, cache_write, tokens_out):
    p = PRICE_PER_M
    return round((tokens_in * p["input"] + cache_read * p["cache_read"]
                  + cache_write * p["cache_write"] + tokens_out * p["output"]) / 1e6, 5)
