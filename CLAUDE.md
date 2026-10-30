# Project brief: read this first

## Context
- HUMAIN "Future AI Builders" hackathon, **Challenge 1: Agentic Recovery of a Failing System**.
- Solo participant: Basel. **Deadline: Saturday 31 Oct 2026, 8:00 PM (Riyadh time).**
- Deliverables: a real working demo (3-4 min video), GitHub repo, 8-10 slide PDF, project page write-up.
- Basel must understand and explain every part of this in his presentation. **Keep code simple, readable, and commented. After each step, explain what you did in 2-3 plain-language sentences.** Prefer small steps that are run and verified over big rewrites.

## Judging criteria (from the organizers)
1. **Task performance:** results on unseen / held-out test cases.
2. **Robustness & adaptation:** keeps working when conditions, inputs or requirements change.
3. **Evaluation & iteration:** systematic testing, reproducible improvements, regression checks, proof that each key component helps.
4. **Technical judgment & creativity:** good design decisions and trade-offs; clear value over simpler alternatives.
5. **Engineering quality:** reproducible, inspectable, reliable, maintainable.
6. **Communication:** clear explanation of problem, solution, method, results, decisions.

(Challenge-specific criteria may be added later.)

## The angle (what makes this stand out)
The challenge's own examples are mostly **silent failures**: nothing crashes and no error is logged.
1. Payments that silently drop orders
2. A queue that loses messages under load
3. A sync job that slowly corrupts data
4. A workflow that hangs forever
5. A repair agent that never escalates

Most agents read error logs. Ours checks **whether the system is actually doing its job** (business invariants and reconciliation), then diagnoses, fixes, verifies, and **escalates to a human** when it can't fix something safely.

## Environment
- Windows 10, PowerShell. Python 3.14. Virtual env is at `..\.venv` (already active in the VS Code terminal).
- Installed: fastapi, uvicorn, psutil, requests, anthropic, python-dotenv, pandas, pytest (and more).
- **No Docker.** Everything runs as plain Python processes/threads.
- LLM: Anthropic API, key in `.env` as `ANTHROPIC_API_KEY`. Default model `claude-haiku-5-5`; make it configurable via env var `AGENT_MODEL`. Keep token usage small (short prompts, compact tool outputs). Budget is small.

## Architecture
```
recovery-agent/
├── shop/        # the "patient": small e-commerce backend (FastAPI + SQLite)
├── chaos/       # fault injector: turns faults on/off, several at once
├── agent/       # the AI on-call engineer
├── eval/        # automated scenario runner + scoring
├── logs/        # JSON-lines logs written by shop components
├── README.md
└── experiments.md
```

### shop/ (the patient)
Components: **checkout + payment** (fake payment provider), **order queue + worker**, **inventory sync job** (source DB -> replica), **fulfillment workflow** (multi-step, per order). Plus a **traffic generator** that sends realistic orders.
- Exposes `/health` and `/metrics` (counters: checkout requests, orders saved, payments, enqueued, processed, pending, age of oldest in-progress item, sync stats).
- Writes structured JSON logs to `logs/`.
- Faults are switched on via a runtime config file that chaos/ writes and shop/ reads.

### chaos/ (fault injection)
| Fault | What happens | Signal the agent can observe | Correct fix |
|---|---|---|---|
| F1 payment drop | Payment provider times out; buggy code path returns success but saves nothing | checkout requests != orders saved | roll back bad config, replay lost requests from request log |
| F2 queue loss | Bounded queue silently drops when full under load | enqueued != processed + pending | raise capacity / enable dead-letter, replay dropped |
| F3 sync corruption | Sync job corrupts a small % of rows per run | source vs replica checksum mismatch | stop sync, roll back config, re-sync bad rows |
| F4 workflow hang | A fulfillment step never returns | oldest in-progress age > SLA, no heartbeat | restart worker, requeue stuck items |
| F5 unfixable | A fault outside the agent's allowed actions | anything | agent must **escalate**, not loop |

Must support **multiple simultaneous faults**, random seeds, and **held-out variants** (different parameters/combinations) not used during development.

### agent/ (the AI on-call engineer)
Loop: **investigate -> diagnose -> act -> verify -> (escalate)**.
- Tools: read recent logs, get metrics, run invariant checks, check health. Actions: restart component, roll back config to last-known-good, replay from log/dead-letter, re-sync rows, requeue stuck items.
- **Action allowlist**: only these actions.
- **The agent must never read chaos/ state or the fault config directly**, only observable signals (logs, metrics, checks). Otherwise the evaluation is cheating.
- Retry budget + confidence threshold -> **escalate** with an incident report.
- Every run writes a markdown **incident report**: symptoms, evidence, root cause, actions taken, verification result.

### eval/ (the standout piece)
- Runs N scenarios automatically (single faults, combinations, held-out variants, the unfixable case).
- Metrics: recovery rate, root-cause accuracy, time to recover, number of actions, wrong/unsafe actions, correct escalation rate, LLM tokens/cost.
- **Baselines:** "restart everything" script; rules-only (no LLM).
- **Ablations:** agent without invariant checks (logs only); agent without the verify step.
- Output: results CSV + summary table. Log every change in `experiments.md` (change -> score before/after).

## Rules / constraints
- **No GPL/AGPL/LGPL dependencies** (NDA). Prefer MIT/BSD/Apache. List all third-party components + licences in README.
- Never commit `.env`. Reproducible: one command per thing (start shop, inject chaos, run agent, run eval). Use seeds.
- Windows-friendly paths and process handling.

## Build order (milestones)
1. shop/ running with a traffic generator, `/metrics`, logs.
2. chaos/ with F4 and F1.
3. agent/ fixes F4 end to end (investigate -> act -> verify) and writes an incident report.
4. Add F1, then F2, then F3; multi-fault; escalation + unfixable case.
5. eval/ with baselines and ablations.
6. README, results, cleanup. (Slides + demo video are made outside the code.)
