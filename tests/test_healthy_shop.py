"""Healthy-shop test: with NO faults the agent must take no actions and report "no incident".

Needs ANTHROPIC_API_KEY. Starts its own shop on port 8765 and clears all chaos faults first.
Run only this test:  python -m pytest tests/test_healthy_shop.py
Skip it:             python -m pytest -m "not llm"
"""
import os
import subprocess
import sys
import time

import pytest
import requests
from dotenv import load_dotenv

load_dotenv()
pytestmark = pytest.mark.llm
PORT = 8765
URL = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def clean_shop():
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    subprocess.run([sys.executable, "-m", "chaos", "clear"], check=True)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "shop.app:app", "--port", str(PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                requests.get(f"{URL}/health", timeout=1)
                break
            except requests.RequestException:
                time.sleep(0.5)
        else:
            pytest.fail("shop did not start")
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_agent_reports_no_incident_on_a_healthy_shop(clean_shop):
    for i in range(30):   # light, normal traffic
        requests.post(f"{URL}/checkout", json={"order_id": f"t-{i}", "sku": "SKU-001", "qty": 1, "amount": 10.0}, timeout=5)
    time.sleep(6)         # let the worker finish and the sync job run

    from agent import tools
    from agent.agent import Agent
    tools.SHOP_URL = URL  # point the agent at the test shop

    rec = Agent().run()
    assert rec["actions"] == [], f"agent acted on a healthy shop: {rec['actions']}"
    assert rec["outcome"] == "NO_INCIDENT"
