"""The agent loop: investigate -> diagnose -> act -> verify -> (escalate)."""
import os
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
Method: 1) call check_invariants. 2) If something fails, investigate with get_metrics and read_logs until you know the root cause. 3) Take the smallest safe action; give a reason and confidence. 4) After each action the system waits and re-checks invariants for you; read that result. 5) When all invariants pass call resolve. If you cannot fix it safely, are unsure, or the budget runs out, call escalate. Never repeat an action that did not help; never guess.
Hints: a stuck worker shows as old oldest_in_progress_age / stale heartbeat with pending growing; a worker log 'started' with no 'finished' marks the stuck order. Be brief."""


class Agent:
    def __init__(self, verify=True):
        self.client = anthropic.Anthropic()
        self.verify = verify          # switch for the "no verify step" ablation later
        self.rec = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "model": MODEL, "symptoms": None,
                    "evidence": [], "actions": [], "verification": None, "outcome": None, "root_cause": None,
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
        entry = {"action": name, "reason": args.get("reason", ""), "confidence": args.get("confidence"), "result": result}
        self.rec["actions"].append(entry)
        if not self.verify:
            return f"action result: {result}"
        time.sleep(VERIFY_WAIT_S)
        checks = self._check()
        entry["verification"] = invariants.summarize(checks)
        self.rec["verification"] = entry["verification"]
        return f"action result: {result}\nverification after {VERIFY_WAIT_S}s:\n{entry['verification']}"

    def _dispatch(self, name, args):
        """Returns (text_for_model, finished?)."""
        if name == "check_invariants":
            text = invariants.summarize(self._check())
            if self.rec["symptoms"] is None:
                self.rec["symptoms"] = text      # the first look = the symptoms
        elif name == "get_metrics":
            text = tools.metrics_text(tools.fetch_metrics())
        elif name == "check_health":
            text = str(tools.fetch_health())
        elif name == "read_logs":
            text = tools.read_logs(args.get("component", ""), args.get("n", 8))
        elif name in tools.ACTIONS:
            return self._action(name, args), False
        elif name == "resolve":
            checks = self._check()
            if not invariants.all_ok(checks):
                return "REFUSED: invariants still failing:\n" + invariants.summarize(checks), False
            self.rec.update(outcome="RESOLVED", root_cause=args.get("root_cause"), summary=args.get("summary"),
                            verification=invariants.summarize(checks))
            return "ok", True
        elif name == "escalate":
            self.rec.update(outcome="ESCALATED", root_cause=args.get("root_cause_guess"),
                            summary=f"{args.get('reason')} | next steps: {args.get('suggested_next_steps', '-')}")
            return "ok", True
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
                results = [{"type": "text", "text": "Call a tool. Finish with resolve or escalate."}]
            messages.append({"role": "user", "content": results})

        if self.rec["outcome"] is None:       # budget ran out: never loop forever, hand over to a human
            self.rec.update(outcome="ESCALATED", summary="Automatic escalation: turn budget exhausted without resolution.")
        self.rec["final_checks"] = invariants.summarize(self._check())
        return self.rec
