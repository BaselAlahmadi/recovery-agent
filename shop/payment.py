"""Fake payment provider. Healthy version: always approves after a tiny delay."""
import random
import time

from shop import config

from shop.logger import log


def charge(order_id, amount):
    """Return "ok" (approved), "declined", or "timeout" (provider never answered)."""
    # FAULT F1: some calls time out. Nothing is logged here on purpose (silent failure).
    if random.random() < config.get("f1_drop_rate"):
        time.sleep(0.2)
        return "timeout"
    time.sleep(0.01)  # pretend network call
    log("payment", "charged", order_id=order_id, amount=amount)
    return "ok"
