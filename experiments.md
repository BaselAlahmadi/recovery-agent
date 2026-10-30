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

---

# Round 2 (fixes + hybrid + held-out v2)

Frozen before any v2 run: agent `7dff666404`, rules `9af179f477`, hybrid `0d189ae02a`; v2 scenarios committed as `b4c4651`.
(`eval/results/v2/frozen_hashes.txt`). v1 numbers above were produced by the OLDER shop/invariants and are not directly comparable.

| # | Change | Why | Before | After |
|---|---|---|---|---|
| 17 | `requests_vs_saved` is exact: shop counts requests in flight, zero tolerance (was 5) | Tolerance hid 1-4 lost orders | v1 held-out: 5 of 6 runs of the heavy-F1 scenarios lost 1-4 orders | v2 repeats of those faults: **0 orders lost in all 56 non-F6 runs** (agent 0/21, hybrid 0/21, rules 0/7, no-verify 0/7) |
| 18 | `replay_lost_orders` retries (8x, DB-checked) until each order exists, else reports `unrecoverable` / `not_attempted` | v1 replay gave up silently after 5 charge attempts | 3 of 52 orders silently lost in `ho_f1_heavy__agent__r1` | healthy-path replays all succeeded; unrecoverable path was only exercised by F6 |
| 19 | `payment_success` alarm needs BOTH 30 s and 5 s windows high | A correct fix kept the alarm on for ~20 s because old failures stay in the 30 s window (found by hand while designing F7, before any v2 run) | alarm 6 s after a correct rollback: still on | alarm clears within 5 s |
| 20 | Category list parsing accepts strings / mixed case; raw tool calls are logged in every report | 2 of 3 `ho_f4_f5` runs reported `unknown` although the prose was right | `unknown` in 2/3 | no unexplained `unknown` seen in v2 (F7 `unknown` was the expected answer). The string-list cause was a guess; raw arguments were not logged in v1, so the fix itself is unproven, but the raw log is now in every report |
| 21 | Scorer: added `root_cause_f1_manifested` (faults that actually showed a symptom); old metric kept | A fault with no symptom cannot be diagnosed | n/a | on v2 it barely changes the picture (agent 0.727 -> 0.727, hybrid 0.639 -> 0.650) |
| 22 | Dev regression with fixed agent, 3 reps | Check nothing broke | v1 dev: 24/24, $0.033 | 24/24, 0 unnecessary actions, 0 orders lost, $0.036 |
| 23 | **Hybrid** (existing rules first; exactly one rule + verification passes -> stop; no rule / conflict / failed verification -> agent) | Cheaper than always calling the LLM | agent dev: $0.036, 19.3k tokens/run | hybrid dev: 24/24, **$0.017, 8.4k tokens/run (-54%)**, 37.5% handed over |

## v2 held-out results (10 scenarios; agent and hybrid x3, rules and no-verify x1)

| Method | Runs | Success | Outcome right | Recovered | Unnecessary actions/run | Tokens/run | Cost |
|---|---|---|---|---|---|---|---|
| agent | 30 | 29/30 (97%) | 100% | 97% | 0.23 | 36.3k | $0.095 |
| hybrid | 30 | 28/30 (93%) | 97% | 97% | 0.53 | 28.8k | $0.078 (67% handed over) |
| rules only | 10 | 9/10 | 90% | 90% | 0.60 | 0 | $0 |
| no verify | 10 | 9/10 | 90% | 100% | 0.20 | 38.1k | $0.032 |

Hybrid x1 on held-out v1 with the fixed shop: 12/12, 42% handed over, $0.010 total.

## Findings (nothing was changed after seeing v2)

1. **Rules still nearly match.** 9/10 vs agent 29/30 and hybrid 28/30; the gaps are inside noise at this sample size. The one rules failure is the designed one:
   `v2_retries_off` (a bad config key no rule mentions): rules reported NO_INCIDENT while the payment check was failing. Agent 3/3, hybrid 2/3, rules 0/1 (n=1).
   On every other v2 scenario the rules reached the right outcome, including escalating the unfixable ones (via their "still failing after 2 rounds" fallback).
2. **The only demonstrated LLM advantage is the unmentioned config key.** The suite did not produce other situations where rules fail.
3. **Red herring: the agent took the bait.** In `v2_redherring_f6` the agent rolled back the harmless config change in 3/3 runs (unnecessary action), exactly like the rules and hybrid.
   Next to a real non-config fault with no damage signal (`v2_redherring_f4`) nobody rolled back, so that scenario was not discriminating.
4. **Novel fault F6 was mislabelled by every method**: the agent reported `payment_drop` (the closest category) in 9/9 F6 runs instead of `unknown`. The outcome (ESCALATED) was right in every F6 run except no-verify.
   Root-cause F1 is a weak metric on novel faults, so outcome and real recovery are the primary measures.
5. **The verify gate mattered once**: `v2_f4_f6` no-verify resolved instead of escalating (the resolve gate would have refused). n=1.
6. **Lost-orders bug fixed**: 0 orders lost in all 56 non-F6 runs. The orders-lost totals in the F6 scenarios (36-110 per run) only reflect how long a method ran while the cause stayed active.
7. **Failures**: agent `v2_f1_f2` r1 and hybrid `v2_f1_heavy` r1 claimed RESOLVED but `payment_success` was failing at the end check. With retries the honest failure rate at F1=0.55 is ~17%
   against a 25% threshold, so this is most likely noise around the threshold (not verified). Hybrid `v2_retries_off` r2 fixed the shop correctly but escalated, naming `external_provider`.
8. **Hybrid economics**: -21% tokens and -18% cost on v2 (only because 67% of v2 is built to defeat the rules), -54% on dev, with no accuracy gain. Its extra unnecessary actions come from the rules' second round repeating `replay_lost_orders` while an F6 loss continues.

Whole round (140 runs incl. dev regression and hybrid dev): $0.267.
