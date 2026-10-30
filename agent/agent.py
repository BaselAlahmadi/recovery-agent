"""The agent loop: investigate -> diagnose -> act -> verify -> (escalate)."""
import json
import os
import re
import time

import anthropic

from agent import invariants, tools

MODEL = os.getenv("AGENT_MODEL", "claude-haiku-5-5")
MAX_TURNS = 14          # LLM calls
MAX_ACTIONS = 6         # retry budget: after this many actions, only escalate is allowed
MIN_CONFIDENCE = 0.5    # the agent must be at least this sure to act
VERIFY_WAIT_S = 5       # seconds to wait after an action before re-checking

SYSTEM = """You are the on-call engineer for a small e-commerce shop (checkout+payments, order queue+worker, inventory sync).
Failures are SILENT: no crashes, no error logs, /health stays ok. Judge health by the invariant checks. Act only on FAIL lines: small gaps on 'ok' lines are normal in-flight noise.
You get an automatic situation report first. If all invariants pass and you took no actions, call no_incident. Otherwise find the root cause (get_metrics, read_logs, get_shop_config), take the smallest safe action with a reason and confidence, and read the verification returned after each action. Fix the CAUSE first (rollback_config, restart_worker), then repair the DAMAGE it did (replay_lost_orders, requeue_unprocessed, resync_replica, requeue_stuck). Several faults can be active at once: keep going until all invariants pass, then call resolve listing every root-cause category you fixed.
Escalate instead of retrying if the cause is outside the shop's control (e.g. payment provider down while the config is already last-known-good) or no allowed action helps. Never repeat an action that did not help; never guess. A stuck worker shows as old oldest_in_progress_age and stale heartbeat; its log has 'started' without 'finished'. Be brief."""


def clean(text, limit=300):
    """Make model-written text safe for the report: cut off any stray XML/tag-like junk,
    collapse whitespace, limit length."""
    text = " ".join(re.split(r"</?[A-Za-z_]", str(text or ""))[0].split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def categories(values):
    """Keep only valid root-cause categories (deduplicated, in order); default to unknown."""
    if isinstance(values, str):
        values = [values]
    out = []
    for v in values or []:
        if v in tools.ROOT_CAUSES and v not in out:
            out.append(v)
    return out or ["unknown"]


def _cached(tool_list):
    """Mark the end of the tool list as cacheable (system prompt + tools are identical every turn)."""
    return tool_list[:-1] + [{**tool_list[-1], "cache_control": {"type": "ephemeral"}}]


class Agent:
    def __init__(self, verify=True):
        self.client = anthropic.Anthropic()
        self.verify = verify          # switch for the "no verify step" ablation later
        self.rec = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "model": MODEL, "symptoms": None,
                    "evidence": [], "actions": [], "verification": None, "outcome": None,
                    "root_cause_categories": [], "root_cause_detail": None, "next_steps": None,
                    "summary": None, "tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cache_write": 0, "turns": 0}

    def _check(self):
        return invariants.run_checks(tools.fetch_metrics)

    def _evidence(self, tool, args, text):
        self.rec["evidence"].append({"tool": tool, "args": args, "result": text})

    def _situation_report(self):
        """Like a pager alert with context: collected by code so the LLM needs fewer turns."""
        checks = invariants.summarize(self._check())
        self.rec["symptoms"] = checks
        metrics = tools.metrics_text(tools.fetch_metrics())
        diff = json.dumps(json.loads(tools.fetch_config())["differs_from_last_known_good"])
        shop_log = tools.read_logs("shop", 5)
        self._evidence("get_metrics", {}, metrics)
        self._evidence("get_shop_config", {}, f"differs_from_last_known_good: {diff}")
        self._evidence("read_logs", {"component": "shop", "n": 5}, shop_log)
        return (f"Situation report (collected automatically):\n{checks}\nmetrics: {metrics}\n"
                f"config differing from last-known-good: {diff}\nrecent shop log:\n{shop_log}")

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
            next_steps = clean(args.get("suggested_next_steps"), 600)
            if not next_steps:      # a human needs to know what to do next
                return "REFUSED: escalate needs suggested_next_steps for the human.", False
            self.rec.update(outcome="ESCALATED", root_cause_categories=categories(args.get("root_cause_categories")),
                            root_cause_detail=clean(args.get("root_cause_detail")),
                            next_steps=next_steps, summary=clean(args.get("reason"), 600))
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
        self.rec.update(outcome="RESOLVED", root_cause_categories=categories(args.get("root_cause_categories")),
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
        elif name == "get_metrics":
            text = tools.metrics_text(tools.fetch_metrics())
        elif name == "check_health":
            text = str(tools.fetch_health())
        elif name == "get_shop_config":
            text = tools.fetch_config()
        elif name == "read_logs":
            text = tools.read_logs(args.get("component", ""), args.get("n", 6))
        else:
            return f"unknown tool '{name}' (not in allowlist)", False
        self._evidence(name, args, text)
        return text, False

    # ---- main loop ----
    def run(self):
        messages = [{"role": "user", "content": self._situation_report()}]
        system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
        tool_defs = _cached(tools.TOOLS)
        for _ in range(MAX_TURNS):
            resp = self.client.messages.create(model=MODEL, max_tokens=600, system=system,
                                               tools=tool_defs, messages=messages)
            u = resp.usage
            self.rec["turns"] += 1
            self.rec["tokens_in"] += u.input_tokens
            self.rec["tokens_out"] += u.output_tokens
            self.rec["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
            self.rec["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
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
            self.rec.update(outcome="ESCALATED", root_cause_categories=["unknown"],
                            summary="Automatic escalation: turn budget exhausted without resolution.")
        self.rec["final_checks"] = invariants.summarize(self._check())
        return self.rec
