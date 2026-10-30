# Demo script (for the screen recording)

Two scenes, about 2 minutes each. Use **three PowerShell windows** side by side, all in the project folder with the
virtual environment active (`..\.venv\Scripts\Activate.ps1`). The AI key must be in `.env` (`ANTHROPIC_API_KEY=...`).

Tip: add `--pause 0.6` to every `python -m demo` command to slow the output down for the camera.
Each AI run costs about $0.001 to $0.002.

## Setup (once per take)

**Window 1: the shop (the "patient")**
```powershell
python -m uvicorn shop.app:app --port 8000
```

**Window 2: customers (traffic)**
```powershell
python -m shop.traffic --rate 5 --duration 0 --seed 7
```
It prints nothing until you stop it. It sends about 5 orders per second.

**Window 3: you (chaos + the demo)** (all commands below are for this window)

> Between scenes, **restart Window 1** (Ctrl+C, run it again) so each scene starts from a clean shop.

---

## Scene 1: F7, "the rules miss it, the AI fixes it"

Story: someone deployed a bad setting that turned **off payment retries** while the payment provider is a bit flaky.
Nothing crashes, no error is logged. Customers just see "payment failed". No fixed rule mentions that setting.

```powershell
python -m chaos clear
python -m chaos on f7 --rate 0.5
```
**Wait about 30 seconds.** The shop needs that long to be sure the failure rate is real and not a blip.

**1a. Fixed rules only (no AI).** Shows the limit of rules:
```powershell
python -m demo --method rules_only --pause 0.6
```
What to point at: `payment_success` is **FAIL**, but "no rule matches", so the rules do nothing and report
**NO INCIDENT**. A red `WARNING` says the shop is still broken.

**1b. The full system (rules first, then the AI):**
```powershell
python -m demo --method hybrid --pause 0.6
```
What to point at, in order:
1. Step 1: one vital sign fails (`payment_success`).
2. Step 2: "no rule matches, handing to the AI".
3. The AI is briefed: the config differs from last-known-good (`payment_retries 2 -> 0`).
4. AI action: `rollback_config` with its reason and confidence.
5. Verification: waits 5 s, re-checks, **ALL INVARIANTS OK**. The provider is still flaky, but customers can pay again.
6. Outcome: RESOLVED, plus the incident report path (open that file on camera).

---

## Scene 2: F5, "the AI knows when to stop" (escalation)

Story: the payment provider is **fully down**. Nothing the shop is allowed to do can fix that. A good on-call
engineer escalates instead of poking things.

Restart Window 1 (clean shop) and Window 2 (traffic), then:
```powershell
python -m chaos on f5
```
**Wait about 30 seconds**, then:
```powershell
python -m demo --method hybrid --pause 0.6
```
What to point at:
1. Step 2: exactly one rule matches (`provider_outage`), so the rules act first. They have **no action** for it.
2. The vital sign is still failing, so the system hands over to the AI.
3. The AI looks at the logs and the config (no changes, so not a bad deploy).
4. **ESCALATED**: root cause `external_provider`, **no actions taken**, and a clear "for a human" next step.
5. Open the incident report: symptoms, evidence, root cause, suggested next steps.

---

## Reset

```powershell
python -m chaos clear
```
Then stop Windows 1 and 2 with Ctrl+C.

## Other things you can show

- Healthy shop: `python -m demo --method hybrid` with no fault. Everything is OK, no AI call, no cost.
- A stuck worker: `python -m chaos on f4`, wait about 20 s, then the demo. One rule matches, the rules fix it, no AI call.
- Two faults at once (rule conflict): `python -m chaos on f1` and `python -m chaos on f4`, wait about 30 s, then the demo.
  Several rules match, so the AI handles it.
- The AI alone: `python -m demo --method agent`.
