"""Paths and runtime config for the shop.

The shop re-reads chaos/runtime_config.json every time it needs a setting.
chaos/ will write that file later to switch faults on and off; the shop only reads it.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# All state (logs, databases, fault switches) lives under STATE_DIR. By default that is the repo
# folder; the eval sets SHOP_STATE_DIR so many shops can run side by side without sharing anything.
STATE_DIR = Path(os.getenv("SHOP_STATE_DIR", ROOT))
LOG_DIR = STATE_DIR / "logs"
DATA_DIR = STATE_DIR / "data"
RUNTIME_CONFIG = STATE_DIR / "chaos" / "runtime_config.json"

# Healthy defaults. A key in the runtime config file overrides the default.
DEFAULTS = {
    "step_delay": 0.05,       # seconds each fulfillment step takes
    "sync_interval": 5.0,     # seconds between inventory sync runs
    # --- environment conditions injected by chaos/ (0 = healthy) ---
    "f1_drop_rate": 0.0,      # F1: share of payment calls that time out (flaky provider)
    "f2_extra_delay": 0.0,    # F2: extra seconds per fulfillment step (slow backend = load)
    "f3_corrupt_rate": 0.0,   # F3: share of replica rows a buggy sync run corrupts
    "f4_hang_rate": 0.0,      # F4: share of orders whose "pack" step hangs forever
    "f5_provider_down": 0.0,  # F5: share of payment calls that time out (1.0 = provider fully down)
}


def get(key):
    """Return one setting: file value if present, otherwise the default."""
    try:
        data = json.loads(RUNTIME_CONFIG.read_text())
    except (OSError, ValueError):  # file missing or half-written -> use defaults
        data = {}
    return data.get(key, DEFAULTS[key])


def modified_at():
    """When the runtime config file last changed (0 if it doesn't exist). Used by fault F4."""
    try:
        return RUNTIME_CONFIG.stat().st_mtime
    except OSError:
        return 0.0
