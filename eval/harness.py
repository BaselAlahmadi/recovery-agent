"""Run ONE eval job (scenario x method x repetition) in its own isolated shop.

  python -m eval.harness <scenario_id> <method> <rep> <port> <out_dir>

Timeline: t=0 traffic starts -> faults are injected at their at_s -> the method runs at agent_at_s ->
traffic + faults stay on for hold_s -> INDEPENDENT checks (the harness, not the method) -> stop traffic,
clear faults, let the queue drain -> audit the raw request log and database for lost/duplicated orders.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval import scoring  # noqa: E402  (pure helpers)


def load_scenario(scenario_id):
    data = json.loads((ROOT / "eval" / "scenarios.json").read_text())
    for key in ("dev", "heldout"):
        for s in data[key]:
            if s["id"] == scenario_id:
                return {**s, "set": key, "hold_s": data["meta"]["hold_s"]}
    raise SystemExit(f"unknown scenario {scenario_id}")


def agent_version():
    """Short hash of the agent's source, stored with every result to prove which version ran."""
    h = hashlib.sha256()
    for p in sorted((ROOT / "agent").glob("*.py")):
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


def audit(state, fetch_metrics):
    """Count lost / duplicated orders from the raw request log + DB (independent of the agent)."""
    resp = {}
    for line in (state / "logs" / "requests.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r["event"] == "response":
            resp[r["order_id"]] = r["status"]
    db = sqlite3.connect(state / "data" / "shop.db")
    saved = {x[0] for x in db.execute("SELECT order_id FROM orders")}
    ship = db.execute("SELECT order_id, COUNT(*) FROM fulfillment WHERE step='ship' GROUP BY order_id").fetchall()
    told_ok_not_saved = len({o for o, s in resp.items() if s == "ok"} - saved)
    unaccounted = []
    for _ in range(3):      # the worker may still be moving orders; take the best of 3 readings
        m = fetch_metrics()
        waiting = m["pending"] + m["in_progress"] + m["parked"] + m["dead_letter"]
        unaccounted.append(max(0, len(saved) - len(ship) - waiting))
        time.sleep(1)
    return {"told_ok_not_saved": told_ok_not_saved, "saved_unaccounted": min(unaccounted),
            "orders_unfulfilled": max(0, len(saved) - len(ship)),
            "duplicate_shipments": sum(1 for _, c in ship if c > 1), "orders_saved": len(saved)}


def run_job(sc, method, rep, port, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    state = out_dir / "state"
    shutil.rmtree(state, ignore_errors=True)
    state.mkdir()
    seed = sc["seed"] + 100 * rep
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "SHOP_STATE_DIR": str(state), "SHOP_SEED": str(seed), "SHOP_URL": url,
           "AGENT_REPORT_DIR": str(out_dir), "PYTHONUNBUFFERED": "1"}
    # agent.tools reads these variables when it is first imported, so set them BEFORE importing it
    os.environ.update({k: env[k] for k in ("SHOP_STATE_DIR", "SHOP_SEED", "SHOP_URL", "AGENT_REPORT_DIR")})
    import requests
    from agent import invariants
    from eval import methods

    py = sys.executable
    faults = [f["id"] for f in sc["faults"]]
    procs = []

    def spawn(*args, log):
        p = subprocess.Popen([py, *args], env=env, cwd=ROOT, stdout=open(out_dir / log, "w"), stderr=subprocess.STDOUT)
        procs.append(p)
        return p

    def fetch():
        return requests.get(f"{url}/metrics", timeout=5).json()

    def chaos(*args):
        subprocess.run([py, "-m", "chaos", *args], env=env, cwd=ROOT, check=True, capture_output=True)

    t_start = time.time()
    try:
        shop = spawn("-m", "uvicorn", "shop.app:app", "--port", str(port), log="shop.out")
        for _ in range(60):
            try:
                requests.get(f"{url}/health", timeout=1)
                break
            except requests.RequestException:
                time.sleep(0.5)
        else:
            raise RuntimeError("shop did not start")
        traffic = spawn("-m", "shop.traffic", "--url", url, "--rate", str(sc["traffic_rate"]),
                        "--duration", "0", "--seed", str(seed), log="traffic.out")
        t0 = time.time()

        def sleep_until(t):
            time.sleep(max(0, t0 + t - time.time()))

        for f in sorted(sc["faults"], key=lambda f: f["at_s"]):
            sleep_until(f["at_s"])
            chaos("on", f["id"], "--rate", str(f["rate"]))
        sleep_until(sc["agent_at_s"])

        # ---- the method under test ----
        rec = methods.run(method)
        if method in ("agent", "no_invariants", "no_verify"):
            from agent import report
            report.write({**rec, "final_checks": rec.get("final_checks", "")})

        # ---- hold under load with faults still on, then check independently ----
        time.sleep(sc["hold_s"])
        samples = [invariants.run_checks(fetch) for _ in range(3)]
        passes = [scoring.recovered(s, faults) for s in samples]
        is_recovered = sum(passes) >= 2
        failing = sorted({c["name"] for s in samples for c in s if not c["ok"]})

        # ---- stop traffic, clear faults, drain, audit ----
        traffic.terminate()
        time.sleep(1.5)
        chaos("clear")
        for _ in range(25):
            m = fetch()
            if m["pending"] + m["in_progress"] == 0:
                break
            time.sleep(2)
        a = audit(state, fetch)
    except Exception:
        return {"job_id": out_dir.name, "scenario": sc["id"], "method": method, "rep": rep,
                "error": traceback.format_exc()[-600:], "wall_s": round(time.time() - t_start, 1)}
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()

    names = [x["action"] for x in rec["actions"]]
    outcome_ok = rec["outcome"] == sc["expected_outcome"]
    return {
        "job_id": out_dir.name, "set": sc["set"], "scenario": sc["id"], "method": method, "rep": rep, "seed": seed,
        "agent_version": agent_version(), "expected_outcome": sc["expected_outcome"], "outcome": rec["outcome"],
        "outcome_correct": int(outcome_ok), "recovered": int(is_recovered), "success": int(outcome_ok and is_recovered),
        "false_claim": int(rec["outcome"] in ("RESOLVED", "NO_INCIDENT") and not is_recovered),
        "expected_root_causes": ",".join(sc["expected_root_causes"]), "root_causes": ",".join(rec["root_cause_categories"]),
        "root_cause_f1": scoring.root_cause_f1(sc["expected_root_causes"], rec["root_cause_categories"]),
        "agent_seconds": rec["agent_seconds"], "time_to_recover_s": rec["agent_seconds"] if is_recovered else None,
        "n_actions": len(names), "actions": ",".join(names), "n_unnecessary": scoring.count_unnecessary(names, faults),
        "duplicate_shipments": a["duplicate_shipments"], "orders_lost": a["told_ok_not_saved"] + a["saved_unaccounted"],
        "told_ok_not_saved": a["told_ok_not_saved"], "saved_unaccounted": a["saved_unaccounted"],
        "orders_unfulfilled": a["orders_unfulfilled"], "orders_saved": a["orders_saved"],
        "turns": rec["turns"], "tokens_in": rec["tokens_in"], "cache_read": rec["cache_read"],
        "cache_write": rec["cache_write"], "tokens_out": rec["tokens_out"],
        "cost_usd": scoring.cost_usd(rec["tokens_in"], rec["cache_read"], rec["cache_write"], rec["tokens_out"]),
        "still_failing": ",".join(failing), "wall_s": round(time.time() - t_start, 1), "error": "",
    }


def main():
    scenario_id, method, rep, port, out_dir = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), Path(sys.argv[5])
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    result = run_job(load_scenario(scenario_id), method, rep, port, out_dir)
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result.get(k) for k in ("job_id", "outcome", "success", "orders_lost", "cost_usd", "error")}))


if __name__ == "__main__":
    main()
