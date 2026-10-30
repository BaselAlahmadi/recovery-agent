"""Structured JSON-lines logging: one file per component in logs/."""
import json
import threading
import time

from shop.config import LOG_DIR

_lock = threading.Lock()


def reset():
    """Delete old log files so every shop start begins with clean logs."""
    LOG_DIR.mkdir(exist_ok=True)
    with _lock:
        for p in LOG_DIR.glob("*.jsonl"):
            p.unlink()


def log(component, event, **fields):
    """Append {"ts":..., "component":..., "event":..., ...fields} to logs/<component>.jsonl."""
    LOG_DIR.mkdir(exist_ok=True)
    record = {"ts": round(time.time(), 3), "component": component, "event": event, **fields}
    with _lock:
        with open(LOG_DIR / f"{component}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
