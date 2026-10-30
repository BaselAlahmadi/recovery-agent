"""Fault injector CLI.

  python -m chaos on f1 [--rate 0.3]   turn a fault on (optionally set its strength)
  python -m chaos off f1               turn one fault off
  python -m chaos list                 show active faults
  python -m chaos clear                turn everything off

Faults are keys in chaos/runtime_config.json; the shop re-reads that file live.
Several faults can be on at once because each one has its own key.

F1 has two parts: the payment provider becomes flaky (runtime config), AND a bad setting
is "deployed" into the shop's own config (data/shop_config.json). Start the shop first.
`off f1` / `clear` also put the shop's config back, so the environment is clean again.
"""
import argparse
import json
import os
import shutil

from shop import settings
from shop.config import RUNTIME_CONFIG

# fault id -> (config key the shop reads, default strength, description)
FAULTS = {
    "f1": ("f1_drop_rate", 0.3, "payment drop: provider is flaky AND a bad 'assume success on timeout' config is deployed"),
    "f4": ("f4_hang_rate", 0.1, "workflow hang: share of orders whose 'pack' step hangs forever"),
}


def read():
    try:
        return json.loads(RUNTIME_CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def write(data):
    # write to a temp file then swap, so the shop never reads a half-written file
    tmp = RUNTIME_CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, RUNTIME_CONFIG)


def deploy_bad_payment_config():
    """Simulate a bad deploy: change ONLY the live shop config (last-known-good stays untouched)."""
    if not settings.CONFIG_PATH.exists():
        print("warning: shop config not found. Start the shop first, then turn F1 on.")
        return
    cfg = json.loads(settings.CONFIG_PATH.read_text())
    cfg["payment_timeout_policy"] = "assume_success"
    settings.write_atomic(settings.CONFIG_PATH, cfg)


def restore_shop_config():
    """Environment reset: put the live shop config back to the last-known-good copy."""
    if settings.LKG_PATH.exists():
        shutil.copyfile(settings.LKG_PATH, settings.CONFIG_PATH)


def main():
    p = argparse.ArgumentParser(prog="chaos")
    p.add_argument("cmd", choices=["on", "off", "list", "clear"])
    p.add_argument("fault", nargs="?", choices=list(FAULTS))
    p.add_argument("--rate", type=float, help="fault strength between 0 and 1")
    a = p.parse_args()

    cfg = read()
    if a.cmd in ("on", "off") and not a.fault:
        p.error(f"'{a.cmd}' needs a fault name: {', '.join(FAULTS)}")
    if a.cmd == "on":
        key, default, _ = FAULTS[a.fault]
        cfg[key] = a.rate if a.rate is not None else default
        write(cfg)
        if a.fault == "f1":
            deploy_bad_payment_config()
    elif a.cmd == "off":
        cfg.pop(FAULTS[a.fault][0], None)
        write(cfg)
        if a.fault == "f1":
            restore_shop_config()
    elif a.cmd == "clear":
        write({})
        cfg = {}
        restore_shop_config()

    active = {f: cfg[k] for f, (k, _, _) in FAULTS.items() if k in cfg}
    print("active faults:", active or "none")
    if a.cmd == "list":
        for f, (_, _, desc) in FAULTS.items():
            print(f"  {f}: {desc}")


if __name__ == "__main__":
    main()
