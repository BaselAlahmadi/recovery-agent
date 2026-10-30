# Evaluation results

Agent source versions in these results: `044a825ad1`. Success = outcome matches expectation AND an independent check shows the shop recovered (the only exemption: the payment-success check when the provider is down).

### Dev set (used while building)

| Method | Runs | Success | Outcome right | Shop recovered | Root-cause F1 | RC F1 (manifested) | Time to recover (s) | Actions | Unnecessary actions | Duplicate shipments | Orders lost (mean) | False 'fixed' claims | Tokens (mean) | Cost ($) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| agent | 24 | 100% | 100% | 100% | 1.00 | nan | 18 | 1.6 | 0.00 | 0 | 0.00 | 0% | 17,371 | 0.033 |

### Held-out set: heldout (never tuned on)

| Method | Runs | Success | Outcome right | Shop recovered | Root-cause F1 | RC F1 (manifested) | Time to recover (s) | Actions | Unnecessary actions | Duplicate shipments | Orders lost (mean) | False 'fixed' claims | Tokens (mean) | Cost ($) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| agent | 36 | 100% | 100% | 100% | 0.93 | nan | 22 | 1.7 | 0.00 | 0 | 0.28 | 0% | 19,757 | 0.058 |
| rules_only | 12 | 100% | 100% | 100% | 0.97 | nan | 8 | 2.1 | 0.08 | 0 | 0.08 | 0% | 0 | 0.000 |
| restart_all | 12 | 8% | 67% | 42% | 0.17 | nan | 5 | 3.0 | 2.08 | 4 | 38.17 | 58% | 0 | 0.000 |
| no_invariants | 12 | 75% | 92% | 83% | 0.72 | nan | 18 | 2.1 | 0.33 | 0 | 3.33 | 17% | 46,322 | 0.050 |
| no_verify | 12 | 100% | 100% | 100% | 0.97 | nan | 12 | 2.0 | 0.08 | 0 | 0.17 | 0% | 22,158 | 0.020 |

### Full agent per scenario: Dev

| Scenario | Expected | Successes | Outcomes right | Recovered | Root-cause F1 | RC F1 (manifested) | Orders lost (mean) | Actions (mean) |
|---|---|---|---|---|---|---|---|---|
| dev_f1 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 2.0 |
| dev_f1_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 4.0 |
| dev_f2 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 2.0 |
| dev_f2_f3 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 2.0 |
| dev_f3 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 1.0 |
| dev_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 2.0 |
| dev_f5 | ESCALATED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 0.0 |
| dev_healthy | NO_INCIDENT | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 0.0 |

### Full agent per scenario: Held-out

| Scenario | Expected | Successes | Outcomes right | Recovered | Root-cause F1 | RC F1 (manifested) | Orders lost (mean) | Actions (mean) |
|---|---|---|---|---|---|---|---|---|
| ho_f1_f2 | RESOLVED | 3/3 | 3/3 | 3/3 | 0.78 | nan | 2.0 | 2.3 |
| ho_f1_f2_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 5.0 |
| ho_f1_f3 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 2.0 |
| ho_f1_heavy | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 1.3 | 2.0 |
| ho_f2_heavy | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 2.0 |
| ho_f3_f4 | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 3.0 |
| ho_f3_strong | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 1.0 |
| ho_f4_f5 | ESCALATED | 3/3 | 3/3 | 3/3 | 0.33 | nan | 0.0 | 1.3 |
| ho_f4_late | RESOLVED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 2.0 |
| ho_f5_partial | ESCALATED | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 0.0 |
| ho_healthy_high | NO_INCIDENT | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 0.0 |
| ho_healthy_low | NO_INCIDENT | 3/3 | 3/3 | 3/3 | 1.00 | nan | 0.0 | 0.0 |

### Failed runs

| Run | Outcome (expected) | Recovered | Still failing | Actions | Root causes (expected) |
|---|---|---|---|---|---|
| ho_f1_f2__restart_all__r1 | RESOLVED (RESOLVED) | 0 | requests_vs_saved | restart_worker,requeue_stuck,resync_replica | - (payment_drop,queue_loss) |
| ho_f1_f2_f4__restart_all__r1 | RESOLVED (RESOLVED) | 0 | queue_accounting,requests_vs_saved | restart_worker,requeue_stuck,resync_replica | - (payment_drop,queue_loss,stuck_worker) |
| ho_f1_f3__no_invariants__r1 | RESOLVED (RESOLVED) | 0 | requests_vs_saved | rollback_config | unknown (payment_drop,sync_corruption) |
| ho_f1_f3__restart_all__r1 | RESOLVED (RESOLVED) | 0 | replica_checksum,requests_vs_saved | restart_worker,requeue_stuck,resync_replica | - (payment_drop,sync_corruption) |
| ho_f1_heavy__restart_all__r1 | RESOLVED (RESOLVED) | 0 | requests_vs_saved | restart_worker,requeue_stuck,resync_replica | - (payment_drop) |
| ho_f2_heavy__no_invariants__r1 | RESOLVED (RESOLVED) | 0 | queue_accounting | rollback_config,requeue_unprocessed,replay_lost_orders | queue_loss (queue_loss) |
| ho_f2_heavy__restart_all__r1 | RESOLVED (RESOLVED) | 0 | queue_accounting | restart_worker,requeue_stuck,resync_replica | - (queue_loss) |
| ho_f3_f4__restart_all__r1 | RESOLVED (RESOLVED) | 0 | replica_checksum | restart_worker,requeue_stuck,resync_replica | - (sync_corruption,stuck_worker) |
| ho_f3_strong__restart_all__r1 | RESOLVED (RESOLVED) | 0 | replica_checksum | restart_worker,requeue_stuck,resync_replica | - (sync_corruption) |
| ho_f4_f5__restart_all__r1 | RESOLVED (ESCALATED) | 1 | payment_success | restart_worker,requeue_stuck,resync_replica | - (stuck_worker,external_provider) |
| ho_f5_partial__no_invariants__r1 | NO_INCIDENT (ESCALATED) | 1 | payment_success | - | - (external_provider) |
| ho_f5_partial__restart_all__r1 | RESOLVED (ESCALATED) | 1 | payment_success | restart_worker,requeue_stuck,resync_replica | - (external_provider) |
| ho_healthy_high__restart_all__r1 | RESOLVED (NO_INCIDENT) | 1 |  | restart_worker,requeue_stuck,resync_replica | - (-) |
| ho_healthy_low__restart_all__r1 | RESOLVED (NO_INCIDENT) | 1 |  | restart_worker,requeue_stuck,resync_replica | - (-) |
