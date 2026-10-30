"""Fault injector CLI.

  python -m chaos on f1 [--rate 0.3]   turn a fault on (optionally set its strength)
  python -m chaos off f1               turn one fault off
  python -m chaos list                 show active faults
  python -m chaos clear                turn everything off

Faults are just keys in chaos/runtime_config.json; the shop re-reads that file live.
Several faults can be on at once because each one has its own key.
"""
import argparse
import json
import os

from shop.config import RUNTIME_CONFIG

# fault id -> (config key the shop reads, default strength, description)
FAULTS = {
    "f1": ("f1_drop_rate", 0.3, "payment drop: share of payments that time out and silently lose the order"),
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
    elif a.cmd == "off":
        cfg.pop(FAULTS[a.fault][0], None)
        write(cfg)
    elif a.cmd == "clear":
        write({})
        cfg = {}

    active = {f: cfg[k] for f, (k, _, _) in FAULTS.items() if k in cfg}
    print("active faults:", active or "none")
    if a.cmd == "list":
        for f, (_, _, desc) in FAULTS.items():
            print(f"  {f}: {desc}")


if __name__ == "__main__":
    main()
