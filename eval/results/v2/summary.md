# Evaluation results

Agent source versions in these results: `7dff666404`. Success = outcome matches expectation AND an independent check shows the shop recovered (the only exemption: the payment-success check when the provider is down).

### Dev set (regression check after the fixes)

| Method | Runs | Success | Outcome right | Shop recovered | Root-cause F1 | RC F1 (manifested) | Time to recover (s) | Actions | Unnecessary actions | Duplicate shipments | Orders lost (mean) | False 'fixed' claims | Tokens (mean) | Cost ($) | Handed to LLM |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| agent | 24 | 100% | 100% | 100% | 1.00 | 1.00 | 18 | 1.6 | 0.00 | 0 | 0.00 | 0% | 19,289 | 0.036 | - |
| hybrid | 24 | 100% | 100% | 100% | 1.00 | 1.00 | 15 | 1.9 | 0.12 | 0 | 0.00 | 0% | 8,422 | 0.017 | 38% |

### Held-out v1 set, re-run with the fixed shop (hybrid only; older v1 numbers are in eval/results/v1)

| Method | Runs | Success | Outcome right | Shop recovered | Root-cause F1 | RC F1 (manifested) | Time to recover (s) | Actions | Unnecessary actions | Duplicate shipments | Orders lost (mean) | False 'fixed' claims | Tokens (mean) | Cost ($) | Handed to LLM |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hybrid | 12 | 100% | 100% | 100% | 0.97 | 1.00 | 18 | 2.0 | 0.17 | 0 | 0.00 | 0% | 10,382 | 0.010 | 42% |

### Held-out set: heldout_v2 (never tuned on)

| Method | Runs | Success | Outcome right | Shop recovered | Root-cause F1 | RC F1 (manifested) | Time to recover (s) | Actions | Unnecessary actions | Duplicate shipments | Orders lost (mean) | False 'fixed' claims | Tokens (mean) | Cost ($) | Handed to LLM |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| agent | 30 | 97% | 100% | 97% | 0.73 | 0.73 | 27 | 2.0 | 0.23 | 0 | 25.47 | 3% | 36,297 | 0.095 | - |
| hybrid | 30 | 93% | 97% | 97% | 0.64 | 0.65 | 29 | 2.4 | 0.53 | 0 | 19.47 | 3% | 28,781 | 0.078 | 67% |
| rules_only | 10 | 90% | 90% | 90% | 0.62 | 0.62 | 14 | 2.5 | 0.60 | 0 | 7.90 | 10% | 0 | 0.000 | - |
| no_verify | 10 | 90% | 90% | 100% | 0.77 | 0.77 | 17 | 2.0 | 0.20 | 0 | 16.80 | 0% | 38,134 | 0.032 | - |

### Full agent per scenario: Dev

| Scenario | Expected | Successes | Outcomes right | Recovered | Root-cause F1 | RC F1 (manifested) | Orders lost (mean) | Actions (mean) |
|---|---|---|---|---|---|---|---|---|
| dev_f1 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| dev_f1_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 4.0 |
| dev_f2 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| dev_f2_f3 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| dev_f3 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 1.0 |
| dev_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| dev_f5 | ESCALATED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 0.0 |
| dev_healthy | NO_INCIDENT | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 0.0 |

### Hybrid per scenario: Dev

| Scenario | Expected | Successes | Outcomes right | Recovered | Root-cause F1 | RC F1 (manifested) | Orders lost (mean) | Actions (mean) |
|---|---|---|---|---|---|---|---|---|
| dev_f1 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| dev_f1_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 4.0 |
| dev_f2 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 3.0 |
| dev_f2_f3 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| dev_f3 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| dev_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| dev_f5 | ESCALATED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 0.0 |
| dev_healthy | NO_INCIDENT | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 0.0 |

### Full agent per scenario: Held-out

| Scenario | Expected | Successes | Outcomes right | Recovered | Root-cause F1 | RC F1 (manifested) | Orders lost (mean) | Actions (mean) |
|---|---|---|---|---|---|---|---|---|
| v2_f1_f2 | RESOLVED | 2/3 | 3/3 | 2/3 | 1.00 | 1.00 | 0.0 | 4.0 |
| v2_f1_heavy | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.3 |
| v2_f2_f3_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 4.0 |
| v2_f4_f6 | ESCALATED | 3/3 | 3/3 | 3/3 | 0.60 | 0.60 | 99.0 | 2.0 |
| v2_healthy_fast | NO_INCIDENT | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 0.0 |
| v2_redherring_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| v2_redherring_f6 | ESCALATED | 3/3 | 3/3 | 3/3 | 0.00 | 0.00 | 81.7 | 1.0 |
| v2_retries_off | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 1.0 |
| v2_retries_off_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 0.67 | 0.67 | 0.0 | 3.0 |
| v2_samesymptom_f6 | ESCALATED | 3/3 | 3/3 | 3/3 | 0.00 | 0.00 | 74.0 | 0.3 |

### Hybrid per scenario: Held-out

| Scenario | Expected | Successes | Outcomes right | Recovered | Root-cause F1 | RC F1 (manifested) | Orders lost (mean) | Actions (mean) |
|---|---|---|---|---|---|---|---|---|
| v2_f1_f2 | RESOLVED | 3/3 | 3/3 | 3/3 | 0.89 | 1.00 | 0.0 | 3.0 |
| v2_f1_heavy | RESOLVED | 2/3 | 3/3 | 2/3 | 1.00 | 1.00 | 0.0 | 2.3 |
| v2_f2_f3_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 4.0 |
| v2_f4_f6 | ESCALATED | 3/3 | 3/3 | 3/3 | 0.50 | 0.50 | 110.0 | 2.0 |
| v2_healthy_fast | NO_INCIDENT | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 0.0 |
| v2_redherring_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | 1.00 | 0.0 | 2.0 |
| v2_redherring_f6 | ESCALATED | 3/3 | 3/3 | 3/3 | 0.00 | 0.00 | 36.0 | 4.0 |
| v2_retries_off | RESOLVED | 2/3 | 2/3 | 3/3 | 0.33 | 0.33 | 0.0 | 1.0 |
| v2_retries_off_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 0.67 | 0.67 | 0.0 | 3.0 |
| v2_samesymptom_f6 | ESCALATED | 3/3 | 3/3 | 3/3 | 0.00 | 0.00 | 48.7 | 2.7 |

> Note: 'Orders lost' includes the f6 scenarios, where the cause (silent write failures) cannot be fixed, so loss continues by design.

### Failed runs

| Run | Outcome (expected) | Recovered | Still failing | Actions | Root causes (expected) |
|---|---|---|---|---|---|
| v2_f1_f2__agent__r1 | RESOLVED (RESOLVED) | 0 | payment_success | rollback_config,replay_lost_orders,replay_lost_orders,requeue_unprocessed | payment_drop,queue_loss (payment_drop,queue_loss) |
| v2_f1_heavy__hybrid__r1 | RESOLVED (RESOLVED) | 0 | payment_success | rollback_config,replay_lost_orders | payment_drop (payment_drop) |
| v2_f4_f6__no_verify__r1 | RESOLVED (ESCALATED) | 1 | requests_vs_saved | restart_worker,requeue_stuck,replay_lost_orders,replay_lost_orders | stuck_worker,payment_drop (stuck_worker,unknown) |
| v2_retries_off__hybrid__r2 | ESCALATED (RESOLVED) | 1 |  | rollback_config | payment_drop,external_provider (unknown) |
| v2_retries_off__rules_only__r1 | NO_INCIDENT (RESOLVED) | 0 | payment_success | - | - (unknown) |
