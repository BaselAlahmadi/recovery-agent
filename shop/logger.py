"""Structured JSON-lines logging: one file per component in logs/."""
import json
import threading
import time

from shop.config import LOG_DIR

_lock = threading.Lock()


def log(component, event, **fields):
    """Append {"ts":..., "component":..., "event":..., ...fields} to logs/<component>.jsonl."""
    LOG_DIR.mkdir(exist_ok=True)
    record = {"ts": round(time.time(), 3), "component": component, "event": event, **fields}
    with _lock:
        with open(LOG_DIR / f"{component}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
