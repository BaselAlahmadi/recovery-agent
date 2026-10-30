"""Paths and runtime config for the shop.

The shop re-reads chaos/runtime_config.json every time it needs a setting.
chaos/ will write that file later to switch faults on and off; the shop only reads it.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
DATA_DIR = ROOT / "data"
RUNTIME_CONFIG = ROOT / "chaos" / "runtime_config.json"

# Healthy defaults. A key in the runtime config file overrides the default.
DEFAULTS = {
    "queue_capacity": 1000,   # max orders waiting for the worker
    "step_delay": 0.05,       # seconds each fulfillment step takes
    "sync_interval": 5.0,     # seconds between inventory sync runs
}


def get(key):
    """Return one setting: file value if present, otherwise the default."""
    try:
        data = json.loads(RUNTIME_CONFIG.read_text())
    except (OSError, ValueError):  # file missing or half-written -> use defaults
        data = {}
    return data.get(key, DEFAULTS[key])
