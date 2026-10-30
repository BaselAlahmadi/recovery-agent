"""The agent loop: investigate -> diagnose -> act -> verify -> (escalate)."""
import os
import re
import time

import anthropic

from agent import invariants, tools

MODEL = os.getenv("AGENT_MODEL", "claude-haiku-5-5")
MAX_TURNS = 12          # LLM calls
MAX_ACTIONS = 4         # retry budget: after this many actions, only escalate is allowed
MIN_CONFIDENCE = 0.5    # the agent must be at least this sure to act
VERIFY_WAIT_S = 5       # seconds to wait after an action before re-checking

SYSTEM = """You are an on-call engineer for a small e-commerce shop (checkout, payments, order queue + worker, inventory sync).
Failures here are SILENT: nothing crashes and logs show no errors. So judge health by the invariant checks, not by errors or /health.
Method: 1) call check_invariants. 2) If everything passes and you have taken no actions, call no_incident. 3) If something fails, investigate (get_metrics, read_logs, get_shop_config) until you know the root cause. 4) Take the smallest safe action; give a reason and confidence. Fix the CAUSE first, then repair the DAMAGE it already did. 5) After each action the system waits and re-checks invariants for you; read that result and continue until they pass. 6) When all invariants pass after your actions, call resolve with a root-cause category. If you cannot fix it safely, are unsure, or the budget runs out, call escalate. Never repeat an action that did not help; never guess.
Separate what the shop controls (its own config and processes) from outside conditions (e.g. the payment provider being flaky): you can only fix the former, so name the former as the root cause.
Hints: a stuck worker shows as old oldest_in_progress_age / stale heartbeat with pending growing; a worker log 'started' with no 'finished' marks the stuck order. Orders that customers were told 'ok' but that are not saved show up as requests_vs_saved failing; a recent bad config change shows in get_shop_config and the shop log. Be brief."""


def clean(text, limit=300):
    """Make model-written text safe for the report: cut off any stray XML/tag-like junk,
    collapse whitespace, limit length."""
    text = re.split(r"</?[A-Za-z_]", str(text or ""))[0]
    return " ".join(text.split())[:limit]


def category(value):
    return value if value in tools.ROOT_CAUSES else "unknown"


class Agent:
    def __init__(self, verify=True):
        self.client = anthropic.Anthropic()
        self.verify = verify          # switch for the "no verify step" ablation later
        self.rec = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "model": MODEL, "symptoms": None,
                    "evidence": [], "actions": [], "verification": None, "outcome": None,
                    "root_cause_category": None, "root_cause_detail": None, "next_steps": None,
                    "summary": None, "tokens_in": 0, "tokens_out": 0, "turns": 0}

    def _check(self):
        return invariants.run_checks(tools.fetch_metrics)

    # ---- tool dispatch ----
    def _action(self, name, args):
        if len(self.rec["actions"]) >= MAX_ACTIONS:
            return "REFUSED: retry budget used up. You must call escalate."
        if float(args.get("confidence", 0)) < MIN_CONFIDENCE:
            return f"REFUSED: confidence below {MIN_CONFIDENCE}. Gather more evidence or escalate."
        result = tools.call_action(name)
        entry = {"action": name, "reason": clean(args.get("reason")), "confidence": args.get("confidence"), "result": result}
        self.rec["actions"].append(entry)
        if not self.verify:
            return f"action result: {result}"
        time.sleep(VERIFY_WAIT_S)
        checks = self._check()
        entry["verification"] = invariants.summarize(checks)
        self.rec["verification"] = entry["verification"]
        return f"action result: {result}\nverification after {VERIFY_WAIT_S}s:\n{entry['verification']}"

    def _finish(self, name, args):
        """Handle resolve / no_incident / escalate. Returns (text, finished?)."""
        if name == "escalate":
            self.rec.update(outcome="ESCALATED", root_cause_category=category(args.get("root_cause_category")),
                            root_cause_detail=clean(args.get("root_cause_detail")),
                            next_steps=clean(args.get("suggested_next_steps")), summary=clean(args.get("reason")))
            return "ok", True
        checks = self._check()
        if not invariants.all_ok(checks):
            return "REFUSED: invariants still failing:\n" + invariants.summarize(checks), False
        if name == "no_incident":
            if self.rec["actions"]:
                return "REFUSED: you took actions, so call resolve instead.", False
            self.rec.update(outcome="NO_INCIDENT", summary=clean(args.get("summary")), verification=invariants.summarize(checks))
            return "ok", True
        # resolve
        if not self.rec["actions"]:
            return "REFUSED: you took no actions. If nothing is wrong, call no_incident.", False
        self.rec.update(outcome="RESOLVED", root_cause_category=category(args.get("root_cause_category")),
                        root_cause_detail=clean(args.get("root_cause_detail")), summary=clean(args.get("summary")),
                        verification=invariants.summarize(checks))
        return "ok", True

    def _dispatch(self, name, args):
        """Returns (text_for_model, finished?)."""
        if name in ("resolve", "no_incident", "escalate"):
            return self._finish(name, args)
        if name in tools.ACTIONS:
            return self._action(name, args), False
        if name == "check_invariants":
            text = invariants.summarize(self._check())
            if self.rec["symptoms"] is None:
                self.rec["symptoms"] = text      # the first look = the symptoms
        elif name == "get_metrics":
            text = tools.metrics_text(tools.fetch_metrics())
        elif name == "check_health":
            text = str(tools.fetch_health())
        elif name == "get_shop_config":
            text = tools.fetch_config()
        elif name == "read_logs":
            text = tools.read_logs(args.get("component", ""), args.get("n", 8))
        else:
            return f"unknown tool '{name}' (not in allowlist)", False
        self.rec["evidence"].append({"tool": name, "args": args, "result": text})
        return text, False

    # ---- main loop ----
    def run(self):
        messages = [{"role": "user", "content": "Review the shop's health now and fix any problem."}]
        for _ in range(MAX_TURNS):
            resp = self.client.messages.create(model=MODEL, max_tokens=800, system=SYSTEM,
                                               tools=tools.TOOLS, messages=messages)
            self.rec["turns"] += 1
            self.rec["tokens_in"] += resp.usage.input_tokens
            self.rec["tokens_out"] += resp.usage.output_tokens
            messages.append({"role": "assistant", "content": resp.content})

            results, done = [], False
            for block in resp.content:
                if block.type == "tool_use":
                    text, finished = self._dispatch(block.name, block.input)
                    done = done or finished
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": text})
            if done:
                break
            if not results:
                results = [{"type": "text", "text": "Call a tool. Finish with resolve, no_incident or escalate."}]
            messages.append({"role": "user", "content": results})

        if self.rec["outcome"] is None:       # budget ran out: never loop forever, hand over to a human
            self.rec.update(outcome="ESCALATED", root_cause_category="unknown",
                            summary="Automatic escalation: turn budget exhausted without resolution.")
        self.rec["final_checks"] = invariants.summarize(self._check())
        return self.rec
