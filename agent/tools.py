"""What the agent can see and do. Everything goes through the shop's HTTP API or logs/.

This file deliberately imports nothing from shop/ or chaos/: the agent only gets
observable signals (metrics, health, logs, config view) and the allowlisted admin actions.
"""
import json
import os
from pathlib import Path

import requests

SHOP_URL = os.getenv("SHOP_URL", "http://127.0.0.1:8000")
LOG_DIR = Path(os.getenv("SHOP_STATE_DIR", Path(__file__).resolve().parent.parent)) / "logs"
LOG_COMPONENTS = ["shop", "requests", "checkout", "payment", "queue", "worker", "sync"]

# ACTION ALLOWLIST: the agent cannot call anything else.
ACTIONS = {
    "restart_worker": "/admin/restart_worker",
    "requeue_stuck": "/admin/requeue_stuck",
    "rollback_config": "/admin/rollback_config",
    "replay_lost_orders": "/admin/replay_lost_orders",
    "requeue_unprocessed": "/admin/requeue_unprocessed",
    "resync_replica": "/admin/resync_replica",
}

# Root-cause categories = which part of the shop failed. A fixed list keeps reports clean and scoreable.
ROOT_CAUSES = ["payment_drop", "queue_loss", "sync_corruption", "stuck_worker", "external_provider", "unknown"]


def fetch_metrics():
    return requests.get(f"{SHOP_URL}/metrics", timeout=5).json()


def fetch_health():
    return requests.get(f"{SHOP_URL}/health", timeout=5).json()


def fetch_config():
    return json.dumps(requests.get(f"{SHOP_URL}/admin/config", timeout=5).json())


def metrics_text(m):
    """Compact view of /metrics (saves tokens)."""
    s = m["sync"]
    flat = {k: v for k, v in m.items() if k != "sync"}
    flat.update(sync_runs=s["runs"], sync_checksums_match=s["copied_checksum"] == s["replica_checksum"])
    return json.dumps(flat, separators=(",", ":"))


def read_logs(component, n=6):
    if component not in LOG_COMPONENTS:
        return f"unknown log '{component}'. choose from {LOG_COMPONENTS}"
    path = LOG_DIR / f"{component}.jsonl"
    if not path.exists():
        return "(no log file)"
    lines = path.read_text(encoding="utf-8").splitlines()[-min(int(n), 15):]
    return "\n".join(l[:160] for l in lines) or "(empty)"


def call_action(name):
    r = requests.post(f"{SHOP_URL}{ACTIONS[name]}", timeout=60)   # replay can take a while
    return json.dumps(r.json())


_ACTION_PROPS = {
    "reason": {"type": "string", "description": "Evidence-based reason"},
    "confidence": {"type": "number", "description": "0-1"},
}
_ROOT_CAUSE_PROPS = {
    "root_cause_categories": {"type": "array", "items": {"type": "string", "enum": ROOT_CAUSES},
                              "description": "Every failing part (payment_drop=orders told ok but not saved, "
                                             "queue_loss, sync_corruption, stuck_worker, external_provider=outside shop control)"},
    "root_cause_detail": {"type": "string", "description": "One plain sentence. No markup."},
}


def _action(name, description):
    return {"name": name, "description": "ACTION. " + description,
            "input_schema": {"type": "object", "properties": _ACTION_PROPS, "required": ["reason", "confidence"]}}


# Tool definitions shown to the model.
TOOLS = [
    {"name": "check_invariants", "description": "Run all invariant checks now.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_metrics", "description": "Raw /metrics counters.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "check_health", "description": "/health: only says the process is up.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_shop_config", "description": "Shop's live config vs last-known-good, and what differs.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "read_logs", "description": f"Last lines of a log. Components: {LOG_COMPONENTS}",
     "input_schema": {"type": "object", "properties": {"component": {"type": "string"}, "n": {"type": "integer"}},
                      "required": ["component"]}},
    _action("restart_worker", "Fresh worker replaces a stuck one; its unfinished orders are parked until requeue_stuck."),
    _action("requeue_stuck", "Put parked orders back on the queue (after restart_worker)."),
    _action("rollback_config", "Restore ALL shop config to last-known-good. Fixes a bad deploy; repairs no damage already done."),
    _action("replay_lost_orders", "Re-create orders customers were told 'ok' but that were never saved. Idempotent. Do after the cause is fixed."),
    _action("requeue_unprocessed", "Re-queue saved orders that never got processed (dropped from the queue or dead-lettered). Idempotent."),
    _action("resync_replica", "Run an inventory sync now using current sync settings (repairs corrupted replica rows once the cause is fixed)."),
    {"name": "no_incident", "description": "Everything is healthy and you took no actions.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
    {"name": "resolve", "description": "Incident fixed by your actions; accepted only if all invariants pass now.",
     "input_schema": {"type": "object", "properties": {**_ROOT_CAUSE_PROPS, "summary": {"type": "string"}},
                      "required": ["root_cause_categories", "root_cause_detail", "summary"]}},
    {"name": "escalate", "description": "Hand over to a human: cannot fix safely, cause outside the shop, or no allowed action helps.",
     "input_schema": {"type": "object", "properties": {**_ROOT_CAUSE_PROPS, "reason": {"type": "string"},
                                                       "suggested_next_steps": {"type": "string"}},
                      "required": ["reason", "root_cause_categories", "suggested_next_steps"]}},
]


# Logs-only ablation: no invariant checks and no raw counters, only logs, /health and the config view.
TOOLS_LOGS_ONLY = [t for t in TOOLS if t["name"] not in ("check_invariants", "get_metrics")]
