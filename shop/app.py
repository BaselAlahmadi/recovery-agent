"""The shop's web API. Run with: python -m uvicorn shop.app:app --port 8000"""
import time

from fastapi import FastAPI
from pydantic import BaseModel

from shop import db, metrics, payment, sync, worker
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
    db.init_db()
    worker.start()
    sync.start()
    log("shop", "started")


@app.post("/checkout")
def checkout(order: Order):
    metrics.inc("checkout_requests")
    o = order.model_dump()
    # request log: every request is recorded first, so lost orders can be replayed later
    log("requests", "checkout", **o)

    result = payment.charge(order.order_id, order.amount)
    if result == "declined":
        metrics.inc("payments_failed")
        return {"status": "payment_failed", "order_id": order.order_id}
    if result == "timeout":
        # BUG (this is what fault F1 triggers): a timeout is treated as success, but the
        # order is never saved or queued, and no error is logged.
        metrics.inc("payments_ok")
        return {"status": "ok", "order_id": order.order_id}
    metrics.inc("payments_ok")

    with db.connect(db.SOURCE_DB) as c:
        c.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", (order.order_id, order.sku, order.qty, order.amount, time.time()))
        c.execute("UPDATE inventory SET stock = MAX(stock - ?, 0) WHERE sku = ?", (order.qty, order.sku))
    metrics.inc("orders_saved")
    log("checkout", "order_saved", order_id=order.order_id)

    worker.enqueue(o)
    return {"status": "ok", "order_id": order.order_id}


@app.get("/health")
def health():
    """Liveness only: 'the process is up'. Says nothing about whether the shop is doing its job."""
    return {"status": "ok", "uptime_s": round(time.time() - START, 1)}


@app.get("/metrics")
def get_metrics():
    return {**metrics.snapshot(), **worker.stats(), "sync": sync.stats()}
