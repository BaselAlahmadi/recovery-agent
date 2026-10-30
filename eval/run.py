"""Run many eval jobs in parallel and collect a results CSV.

  python -m eval.run --set dev --methods agent --reps 3
  python -m eval.run --set heldout --methods agent --reps 3
  python -m eval.run --set heldout --methods restart_all rules_only no_invariants no_verify --reps 1

Finished jobs are skipped on re-run (a crash never re-spends money); use --force to redo them.
"""
import argparse
import csv
import json
import queue
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "eval" / "runs"
RESULTS = ROOT / "eval" / "results"
BASE_PORT = 8100
JOB_TIMEOUT_S = 420


def job_dir(set_name, scenario, method, rep):
    return RUNS / set_name / f"{scenario}__{method}__r{rep}"


def collect():
    """Gather every finished result.json into one CSV."""
    rows = [json.loads(p.read_text()) for p in sorted(RUNS.glob("*/*/result.json"))
            if not p.parent.parent.name.startswith("_")]   # _smoke etc. are not results
    rows = [r for r in rows if not r.get("error")]
    if rows:
        RESULTS.mkdir(parents=True, exist_ok=True)
        cols = list(rows[0].keys())
        with open(RESULTS / "results.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["dev", "heldout"], required=True)
    ap.add_argument("--methods", nargs="+", default=["agent"])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", nargs="*", help="only these scenario ids")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    scenarios = json.loads((ROOT / "eval" / "scenarios.json").read_text())[a.set]
    jobs = [(s["id"], m, r) for s in scenarios if not a.only or s["id"] in a.only
            for m in a.methods for r in range(1, a.reps + 1)]
    ports = queue.Queue()
    for i in range(a.workers):
        ports.put(BASE_PORT + i)

    def run(job):
        scenario, method, rep = job
        d = job_dir(a.set, scenario, method, rep)
        res = d / "result.json"
        if res.exists() and not a.force and not json.loads(res.read_text()).get("error"):
            return f"skip  {d.name}"
        port = ports.get()
        try:
            subprocess.run([sys.executable, "-m", "eval.harness", scenario, method, str(rep), str(port), str(d)],
                           cwd=ROOT, timeout=JOB_TIMEOUT_S, capture_output=True)
        except subprocess.TimeoutExpired:
            d.mkdir(parents=True, exist_ok=True)
            (d / "result.json").write_text(json.dumps({"job_id": d.name, "error": "job timed out"}))
        finally:
            ports.put(port)
        r = json.loads(res.read_text()) if res.exists() else {"error": "no result written"}
        if r.get("error"):
            return f"ERROR {d.name}: {r['error'][-200:]}"
        return (f"done  {d.name}: outcome={r['outcome']} (expected {r['expected_outcome']}) recovered={r['recovered']} "
                f"success={r['success']} lost={r['orders_lost']} actions={r['n_actions']} ${r['cost_usd']}")

    print(f"{len(jobs)} jobs, {a.workers} in parallel", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        for line in ex.map(run, jobs):
            print(line, flush=True)
    rows = collect()
    print(f"collected {len(rows)} results -> eval/results/results.csv; total cost ${sum(r['cost_usd'] for r in rows):.3f}")


if __name__ == "__main__":
    main()
