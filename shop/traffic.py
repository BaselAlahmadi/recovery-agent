"""Traffic generator. Usage: python -m shop.traffic --rate 5 --duration 30 --seed 1"""
import argparse
import random
import time

import requests

from shop.db import SKUS


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--rate", type=float, default=5, help="orders per second")
    p.add_argument("--duration", type=float, default=30, help="seconds (0 = run forever)")
    p.add_argument("--seed", type=int, default=1, help="same seed -> same orders")
    args = p.parse_args()

    rng = random.Random(args.seed)
    session = requests.Session()
    sent = ok = 0
    end = time.time() + args.duration if args.duration else float("inf")

    while time.time() < end:
        sent += 1
        order = {
            "order_id": f"o-{args.seed}-{sent}",
            "sku": rng.choice(SKUS),
            "qty": rng.randint(1, 3),
            "amount": round(rng.uniform(5, 200), 2),
        }
        try:
            if session.post(f"{args.url}/checkout", json=order, timeout=5).ok:
                ok += 1
        except requests.RequestException:
            pass  # shop down or slow: just keep going
        time.sleep(rng.expovariate(args.rate))  # random gaps -> bursty, realistic traffic

    print(f"sent={sent} http_ok={ok}")


if __name__ == "__main__":
    main()
