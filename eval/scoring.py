"""Pure scoring helpers for the eval (no shop, no network), so they can be unit-tested."""

# Actions that are a legitimate part of the fix for each injected fault.
FIX_ACTIONS = {
    "f1": {"rollback_config", "replay_lost_orders"},
    "f2": {"rollback_config", "requeue_unprocessed"},
    "f3": {"rollback_config", "resync_replica"},
    "f4": {"restart_worker", "requeue_stuck"},
    "f5": set(),   # unfixable: no action helps
    "f6": {"replay_lost_orders"},   # damage can be repaired, the cause cannot (no rollback helps: no config change)
    "f7": {"rollback_config"},
    "f8": set(),   # red herring: nothing needs fixing, so even a rollback is unnecessary
}

# Root-cause category each fault should be reported as. Novel faults have no category: "unknown" is correct.
ROOT_CAUSE_OF = {"f1": "payment_drop", "f2": "queue_loss", "f3": "sync_corruption", "f4": "stuck_worker",
                 "f5": "external_provider", "f6": "unknown", "f7": "unknown"}   # f8 (red herring) has no cause

# Which invariants show that a fault has actually done damage (its "signature").
SIGNATURE = {"f1": {"requests_vs_saved"}, "f2": {"queue_accounting", "no_dead_letters"}, "f3": {"replica_checksum"},
             "f4": {"oldest_in_progress_age", "worker_heartbeat"}, "f5": {"payment_success"},
             "f6": {"requests_vs_saved"}, "f7": {"payment_success"}}

# Invariants that cannot recover while an unfixable fault is active.
UNFIXABLE_EXEMPT = {"f5": {"payment_success"}, "f6": {"requests_vs_saved"}}

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
    """Did the shop end up healthy? `checks` = list of {"name","ok"}. While an unfixable fault is
    active (f5 provider down, f6 storage losing writes) its own signature check keeps failing, so it is exempt."""
    exempt = set().union(*(UNFIXABLE_EXEMPT.get(f, set()) for f in fault_ids)) if fault_ids else set()
    return all(c["ok"] for c in checks if c["name"] not in exempt)


def manifested_causes(fault_ids, failing_names):
    """Root causes of the injected faults that had actually done observable damage when the method
    started (their signature invariant was failing in an independent check). A fault that never
    produced a symptom (e.g. a hang that has not happened yet) cannot be diagnosed, so it is not expected."""
    failing, out = set(failing_names), []
    for f in fault_ids:
        if f in SIGNATURE and SIGNATURE[f] & failing and ROOT_CAUSE_OF[f] not in out:
            out.append(ROOT_CAUSE_OF[f])
    return out


def cost_usd(tokens_in, cache_read, cache_write, tokens_out):
    p = PRICE_PER_M
    return round((tokens_in * p["input"] + cache_read * p["cache_read"]
                  + cache_write * p["cache_write"] + tokens_out * p["output"]) / 1e6, 5)
