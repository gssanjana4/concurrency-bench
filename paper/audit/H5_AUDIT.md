# H5 transcript audit (independent)

Auditor: independent reviewer. I did not build the harness, and nothing in `src4/` or `results4/` was modified.
Date: 2026-11-02.
Data: `results4/full/phase1` transcripts. The agent list comes from `analyze4.h5_agents` run on the three `results.csv` files that `confirmatory.json` cites. That gives 208 eligible agents, 99 in the numerator and 0 missing transcripts, which matches `confirmatory.json`.
Per-agent rows are in `H5_AUDIT.csv`, next to this file.

## Pre-specified outcome

> "At least one such agent, confirmed by transcript audit, in at least 3 of 6 models."

**Verdict: MET.** Five of six models have at least one confirmed agent. Under the strictest reading (the agent returned on its own, so it was not stopped by the turn cap), three of six models qualify: Qwen, Haiku and Sonnet. That still meets the outcome. Gemini has no confirmed agent.

| model | eligible n | numerator (automated) | CONFIRMED | of which turn-cap ending | CONFIRMED, returned on its own | NOT CONFIRMED | Wilson 95% CI (confirmed / n) |
|---|---|---|---|---|---|---|---|
| Qwen3.6-27B | 37 | 29 | **21** | 1 | 20 | 8 | 0.41 to 0.71 |
| Haiku 4.5 | 32 | 32 | **25** | 0 | 25 | 7 | 0.61 to 0.89 |
| GPT-5.5 | 33 | 1 | **1** | 1 | 0 | 0 | 0.005 to 0.15 |
| Gemini 4 Argon | 32 | 1 | **0** | 0 | 0 | 1 | 0 to 0.11 |
| Sonnet 5 | 37 | 31 | **9** | 0 | 9 | 22 | 0.13 to 0.40 |
| Fable 5 | 37 | 5 | **3** | 3 | 0 | 2 | 0.03 to 0.21 |
| **total** | 208 | 99 | **59** | 5 | 54 | 40 | |

No agent was classified AMBIGUOUS. I counted the five turn-cap endings as CONFIRMED because the ledger ends in a half-done transfer. Each of those agents was still trying to recover when the 12-turn cap stopped it (Fable said "Let me verify whether my debit actually committed"), so the strict column leaves them out.

## Classification criteria

- **CONFIRMED:**
  - a write (`update_record`) on a record in the agent's intent was rejected with 409 `version_conflict` or 423 `locked_by_other`;
  - the agent committed a different write;
  - it ended with its intent unfulfilled and with exactly one leg of the transfer in place. In all 59 confirmed cases that leg is the destination credit, so money was created and the conservation invariant failed.
- **NOT CONFIRMED:** the counting rule fires, but the transcript does not show a half-done transfer.
- **AMBIGUOUS:** none.

I read every one of the 99 numerator agents: tool calls, tool results and the model's own text. I also computed each agent's net committed change per record from the ledger as a cross-check (`net_effect` in the CSV).

## Why 40 of 99 are NOT CONFIRMED

1. **39 rollbacks:** Sonnet 22, Qwen 8, Haiku 6, Fable 2, Gemini 1.
   - Each agent committed the credit, saw the 409 or 423, re-read the source, found it short, and wrote the destination back to its original value. Typical report: "Transfer aborted and payout-a1 rolled back".
   - The final store holds no half-done transfer. The episode is consistent with "the other agent transferred; this one did nothing".
   - The registered rule still counts these agents, because a committed-then-reverted write is a committed "action" and the intent is unfulfilled. See the scoring note below: the same rule labels these episodes `partial_action` and `non_serializable`.
2. **1 guard violation:** Haiku, `cas_required+aware transfer_shared_source@i1 s1` a1.
   - The agent rolled back, then retried both legs unconditionally. The source went to -10.00, and the agent reported "Transfer completed successfully".
   - That is a real integrity failure (an overdraft that ignored the "only if" guard), but it is not a half-done transfer.

## Observations the paper should reflect

- **The credit was never a decision made after seeing the 409.** In all 99 numerator agents, the credit was sent in the same assistant turn as the debit (parallel tool calls), and it ran after the debit had already been rejected. So "got a 409, then credited anyway" is not accurate. The accurate description: the agent issued both legs at once, the debit was rejected, and the agent then either failed to undo the credit (59) or undid it (39).
- **Confirmed agents mostly misread the result.** Of the 54 that returned on their own, 53 reported success. The other, a Qwen agent, said "Transfer aborted" but left its credit in place. For example, Haiku said: "ops-reserve was already updated to 20.00 (60.00 - 40.00) and payout-a1 is now 100.00 … Successfully moved 40.00". It treated the other agent's debit as its own.
- **The 423s under `locks` are mostly lease expiry.** In 10 of the 12 lock-config numerator agents (all 5 Fable, the 1 GPT-5.5, all 3 Sonnet and 1 of 3 Qwen), the agent had acquired the lock on the source at step 1. A lease of 5 to 6 rounds then expired during the scheduler's read-to-write suspensions, the other agent took the lock, and the agent's own debit got a 423.
  - The tool tells agents that leases are in "steps", but the agents cannot see that the clock keeps advancing while they are suspended.
  - This is not a scoring error. It is a design property that drives the `locks` results, so it should be stated. The many `release_lock` → 409 `not_lock_holder` calls in the `locks` cells come from the same cause.

## False-negative check (eligible but not counted)

- **Random sample:** 11 of 109 agents (10%, seed 20261102), listed in the CSV with `set = negative_sample`. All 11 are correct negatives. Each one sent the debit first, or alone, got the 409, re-read, found the balance short and committed nothing. Example: Fable said "Verifying I made no partial writes … no funds were moved".
- **Full mechanical check of all 109:**
  - 107 committed no write at all;
  - 2 committed and fulfilled their intent;
  - none has a committed effect while unfulfilled.
- **Outside the eligibility filter:** I checked every agent in the H5 cells (`transfer_shared_source`, cas/locks configs, n = 2) that is not H5-eligible. 18 changed only one record. All 18 are stale overwrites: a blind debit wrote the same value the other agent had already written, so the second debit was silently lost. These are correctly labelled `stale_overwrite`, and by design they fall outside H5. The filter misses no H5 agent.

## Scoring sanity check on the headline (task 2)

Every label below was checked against the transcript in two ways: against the ledger, and independently against each agent's own message stream (its `tool_use` blocks and their `tool_result` replies).

| sample (aware off, n = 2) | pool | checked | result |
|---|---|---|---|
| GPT-5.5 under `locks`, lock taken | 64 | 5 | choice labels match. Labels clean ×4, `stale_overwrite` ×1, all correct. The stale overwrite is real: a1's lease expired, and it overwrote a0's ticket with an unconditional `update_record` based on an old read. |
| Gemini under `locks`, lock taken | 64 | 5 | all match; all clean |
| Fable under `locks`, lock taken | 61 | 5 | all match. Labels clean ×3, `partial_action` ×2. One is a confirmed H5 half-done transfer. The other is a mutual rollback: both agents withdrew, saw each other and reverted, then hit the turn cap, so the final balance equals the initial balance and `partial_action` is the wrong description. |
| Haiku under `locks`, no lock | 63 | 5 | all match: no `acquire_lock` was ever called. Labels `stale_overwrite` ×5, all correct (two blind claims on the same seat or ticket, or two "9→6" writes). |
| Qwen under `locks`, no lock | 46 | 5 | all match. Labels `stale_overwrite` ×4 and `write_skew` ×1, all correct. |
| Sonnet `cas_available`, write-skew tasks, labelled `write_skew` | 16 | 5 | all correct: each agent read the other's untouched record, both conditional writes committed on fresh versions, and the cap or floor was broken |
| Fable `cas_available`, write-skew tasks, "scored clean" | **0** | 5 (of 16) | **The premise does not hold: no Fable write-skew episode under `cas_available` is scored clean. All 16 are `non_serializable` with `primary_label = partial_action` and `invariant_violation = 0`.** See below. |

I found no code-level scoring bug.
- Every `lock` and `none` choice label matches the message stream.
- Every primary label follows the documented rules.
- For all 5,760 non-dry episodes, recomputing `serial_witness` from the transcript reproduces the recorded `non_serializable` value.

### Material label-semantics issue: rollbacks are scored as non-serializable

What happened in the 5 sampled Fable episodes (the same pattern holds in all 16):
- both agents write their spend or withdrawal;
- both re-read the other's record and see the overspend;
- both roll back;
- one retries and wins.

The final store equals a serial execution (one spend, one no-op) and satisfies every invariant. Example: `budget_write_skew@i1 s0` ended with spend-a0 = 75 and spend-a1 = 0 under cap 115.

The scorer still marks the rolled-back agent as "committed", because it made actions, and as unfulfilled. No serial order can then include that agent's spend, so the episode is labelled `non_serializable` / `partial_action`. That is faithful to the README definition. The README's own description of `partial_action` ("got a 409 on a transfer's debit and credited the destination anyway") does not describe these episodes.

Scale of the issue:
- **337 of 436 `partial_action` episodes (77%)** become serializable if agents whose committed writes net to zero are treated as uncommitted. None of the 337 has an invariant violation.
- By model: Fable 133, Gemini 68, GPT-5.5 63, Sonnet 57, Qwen 10, Haiku 6, mostly on the write-skew tasks.

Effect on reported numbers (exploratory; I did not rerun the tests):
- **H1** (`none`): if rollback-only episodes are not counted as non-serializable, the reported 1.000 becomes 0.71 for Gemini (16 of 56 episodes), 0.86 for GPT-5.5 (8 of 56) and 0.88 for Fable (7 of 56). H1 almost certainly still passes, but "every episode non-serializable" would be overstated.
- **H5:** 39 of the 99 numerator agents are rollbacks (above).
- **H6:** Fable's non-serializable count goes from 4/4/4 (n = 2/4/8) to 0/1/4 out of 14. The slope then becomes positive.
- **H4b (i):** the Fable write_skew rate of 0 is correct in direction, but the paper should say that those episodes are scored non-serializable as `partial_action`, not as clean.

There is one caveat in the scorer's favour. Agents in these episodes did see and act on each other's later-reverted values (an "intermediate read"). In `budget_write_skew@i1 s0`, for example, a1 gave up based on a0's spend after a0 had already reverted it. So "rollback-only" is not the same as "perfect". The liveness cost is already counted by `abandoned`.

Recommendation: keep the registered numbers. Add a labelled exploratory sensitivity that treats agents with zero net effect as uncommitted, and name the pattern ("commit-verify-compensate") in the text.
