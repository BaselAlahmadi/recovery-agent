"""The shop's OWN configuration (separate from chaos/runtime_config.json).

Think of it as the settings that were "deployed" to the shop:
  data/shop_config.json      = live config the shop is using right now
  data/shop_config_lkg.json  = last-known-good copy, so a bad deploy can be rolled back
"""
import json
import os

from shop.config import DATA_DIR
from shop.logger import log

CONFIG_PATH = DATA_DIR / "shop_config.json"
LKG_PATH = DATA_DIR / "shop_config_lkg.json"

DEFAULTS = {
    # What to do when the payment provider times out:
    #   "retry_then_fail"  -> retry a couple of times, then honestly tell the customer it failed (good)
    #   "assume_success"   -> pretend it worked (BAD: this is the F1 bug)
    "payment_timeout_policy": "retry_then_fail",
    "payment_retries": 2,
}

_seen = {"cfg": None}  # last config we saw, so we can log when it changes


def write_atomic(path, data):
    """Write to a temp file then swap, so readers never see a half-written file."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _read(path):
    try:
        return {**DEFAULTS, **json.loads(path.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def init():
    """Called at shop start: live and last-known-good both begin as the healthy defaults."""
    DATA_DIR.mkdir(exist_ok=True)
    write_atomic(CONFIG_PATH, DEFAULTS)
    write_atomic(LKG_PATH, DEFAULTS)
    _seen["cfg"] = dict(DEFAULTS)


def _diff(old, new):
    return {k: [old.get(k), new.get(k)] for k in new if old.get(k) != new.get(k)}


def get(key):
    """Read one setting from the live config. Logs an audit line if the config changed."""
    cfg = _read(CONFIG_PATH)
    if _seen["cfg"] is not None and cfg != _seen["cfg"]:
        log("shop", "config_changed", changes=_diff(_seen["cfg"], cfg))
    _seen["cfg"] = cfg
    return cfg[key]


def view():
    """What the agent sees at GET /admin/config."""
    live, lkg = _read(CONFIG_PATH), _read(LKG_PATH)
    return {"live": live, "last_known_good": lkg, "differs_from_last_known_good": _diff(lkg, live)}


def rollback():
    """Restore the live config to the last-known-good copy."""
    live, lkg = _read(CONFIG_PATH), _read(LKG_PATH)
    if live == lkg:
        return {"rolled_back": False, "note": "live config already equals last-known-good"}
    write_atomic(CONFIG_PATH, lkg)
    log("shop", "config_rolled_back", restored=_diff(live, lkg))
    return {"rolled_back": True, "restored": _diff(live, lkg)}
