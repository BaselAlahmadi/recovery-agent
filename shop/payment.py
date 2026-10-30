"""Fake payment provider. Healthy version: always approves after a tiny delay."""
import time

from shop.logger import log


def charge(order_id, amount):
    """Return True if the payment was approved."""
    time.sleep(0.01)  # pretend network call
    log("payment", "charged", order_id=order_id, amount=amount)
    return True
