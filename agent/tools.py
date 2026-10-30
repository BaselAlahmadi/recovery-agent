"""What the agent can see and do. Everything goes through the shop's HTTP API or logs/.

This file deliberately imports nothing from shop/ or chaos/: the agent only gets
observable signals (metrics, health, logs, config view) and the allowlisted admin actions.
"""
import json
import os
from pathlib import Path

import requests

SHOP_URL = os.getenv("SHOP_URL", "http://127.0.0.1:8000")
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_COMPONENTS = ["shop", "requests", "checkout", "payment", "queue", "worker", "sync"]

# ACTION ALLOWLIST: the agent cannot call anything else.
ACTIONS = {
    "restart_worker": "/admin/restart_worker",
    "requeue_stuck": "/admin/requeue_stuck",
    "rollback_config": "/admin/rollback_config",
    "replay_lost_orders": "/admin/replay_lost_orders",
}

# Root-cause categories: a fixed list, so reports are clean and can be scored automatically.
ROOT_CAUSES = ["stuck_worker", "bad_config", "queue_overflow", "sync_corruption", "external_provider", "unknown"]


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
    return json.dumps(flat)


def read_logs(component, n=8):
    if component not in LOG_COMPONENTS:
        return f"unknown log '{component}'. choose from {LOG_COMPONENTS}"
    path = LOG_DIR / f"{component}.jsonl"
    if not path.exists():
        return "(no log file)"
    lines = path.read_text(encoding="utf-8").splitlines()[-min(int(n), 20):]
    return "\n".join(l[:200] for l in lines) or "(empty)"


def call_action(name):
    r = requests.post(f"{SHOP_URL}{ACTIONS[name]}", timeout=60)   # replay can take a while
    return json.dumps(r.json())


_ACTION_PROPS = {
    "reason": {"type": "string", "description": "Evidence-based reason for this action"},
    "confidence": {"type": "number", "description": "0-1 confidence that this is the right action"},
}
_ROOT_CAUSE_PROPS = {
    "root_cause_category": {"type": "string", "enum": ROOT_CAUSES},
    "root_cause_detail": {"type": "string", "description": "One plain sentence. No markup or tags."},
}


def _action(name, description):
    return {"name": name, "description": "ACTION. " + description,
            "input_schema": {"type": "object", "properties": _ACTION_PROPS, "required": ["reason", "confidence"]}}


# Tool definitions shown to the model.
TOOLS = [
    {"name": "check_invariants",
     "description": "Run all business-invariant checks (the shop's vital signs). Always start here.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_metrics",
     "description": "Raw /metrics counters.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "check_health",
     "description": "Call /health. Only says the process is up, not that the shop works.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_shop_config",
     "description": "Read-only: the shop's live config next to its last-known-good config, and what differs.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "read_logs",
     "description": f"Last lines of one component log. Components: {LOG_COMPONENTS}",
     "input_schema": {"type": "object", "properties": {"component": {"type": "string"}, "n": {"type": "integer"}},
                      "required": ["component"]}},
    _action("restart_worker", "Start a fresh order worker and retire the stuck one. Its unfinished orders are "
                              "PARKED (not lost) until you call requeue_stuck. Use when the worker is stuck/hung."),
    _action("requeue_stuck", "Put parked orders back on the queue so they get processed. Use after restart_worker."),
    _action("rollback_config", "Restore the shop's configuration to its last-known-good version. Use when a bad "
                               "config change is the cause. Stops NEW damage; does not repair orders already lost."),
    _action("replay_lost_orders", "Re-create orders that customers were told succeeded but were never saved, by "
                                  "replaying the request log. Safe to repeat (never duplicates). Do this AFTER the "
                                  "cause is fixed, otherwise new orders keep getting lost."),
    {"name": "no_incident",
     "description": "Everything is healthy and you took no actions: report that there is no incident. "
                    "Only accepted if all invariants pass and you took no actions.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
    {"name": "resolve",
     "description": "Declare an incident fixed (you took actions). Only accepted if all invariants pass right now.",
     "input_schema": {"type": "object", "properties": {**_ROOT_CAUSE_PROPS, "summary": {"type": "string"}},
                      "required": ["root_cause_category", "root_cause_detail", "summary"]}},
    {"name": "escalate",
     "description": "Hand over to a human when you cannot fix this safely or confidently.",
     "input_schema": {"type": "object", "properties": {**_ROOT_CAUSE_PROPS, "reason": {"type": "string"},
                                                       "suggested_next_steps": {"type": "string"}},
                      "required": ["reason", "root_cause_category"]}},
]
