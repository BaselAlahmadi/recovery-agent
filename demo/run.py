"""Demo mode: watch Vitals work, step by step (made for screen recording).

  python -m demo --method hybrid            rules first, the AI only when needed (the full system)
  python -m demo --method rules_only        fixed rules only, no AI
  python -m demo --method agent             the AI alone
  options: --pause 0.6  (seconds between lines, for recording)   --no-color

This file only PRINTS. It wraps the existing functions (print, then call the original unchanged), so it can
only show what the frozen agent / rules / hybrid really do. It changes no decision and no action.
"""
import argparse
import json
import os
import sys
import textwrap
import time

from dotenv import load_dotenv

load_dotenv()

from agent import invariants, report, tools  # noqa: E402  (needs .env loaded first)
from agent.agent import Agent  # noqa: E402
from eval import hybrid, methods, scoring  # noqa: E402

WIDTH = 100
ctx = {"who": "rules", "rules_ran": False, "reason": "", "step": 0, "ai_steps_open": False, "n_actions": 0}
opts = {"pause": 0.4, "color": True}


# ---------------- pure helpers (unit-tested) ----------------
def short(text, n=WIDTH - 12):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3] + "..."


def failing_lines(text):
    """The FAIL lines of an invariants summary (the one-line-per-check text the agent sees)."""
    return [l[5:].strip() for l in str(text).splitlines() if l.startswith("FAIL")]


def split_verification(text):
    """From an action result text, return (action_result_line, verification_status, failing_lines)."""
    if "verification after" not in text:
        return text.splitlines()[0] if text else "", None, []
    head, _, ver = text.partition("verification after")
    status = ver.splitlines()[1] if len(ver.splitlines()) > 1 else ""
    return head.replace("action result:", "").strip(), status.strip(), failing_lines(ver)


# ---------------- printing ----------------
try:
    import colorama
    colorama.just_fix_windows_console()
    from colorama import Fore, Style
except ImportError:                                  # colours are optional
    Fore = Style = None


def paint(text, color=None, bold=False):
    if not opts["color"] or Fore is None:
        return text
    return (Style.BRIGHT if bold else "") + (getattr(Fore, color.upper()) if color else "") + text + Style.RESET_ALL


def say(text="", indent=2, color=None, bold=False):
    for line in textwrap.wrap(str(text), WIDTH - indent, subsequent_indent="  ") or [""]:
        print(" " * indent + paint(line, color, bold))
    sys.stdout.flush()
    time.sleep(opts["pause"])


def step(title):
    ctx["step"] += 1
    print()
    print(paint(f"STEP {ctx['step']}  {title}", "cyan", bold=True))
    print(paint("-" * WIDTH, "cyan"))
    sys.stdout.flush()
    time.sleep(opts["pause"])


def say_marked(mark, color, rest):
    """A line that starts with a coloured marker. Wrap the PLAIN text first, then colour the marker, so the
    invisible colour codes never count toward the line width."""
    lines = textwrap.wrap(f"{mark} {rest}", WIDTH - 2, subsequent_indent="         ")
    lines[0] = lines[0].replace(mark, paint(mark, color, True), 1)
    for line in lines:
        print("  " + line)
    sys.stdout.flush()
    time.sleep(opts["pause"])


def show_checks(checks):
    for c in checks:
        mark, color = ("[ OK ]", "green") if c["ok"] else ("[FAIL]", "red")
        detail = short(c["detail"], 62) if c["ok"] else " ".join(c["detail"].split())   # failures are shown in full
        say_marked(mark, color, f"{c['name']:<24} {detail}")
    bad = [c["name"] for c in checks if not c["ok"]]
    say(("All vital signs pass." if not bad else f"{len(bad)} vital sign(s) failing: {', '.join(bad)}"),
        2, "green" if not bad else "red", bold=True)


def vitals():
    return invariants.run_checks(tools.fetch_metrics)


# ---------------- wrapping the frozen code (print only) ----------------
def install_wrappers():
    orig_call_action = tools.call_action

    def call_action(name):
        result = orig_call_action(name)
        if ctx["who"] == "rules":
            say_marked("RULE ACTION", "yellow", f"{name}  ->  {short(result, 60)}")
        return result
    tools.call_action = call_action

    orig_rules = methods.rules_only

    def rules_only():
        ctx["rules_ran"] = True
        ctx["who"] = "rules"
        step("RULES ACT  (fixed if-then rules, no AI)")
        rec = orig_rules()
        names = [a["action"] for a in rec["actions"]]
        say(f"rules finished. actions taken: {', '.join(names) if names else 'none'}", 2)
        say("re-checking the vital signs:", 2)
        show_checks(vitals())
        return rec
    methods.rules_only = rules_only

    orig_agent_run = Agent.run

    def agent_run(self):
        ctx["who"] = "ai"
        step("THE AI TAKES OVER")
        say("why: " + ctx["reason"], 2, "yellow", bold=True)
        return orig_agent_run(self)
    Agent.run = agent_run

    orig_briefing = Agent._situation_report

    def situation_report(self):
        text = orig_briefing(self)
        say("the AI is first handed an automatic briefing:", 2)
        bad = failing_lines(self.rec.get("symptoms") or "")
        say("- vital signs: " + (f"{len(bad)} failing ({', '.join(l.split(':')[0] for l in bad)})" if bad else "all pass"), 4)
        for e in self.rec["evidence"]:
            if e["tool"] == "get_metrics":
                say("- the live metrics", 4)
            elif e["tool"] == "get_shop_config":
                say("- " + short(e["result"].replace("differs_from_last_known_good:", "config vs last-known-good, differs:"), 80), 4)
            elif e["tool"] == "read_logs":
                last = (e["result"].splitlines() or [""])[-1]
                say("- the last shop-log lines, newest: " + short(last, 60), 4)
        return text
    Agent._situation_report = situation_report

    orig_dispatch = Agent._dispatch

    def dispatch(self, name, args):
        text, finished = orig_dispatch(self, name, args)
        ai_event(name, args, text, finished)
        return text, finished
    Agent._dispatch = dispatch


def open_investigation():
    if not ctx["ai_steps_open"]:
        ctx["ai_steps_open"] = True
        step("THE AI RE-CHECKS BEFORE FINISHING" if ctx["n_actions"] else
             "THE AI INVESTIGATES FURTHER  (read-only tools: logs, metrics, config)")


def ai_event(name, args, text, finished):
    if name == "read_logs":
        open_investigation()
        say(f"looked at: the '{args.get('component')}' log (last {args.get('n', 6)} lines)", 2)
    elif name == "get_metrics":
        open_investigation()
        say("looked at: the live metrics", 2)
    elif name == "check_health":
        open_investigation()
        say("looked at: /health  (it only says the process is up)", 2)
    elif name == "get_shop_config":
        open_investigation()
        try:
            diff = json.loads(text)["differs_from_last_known_good"]
        except (ValueError, KeyError):
            diff = {}
        say("looked at: shop config vs last-known-good  ->  " +
            (", ".join(f"{k}: {v[0]!r} -> {v[1]!r}" for k, v in diff.items()) if diff else "no changes"), 2)
    elif name == "check_invariants":
        open_investigation()
        bad = failing_lines(text)
        say("re-ran the vital signs  ->  " + ("all pass" if not bad else f"{len(bad)} failing"), 2)
    elif name in tools.ACTIONS:
        ctx["ai_steps_open"] = False
        ctx["n_actions"] += 1
        step(f"AI ACTION {ctx['n_actions']}: {name}")
        if text.startswith("REFUSED"):
            say("refused by the safety rails: " + short(text), 2, "red")
            return
        say(f"why:        {args.get('reason', '')}", 2)
        say(f"confidence: {args.get('confidence')}", 2)
        result, status, bad = split_verification(text)
        say(f"result:     {short(result, 80)}", 2)
        if status is not None:
            say("verification (waited 5 s, then re-checked the vital signs):", 2)
            say(status, 4, "green" if "ALL INVARIANTS OK" in status else "red", bold=True)
            for l in bad:
                say(short(l), 4, "red")
    elif name in ("resolve", "no_incident", "escalate") and not finished:
        say("the AI tried to finish, but the safety rails refused: " + short(text), 2, "red")


# ---------------- main flow ----------------
def rule_check_step(method):
    step("RULE CHECK")
    failing = {c["name"] for c in vitals() if not c["ok"]}
    if method == "agent":
        ctx["reason"] = "AI-only mode (no rules)."
        say("(AI-only mode: no rules are used.)", 2)
        return
    config_changed = bool(failing) and bool(json.loads(tools.fetch_config())["differs_from_last_known_good"])
    if failing:
        say("config differs from last-known-good: " + ("yes" if config_changed else "no"), 2)
    matched = hybrid.matching_rules(failing, config_changed) if failing else ["all_clear"]
    if matched == ["all_clear"]:
        say("all-clear rule matches: nothing is failing.", 2, "green", bold=True)
    elif len(matched) == 1:
        say(f"exactly one rule matches: '{matched[0]}'  ->  the rules will act first.", 2, "green", bold=True)
        ctx["reason"] = f"the rules acted ('{matched[0]}') but the vital signs are still failing."
    elif not matched:
        say("no rule matches what is failing" + ("  ->  handing to the AI." if method == "hybrid"
                                                  else "  ->  the rules have nothing to do."), 2, "yellow", bold=True)
        ctx["reason"] = "no rule matches what is failing."
    else:
        say(f"several rules match ({' + '.join(matched)}) and may conflict" +
            ("  ->  handing to the AI." if method == "hybrid" else "."), 2, "yellow", bold=True)
        ctx["reason"] = "several rules match at once (more than one fault)."
    if method == "rules_only":
        say("(rules-only mode: the AI is never called.)", 2)


def final_step(method, rec, seconds):
    step("OUTCOME")
    outcome = rec["outcome"]
    color = {"RESOLVED": "green", "NO_INCIDENT": "green", "ESCALATED": "yellow"}.get(outcome, None)
    say(f"{outcome.replace('_', ' ')}", 2, color, bold=True)
    cats = rec.get("root_cause_categories") or []
    say("root causes: " + (", ".join(cats) if cats else "none named"), 2)
    if rec.get("root_cause_detail"):
        say("detail: " + rec["root_cause_detail"], 2)
    names = [a["action"] for a in rec["actions"]]
    say("actions taken: " + (" -> ".join(names) if names else "none"), 2)
    handled = {"hybrid": ("rules only (no AI call)" if not rec.get("handover") else "rules + AI"),
               "agent": "AI", "rules_only": "rules only (no AI call)"}[method]
    if method == "hybrid" and rec.get("handover") and not ctx["rules_ran"]:
        handled = "AI (no rule matched or several conflicted)"
    say("handled by: " + handled, 2)
    say("final vital signs:", 2)
    final_checks = vitals()
    show_checks(final_checks)
    if outcome != "ESCALATED" and not all(c["ok"] for c in final_checks):
        say("WARNING: it reported " + outcome.replace("_", " ") + " but the shop is still broken (see FAIL above).",
            2, "red", bold=True)
    if outcome == "ESCALATED":
        say("for a human: " + (rec.get("next_steps") or rec.get("summary") or "-"), 2, "yellow")
    tokens = rec["tokens_in"] + rec["cache_read"] + rec["cache_write"] + rec["tokens_out"]
    cost = scoring.cost_usd(rec["tokens_in"], rec["cache_read"], rec["cache_write"], rec["tokens_out"])
    say(f"time: {seconds:.0f} s   AI tokens: {tokens:,}   est. cost: ${cost:.4f}", 2)
    if "evidence" in rec:
        path = report.write({**rec, "final_checks": rec.get("final_checks", "")})
        say(f"incident report: {path}", 2, "cyan", bold=True)
    else:
        say("(no AI was used, so no incident report was written)", 2)


def main():
    ap = argparse.ArgumentParser(prog="python -m demo")
    ap.add_argument("--method", choices=["hybrid", "agent", "rules_only"], default="hybrid")
    ap.add_argument("--pause", type=float, default=0.4, help="seconds between lines (use ~0.6 when recording)")
    ap.add_argument("--no-color", action="store_true")
    a = ap.parse_args()
    opts["pause"], opts["color"] = a.pause, not (a.no_color or os.getenv("NO_COLOR"))
    try:
        tools.fetch_health()
    except Exception:
        sys.exit(f"Shop not reachable at {tools.SHOP_URL}. Start it first (see demo/DEMO.md).")

    print(paint(f"\nVITALS  -  demo mode  -  method: {a.method}", "magenta", bold=True))
    t0 = time.time()
    step("VITAL SIGNS  (is the shop actually doing its job?)")
    show_checks(vitals())
    rule_check_step(a.method)
    install_wrappers()
    rec = {"hybrid": hybrid.run, "agent": lambda: Agent().run(), "rules_only": methods.rules_only}[a.method]()
    final_step(a.method, rec, time.time() - t0)
    print()


if __name__ == "__main__":
    main()
