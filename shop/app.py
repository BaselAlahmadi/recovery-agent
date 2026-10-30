"""The shop's web API. Run with: python -m uvicorn shop.app:app --port 8000"""
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shop import db, logger, metrics, orders, payment, settings, sync, worker
from shop.logger import log

app = FastAPI(title="shop")
START = time.time()


class Order(BaseModel):
    order_id: str
    sku: str
    qty: int
    amount: float


@app.on_event("startup")
def startup():
    logger.reset()       # fresh logs + fresh DB + fresh config every start (replay relies on this match)
    db.init_db()
    settings.init()
    worker.start()
    sync.start()
    log("shop", "started")


def _respond(order_id, status, code=200):
    """Answer the customer AND record what we told them (needed to find 'told ok, never saved')."""
    log("requests", "response", order_id=order_id, status=status)
    metrics.record_outcome(status == "ok")
    return JSONResponse({"status": status, "order_id": order_id}, status_code=code)


@app.post("/checkout")
def checkout(order: Order):
    metrics.inc("checkout_requests")
    o = order.model_dump()
    # request log: every request is recorded first, so lost orders can be replayed later
    log("requests", "checkout", **o)

    policy = settings.get("payment_timeout_policy")
    result = payment.charge(order.order_id, order.amount)

    if result == "timeout":
        metrics.inc("payment_timeouts")
        if policy == "assume_success":
            # BUG (this is what the bad config for fault F1 turns on): a timeout is treated as
            # success, but the order is never saved or queued, and no error is logged.
            metrics.inc("payments_ok")
            return _respond(order.order_id, "ok")
        for _ in range(settings.get("payment_retries")):    # healthy policy: retry, then give up
            result = payment.charge(order.order_id, order.amount)
            if result != "timeout":
                break
            metrics.inc("payment_timeouts")

    if result != "ok":      # declined, or still timing out: tell the customer honestly
        metrics.inc("payments_failed")
        return _respond(order.order_id, "payment_failed", 503)

    metrics.inc("payments_ok")
    orders.save_order(o)
    return _respond(order.order_id, "ok")


@app.get("/health")
def health():
    """Liveness only: 'the process is up'. Says nothing about whether the shop is doing its job."""
    return {"status": "ok", "uptime_s": round(time.time() - START, 1)}


@app.get("/metrics")
def get_metrics():
    return {**metrics.snapshot(), **worker.stats(), "sync": sync.stats()}


# ---- Admin endpoints: the ONLY things the recovery agent is allowed to do or see ----
@app.get("/admin/config")
def admin_config():
    """Read-only: the shop's live config next to its last-known-good config."""
    return settings.view()


@app.post("/admin/restart_worker")
def admin_restart_worker():
    """Start a fresh worker, retire the stuck one, park its unfinished orders."""
    return worker.restart()


@app.post("/admin/requeue_stuck")
def admin_requeue_stuck():
    """Put parked orders back on the queue."""
    return worker.requeue_parked()


@app.post("/admin/rollback_config")
def admin_rollback_config():
    """Restore the shop's last-known-good config."""
    return settings.rollback()


@app.post("/admin/replay_lost_orders")
def admin_replay_lost_orders():
    """Replay orders that were acknowledged but never saved (never duplicates)."""
    return orders.replay_lost_orders()


@app.post("/admin/requeue_unprocessed")
def admin_requeue_unprocessed():
    """Re-queue saved orders that never got processed (dropped from the queue / dead-lettered)."""
    return orders.requeue_unprocessed()


@app.post("/admin/resync_replica")
def admin_resync_replica():
    """Run an inventory sync right now (with the shop's current sync settings)."""
    return sync.resync()
