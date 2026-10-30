"""What the agent can see and do. Everything goes through the shop's HTTP API or logs/.

This file deliberately imports nothing from shop/ or chaos/: the agent only gets
observable signals (metrics, health, logs) and the allowlisted admin actions.
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
}


def fetch_metrics():
    return requests.get(f"{SHOP_URL}/metrics", timeout=5).json()


def fetch_health():
    return requests.get(f"{SHOP_URL}/health", timeout=5).json()


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
    r = requests.post(f"{SHOP_URL}{ACTIONS[name]}", timeout=10)
    return json.dumps(r.json())


_ACTION_PROPS = {
    "reason": {"type": "string", "description": "Evidence-based reason for this action"},
    "confidence": {"type": "number", "description": "0-1 confidence that this is the right action"},
}

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
    {"name": "read_logs",
     "description": f"Last lines of one component log. Components: {LOG_COMPONENTS}",
     "input_schema": {"type": "object", "properties": {"component": {"type": "string"}, "n": {"type": "integer"}},
                      "required": ["component"]}},
    {"name": "restart_worker",
     "description": "ACTION. Start a fresh order worker and retire the stuck one. Its unfinished orders are "
                    "PARKED (not lost) until you call requeue_stuck. Use when the worker is stuck/hung.",
     "input_schema": {"type": "object", "properties": _ACTION_PROPS, "required": ["reason", "confidence"]}},
    {"name": "requeue_stuck",
     "description": "ACTION. Put parked orders back on the queue so they get processed. Use after restart_worker.",
     "input_schema": {"type": "object", "properties": _ACTION_PROPS, "required": ["reason", "confidence"]}},
    {"name": "resolve",
     "description": "Declare the incident fixed. Only accepted if all invariants pass right now.",
     "input_schema": {"type": "object", "properties": {"root_cause": {"type": "string"}, "summary": {"type": "string"}},
                      "required": ["root_cause", "summary"]}},
    {"name": "escalate",
     "description": "Hand over to a human when you cannot fix this safely or confidently.",
     "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}, "root_cause_guess": {"type": "string"},
                                                       "suggested_next_steps": {"type": "string"}},
                      "required": ["reason"]}},
]
