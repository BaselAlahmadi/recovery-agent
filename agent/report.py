"""Write the markdown incident report for one agent run."""
import time
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def write(rec):
    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / f"incident_{time.strftime('%Y%m%d_%H%M%S')}.md"
    L = [f"# Incident report: {rec['outcome'].replace('_', ' ')}", "",
         f"- Started: {rec['started']}", f"- Model: {rec['model']}",
         f"- LLM turns: {rec['turns']} | tokens in/out: {rec['tokens_in']}/{rec['tokens_out']}", "",
         "## Symptoms (first invariant check)", "```", rec["symptoms"] or "(none recorded)", "```", "",
         "## Evidence gathered"]
    for e in rec["evidence"]:
        L += [f"**{e['tool']}** {e['args'] or ''}", "```", e["result"][:700], "```"]
    L += ["", "## Root cause",
          f"- Category: `{rec['root_cause_category'] or 'none'}`",
          f"- Detail: {rec['root_cause_detail'] or '-'}", "", "## Actions taken"]
    if not rec["actions"]:
        L.append("(none)")
    for i, a in enumerate(rec["actions"], 1):
        L += [f"{i}. `{a['action']}` (confidence {a['confidence']}): {a['reason']}", f"   - result: {a['result']}"]
    L += ["", "## Verification result", "```", rec["final_checks"], "```", "", "## Summary", rec["summary"] or "-"]
    if rec["next_steps"]:
        L += ["", "## Suggested next steps for a human", rec["next_steps"]]
    path.write_text("\n".join(L), encoding="utf-8")
    return path
