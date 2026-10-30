"""Fault injector CLI.

  python -m chaos on f1 [--rate 0.3]   turn a fault on (optionally set its strength)
  python -m chaos off f1               turn one fault off
  python -m chaos list                 show active faults
  python -m chaos clear                turn everything off

Each fault has up to two parts:
  1. an ENVIRONMENT condition, a key in chaos/runtime_config.json (flaky provider, slow worker...)
  2. a bad DEPLOY: wrong values written into the shop's own config (data/shop_config.json)
     while its last-known-good copy stays untouched, so the agent can roll back.
Several faults can be on at once because each one has its own keys. Start the shop first.
`off fX` puts back only that fault's deployed settings; `clear` resets everything.
"""
import argparse
import json
import os
import shutil

from shop import settings
from shop.config import RUNTIME_CONFIG

FAULTS = {
    "f1": {"key": "f1_drop_rate", "default": 0.3,
           "deploy": {"payment_timeout_policy": "assume_success"},
           "desc": "payment drop: provider flaky (rate) + bad deploy 'assume success on timeout'"},
    "f2": {"key": "f2_extra_delay", "default": 0.1,
           "deploy": {"queue_capacity": 10, "queue_overflow_policy": "drop"},
           "desc": "queue loss: worker slower by <rate> s/step (load) + bad deploy 'tiny queue, silently drop'"},
    "f3": {"key": "f3_corrupt_rate", "default": 0.1,
           "deploy": {"sync_mode": "fast"},
           "desc": "sync corruption: share of replica rows corrupted per run + bad deploy sync_mode=fast"},
    "f4": {"key": "f4_hang_rate", "default": 0.1, "deploy": {},
           "desc": "workflow hang: share of orders whose 'pack' step hangs forever"},
    "f5": {"key": "f5_provider_down", "default": 1.0, "deploy": {},
           "desc": "UNFIXABLE: payment provider is down (share of calls that time out)"},
    "f6": {"key": "f6_save_fail_rate", "default": 0.3, "deploy": {},
           "desc": "NOVEL, no config change: share of order writes silently lost (same symptom as f1, different cause)"},
    "f7": {"key": "f7_flaky_rate", "default": 0.4, "deploy": {"payment_retries": 0},
           "desc": "payment provider flaky (rate) + bad deploy payment_retries=0 (a setting no rule mentions)"},
    "f8": {"key": "f8_red_herring", "default": 1.0, "deploy": {"receipt_footer": "AUTUMN-SALE"},
           "desc": "RED HERRING: a harmless config change that breaks nothing (the shop never reads f8_red_herring)"},
}


def read():
    try:
        return json.loads(RUNTIME_CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def write(data):
    # write to a temp file then swap, so the shop never reads a half-written file
    RUNTIME_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = RUNTIME_CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, RUNTIME_CONFIG)


def deploy(changes):
    """Simulate a bad deploy: change ONLY the live shop config (last-known-good stays untouched)."""
    if not changes:
        return
    if not settings.CONFIG_PATH.exists():
        print("warning: shop config not found. Start the shop first, then turn the fault on.")
        return
    cfg = json.loads(settings.CONFIG_PATH.read_text())
    cfg.update(changes)
    settings.write_atomic(settings.CONFIG_PATH, cfg)


def undeploy(keys):
    """Environment reset for one fault: put just these keys back to their last-known-good values."""
    if not keys or not settings.CONFIG_PATH.exists():
        return
    cfg = json.loads(settings.CONFIG_PATH.read_text())
    lkg = json.loads(settings.LKG_PATH.read_text())
    cfg.update({k: lkg[k] for k in keys if k in lkg})
    settings.write_atomic(settings.CONFIG_PATH, cfg)


def main():
    p = argparse.ArgumentParser(prog="chaos")
    p.add_argument("cmd", choices=["on", "off", "list", "clear"])
    p.add_argument("fault", nargs="?", choices=list(FAULTS))
    p.add_argument("--rate", type=float, help="fault strength (meaning depends on the fault)")
    a = p.parse_args()

    cfg = read()
    if a.cmd in ("on", "off") and not a.fault:
        p.error(f"'{a.cmd}' needs a fault name: {', '.join(FAULTS)}")
    if a.cmd == "on":
        f = FAULTS[a.fault]
        cfg[f["key"]] = a.rate if a.rate is not None else f["default"]
        write(cfg)
        deploy(f["deploy"])
    elif a.cmd == "off":
        f = FAULTS[a.fault]
        cfg.pop(f["key"], None)
        write(cfg)
        undeploy(list(f["deploy"]))
    elif a.cmd == "clear":
        write({})
        cfg = {}
        if settings.LKG_PATH.exists():
            shutil.copyfile(settings.LKG_PATH, settings.CONFIG_PATH)

    active = {n: cfg[f["key"]] for n, f in FAULTS.items() if f["key"] in cfg}
    print("active faults:", active or "none")
    if a.cmd == "list":
        for n, f in FAULTS.items():
            print(f"  {n}: {f['desc']}")


if __name__ == "__main__":
    main()
