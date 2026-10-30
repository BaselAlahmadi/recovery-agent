# Experiments log

Every change to the agent or shop, with the score before and after. Single runs unless noted; the systematic
numbers are in `eval/results/summary.md`. Price basis: Haiku 5.5 at $0.10 / $0.50 per 1M tokens (in / out).

| # | Date | Change | Why | Before | After |
|---|---|---|---|---|---|
| 1 | 10-30 | First agent run vs F4 (hung worker) | Milestone 3 | crashed: SDK rejects `temperature` | removed argument, ran |
| 2 | 10-30 | **Replica checksum compares replica with what the last sync copied**, not the live source | Live-source comparison false-alarmed under traffic (replica lags 5 s), so the agent escalated a case it had actually fixed | F4 run: ESCALATED, 28.5k in / 1.8k out | RESOLVED, 13.0k in / 0.7k out, 5 turns |
| 3 | 10-30 | Replay skips orders answered `payment_failed`; request log now records the response | Honest failures must not be re-created | n/a | audit: 0 told-ok-but-lost, 0 duplicates, 2nd replay finds 0 |
| 4 | 10-30 | Root cause becomes a category list + sanitised detail | A model once leaked XML-like text into a free-text field | stray markup in report | clean category and detail in all later reports |
| 5 | 10-30 | Added `payment_success` invariant (failed checkouts in last 30 s) | Provider outage keeps every counter balanced, so nothing else fires | F5: no signal | F5: agent escalates with 0 actions |
| 6 | 10-30 | **Token cut**: pre-collected situation report, prompt caching on system + tools, shorter tool text | Cost / turns | F1: 27.7k in, 6 turns | F1: 13.4k in + 12.6k cached reads, 5 turns (about half the effective input cost) |
| 7 | 10-30 | Prompt: "act only on FAIL lines" | Agent replayed orders because of `gap=1` on an `ok` line | F3 run: 1 unnecessary action | not seen again in later runs (small sample) |
| 8 | 10-30 | Escalation without `suggested_next_steps` is refused | One escalation arrived with no next steps for the human | missing section in report | always present |
| 9 | 10-30 | `replay_lost_orders` waits 1 s before reading the request log | Eval smoke test: 1 order answered ok mid-rollback was skipped as "in flight" and never recovered | orders_lost = 1 | (checked in dev set below) |
| 10 | 10-30 | **Eval harness**: isolated shop per run, independent audit of raw request log + DB | Judge the agent without trusting its own claims | n/a | smoke test (rules_only on F1+F4) found change #9 |
| 11 | 10-30 | **Dev set, full agent, 3 reps** (agent source `044a825ad1`) | Tune on dev only | n/a | 24/24 success, 0 unnecessary actions, 0 orders lost, $0.033. Nothing to tune, agent frozen. |
| 12 | 10-30 | **Held-out set, full agent, 3 reps** (same source hash, never tuned on) | The real test | n/a | 36/36 success (>= ~90% at 95% confidence), 0 unnecessary actions, 0 duplicates; 5/36 runs lost 1-4 orders (see findings) |
| 13 | 10-30 | Baseline: restart everything (1 rep) | Naive ops reflex | n/a | 1/12 success, 58% false "fixed" claims, 38 orders lost per run, 4 duplicate shipments |
| 14 | 10-30 | Baseline: rules only, no LLM (1 rep) | Is the LLM needed? | n/a | 12/12 success, 8 s to recover, $0 |
| 15 | 10-30 | Ablation: no invariant checks / logs only (1 rep) | Do the vital signs matter? | agent 12/12 on same scenarios* | 9/12 success, 17% false claims, 2.3x tokens, root-cause F1 0.72 vs 0.93 |
| 16 | 10-30 | Ablation: no verify step (1 rep) | Does verification matter? | agent 12/12 on same scenarios* | 12/12 success: no measurable benefit on this suite |

\* the agent's 36 held-out runs are 100%; the ablations ran each scenario once.

## Findings from the held-out evaluation (agent frozen at `044a825ad1`; NOT fixed afterwards, to keep held-out clean)

1. **Rules-only matches the LLM agent on this suite** (12/12 vs 36/36, rules 3x faster, free). Every fault here leaves a clean signature in
   the invariants, so one rule per invariant is enough. The suite does not show a need for the LLM; showing one would need fault types or
   ambiguous signals the rules were not written for.
2. **Invariant checks matter**: without them 3 of 12 runs failed (a missed provider outage reported as "no incident", a partial fix, an
   unrepaired queue) and tokens more than doubled. Single run per scenario, so treat as indicative.
3. **The verify step showed no benefit**: every action worked first time, so there was nothing for verification to catch. It cost about 10 s
   per run. Not evidence that verification is useless, only that this suite never made an action fail.
4. **Real defect: orders can still be lost after a "successful" fix.** In 5 of 36 agent runs (heavy F1 / F1+F2) 1-4 orders stayed lost.
   Cause, verified in `ho_f1_heavy__agent__r1` only: `replay_lost_orders` returned `found 52, replayed 49, still_failed 3` (the flaky provider failed 5
   retries in a row), but the invariant tolerance (5 in-flight requests) hid the gap, so the agent verified OK and resolved. The other 4 runs
   with losses were not read individually; same mechanism is the likely cause (not confirmed).
   Candidate fix (needs a fresh evaluation): treat `still_failed > 0` as unfinished, replay again, and lower the tolerance.
5. **Root-cause scoring artefact**: in `ho_f1_f2` runs 1-2 the agent named only `payment_drop`. The F2 deploy was rolled back too, but the slowed
   queue never overflowed (no symptom), so naming `queue_loss` was not possible from evidence. Expected causes list injected faults, not
   manifested ones, so F1 = 0.67 there is partly the scenario's fault. (Inferred: the independent check passed without any requeue action and the
   agent's first report showed `queue_accounting` ok; I did not inspect the queue directly.)
6. **Escalation category bug**: in 2 of 3 `ho_f4_f5` runs the structured category came out `unknown` although the prose correctly named the
   provider outage (and the stuck worker). The reason for `unknown` was not captured (raw tool arguments are not logged).
7. **Restart-everything is unsafe, not just ineffective**: its `restart_worker` produced 4 duplicate shipments; the agent and rules produced 0.

Total eval cost: $0.16 for all 108 runs (24 dev + 84 held-out), 0 errors.
