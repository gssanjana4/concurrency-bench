# src5: harness v2 for Study 2 (corrected) of "Do LLM Agents Coordinate on Shared Records?"

> **V2 pre-spend fixes (2026-11-03), Round 3 the same day.** Two pre-spend reviews (`paper-concurrency/review/V1_db_prespend.md`,
> `V2_agent_prespend.md`) and their re-checks (`V1b_db_recheck.md`, `V2b_agent_recheck.md`) found defects that
> would have been frozen into the transcripts. All are fixed; the blocker-by-blocker map, with the test that proves
> each fix, is `../CHANGES_V2.md` (Round 3: its last section). This README describes the harness as it now stands.

Study 1 is `src4/`. It is frozen and pre-registered, and nothing in it was changed: the `src4` and `src4_batch`
hashes are identical before and after this build. Study 2 copies what it needs into `src5/` (harness) and
`src5_batch/` (batch execution) and fixes the defects found by the four hard reviews
(`paper-concurrency/review/T1`–`T4`). Stdlib only, apart from the `anthropic` SDK for the batch path.

```
cd src5 && python3 -m unittest tests5                           # 87 harness tests, ~6 s
python3 validity5.py --out validity                             # reference-policy validity table (~3 min)
python3 plan5.py --plan plan_study2.json                        # grid + cost per provider + power
cd ../src5_batch && python3 -m unittest tests_batch tests_gemini # 56 batch-path tests incl. the equivalence gate
python3 ../src5_verify/mutate5.py                               # mutation testing (115 mutants)
python3 rescore5.py --cap 24 --out cap24.csv <transcript dirs>   # pre-registered sensitivity: locks/all at 24 calls
bash ../run_conc_study2.sh --dry-run                            # the whole grid with fake models + dry_check5
```

## Files

| file | purpose |
|---|---|
| `records5.py` | versioned store + ledger (src4 copy; `CallRecord` gains `own_call`, `fencing_token`, `lease_remaining`, `waited_rounds`) |
| `world5.py` | tool surface: fenced locks (per-record tokens, own-call leases), `renew_lock`, blocking lock wait (150 rounds), plain-overwrite `claim`, one neutral 409 text, `all_available` = CAS + locks, cue-free texts |
| `scheduler5.py` | seeded randomized environment per episode (start offsets, think time, call latency, round order) |
| `tasks5.py` | intents (now with unguarded `effect` and `net_delta`), invariants with kinds, `accounted`, `rolled_back_agents`, `control_of` |
| `instances5.py` | 7 contended templates + 7 matched controls, neutral names, disjoint from Study 1 |
| `agents5.py` | scripted reference policies (correct protocols, naive policies, probes, deadlock diagnostic) |
| `score5.py` | checker: final-state verdict, all-reads DSG, split non-exclusive flags, outcome classes, interleaving descriptor |
| `design5.py` | configs, scheduler defaults, the call cap |
| `validity5.py` | reference-policy validity table, checker agreement, interleaving report → `validity/` |
| `model_agent5.py`, `providers5.py`, `preflight5.py` | model loop and providers (records per-completion settings; Qwen routing; optional Ollama) |
| `run5.py` | sync grid runner (OpenRouter models; any model in dry runs) |
| `budget5.py` | spend across all logs, one cap per provider family plus a total, per-model sub-caps |
| `plan5.py`, `study1_costs.json`, `plan_study2.json`, `plan_study2.txt` | planner built on Study 1's observed costs; the chosen grid |
| `summarize5.py` | descriptive summary of results CSVs (drops and counts episodes without their matched partner) |
| `rescore5.py` | sensitivity re-score of finished episodes at a lower call cap (24) from the logged ledgers |
| `freeze5.py`, `FREEZE.md` | sha256 of every frozen file: `src5/*.py|*.json`, `src5_batch/*.py|*.json|*.sh`, `src5_verify/dry_check5.py`, `run_conc_study2.sh` (Round 3). The runner and batch driver refuse to start on any mismatch or unlisted file. |
| `tests5.py` | unit tests |
| `../src5_verify/dry_check5.py` | checks over a full dry run (channels exercised, control disjointness, tokens, message ids, probes) |

## What changed from Study 1, and why (each item is tested)

### 1. Locks: fenced, exclusive writes (T1 §6, T2 F4, T4 M2; V2 fixes V1 B3–B6)
**What the lock service guarantees, precisely.** Fenced *writes* are exclusive: while a record is locked only
the holder's writes that carry the live token are accepted. Read-modify-write is safe **only when the read is
inside the same lease as the write.** A read under one lease followed by a write under a later lease (re-acquired,
new token), or a tokenless write once the record is unlocked again, is accepted and can lose an update (review V1
B5, L1/L2). v1 of this README said "real mutual exclusion"; that overstated it.
- **The lease counts the holder's own tool calls.** `acquire_lock(record_id, lease_calls)` covers the holder's
  next `lease_calls` calls of any kind, on any record (1–20). Global rounds, think time and the holder's own
  waiting do not count. The tool description states the unit, the range and that time between calls does not
  count.
- **Fencing tokens, one counter per record (V1 B4).** `acquire_lock` returns `fencing_token`, strictly increasing
  over the grants *on that record*. (v1 used one global counter, so in a control a0's token was 2 whenever a1 had
  locked its own private record first: an information channel between the arms.) While a record is locked, writes
  need the token: anyone else gets `423`, the holder gets `428` without the token and `409` with a wrong one. A
  write whose token's lease has ended gets `409`: `lease_expired` ("your lock on X has ended."; v1 added "acquire
  it again", which steered models into the lost update above) or `stale_fencing_token` if the record was locked
  again since.
- **Visible lease.** `lease_remaining` is returned by `acquire_lock`, `renew_lock` and every fenced write.
  `renew_lock(record_id, lease_calls)` restarts the lease of a lock still held.
- **Blocking wait: 150 rounds (V1 B3, Round 3 V1b R1).** A refused `acquire_lock` is held by the scheduler up to
  150 rounds and costs one call; the description says so. 150 covers the longest hold one non-renewed lease
  allows: (max_lease_calls + 1) × (1 + gap_max + latency_max) = 21 × 7 = 147 rounds, so a correct holder is never
  timed out, however many calls it makes inside its lease. History: v1 waited 6 (44 % of waits against a correct
  holder ended in 423); V2 waited 48, tuned to the fastest correct holder (`lock_protected`), and refused 10 % /
  35 % of waits on budget_write_skew against holders that make 2 / 4 more calls inside the critical section
  (Study 1 holders made a median of 3–6 and a p90 of 6–11 calls while holding). **At 150: 0 of 4,200 waits end in
  423** against holders with 0, 2, 3, 4, 8 or 11 extra calls, in all 7 families (4 instances × 25 schedules each;
  V2's 48 refused 865 of them). The wait costs rounds, not calls or money: `lock_protected`'s ledgers are
  identical at 48 and 150 (tested), and the deadlock diagnostic stays far below `max_rounds` = 3000.
- **Release on exit and version hiding.** A finished agent's locks are released, and its `lock_leak` is still
  recorded. 423 bodies do not leak versions under `locks`.
- **The lock-safety gate checks leases (V1 B6).** Every lock event carries the ledger `seq` at which it takes
  effect. `score5.mutual_exclusion_violations` now requires every committed fenced write to lie strictly inside
  its token's validity window, and no committed write by a non-holder (or by the holder without the live token)
  while a lock is live. v1 checked only that the token had been granted to the writer: a deliberately broken world
  that accepts expired tokens was flagged in 0/8 episodes; now 8/8 (test, and the reviewer's L5 script). A world
  that ignores locks is also caught. **0 violations in all 23,808 validity episodes.**
- **What a lock user did, measured (V1 B5; Round 3 V1b S1).** Per agent: `fenced_stale_basis` (a fenced write
  whose basis read of the written record precedes its token's grant), `fenced_unread_basis` (a fenced write whose
  writer made no read of the record inside the token's window: a locked blind overwrite) and `lock_effective`
  (granted, committed, every committed write fenced and preceded by a read of its record under that token;
  undefined if it committed nothing). V2 credited a locked blind overwrite (lock, `claim` with the token, no read)
  as effective in 64/64 agents of episodes that all failed `stale_overwrite`; now 0. New naive rows that must fail:
  `reacquire_no_reread` (lease 1, read, innocent call, 409, re-acquire, write the old value: fails 1.00, every
  write fenced and in-lease, 0 mutex violations, every such write flagged) and `lease_then_tokenless` (lease
  runs out, tokenless write: fails 0.91–1.00). The v1 probes `lock_short_lease` and `lock_no_fence` never write
  (fulfilment 0); they show only that the server refuses the misuse, and are labelled rejection probes.

### 2. The scheduler varies interleavings (T1 §7, T2 F9; V2 fix V1 B2)
- **Seeded random environment per episode.** Seed = sha256 of (space, family, instance, schedule index, n).
  Each agent gets a start offset U{0..6}, a **think time U{0..4} before every completion**, and with probability
  0.3 an extra call latency U{1..2} after each call. The round order is reshuffled every round.
- **Think time placement (V1 B2).** v1 put the gap only after the first read of a decision cycle, so "re-read,
  then write" had a near-zero read-to-write window by rule. An LLM thinks after every tool result. Now a model
  agent marks the last call of each reply (`ToolCall.ends_turn`); the gap follows that call, so the calls of one
  reply run back to back and every new completion waits. Every scripted yield is its own turn.
- **Determinism.** Draws are indexed by each agent's own counters, so the same seed and the same behaviour
  give an identical ledger (tested).
- **Paired design.** A contended task and its control share the schedule seed.
- **Interleaving distribution.** Measured on `naive`, contended, n = 2, 224 episodes (`validity/validity.md`):

  | | Study 2 scheduler | Study-1-like schedule (gap 2, no jitter, no latency) |
  |---|---|---|
  | first mover | a0 114, a1 110 | (fixed by seed in Study 1) |
  | every first read before every other agent's first write | 85 % | 100 % |
  | distinct first-read/first-write patterns | 11 | 4 |
  | failure rate, naive / rereader (config none) | **0.75 / 0.56** | 1.00 / 1.00 |

  v1 reported 0.64 / 0.32 and called it proof that re-reading helps; half of that gap was the think-gap rule
  (rereader/naive 0.50 under v1's rule, **0.74** now, the reviewer's every-read figure). Re-reading helps a
  little, and only because the schedule varies. Under `none`, versions are hidden and value-ABA is
  undetectable, so for 5 of 7 families no correct protocol exists there; what separates models under `none` is
  the timing of their last read.

### 3. Uncontended controls (T1 §8 blocker, T2 F1, T4 F2)
- **Construction.** Every contended template `T` has `T_ctrl`. Each agent gets a private copy of `T`'s whole
  record group: same number of records, same amounts, same wording. Only the group tag inside record names
  differs.
- **Agent a0's text is identical in `T` and `T_ctrl`.** Peer-owned records that a guard reads (for example
  `budget:ops-south/spend-hiring`) are named from neutral pools in both arms. No agent can tell from its text
  whether its records are shared.
- **Same tool menu** in both arms.
- **Verified uncontended (V1 B4).**
  - Statically: `shared_records() == ∅`.
  - Dynamically: **zero cross-agent edges in every control episode of every policy**, and every control episode
    of every policy is `clean` (validity table). `cross_agent_edges` now counts DSG edges **plus delivered
    messages** (a message the recipient read is an information flow; v1 left it out); the record edges and
    `messages_delivered` are reported separately, and control episodes with a delivered message are reported
    apart (only possible in the peer-informed rehearsal configuration, never in the grid).
  - The other two shared channels are closed: fencing tokens are per record and message ids per recipient.
  - The dry-run fake model now **locks and messages** when those tools are offered, so the dry run exercises
    these channels (v1's dry run never took a lock or sent a message, which made its "0 cross-agent edges"
    vacuous for them). `src5_verify/dry_check5.py` checks the full dry run: controls have 0 record edges, tokens
    in controls are a private 1, 2, … sequence per record, message ids are 1, 2, … per recipient, a0's prompt is
    byte-identical in each contended/control pair, and the lock-safety gate is clean.

### 4. The call cap scales with n and config, and is validated (T2 F3, T4 M7)
- **Formula:** `call_cap(n, config) = 8n + 8 (+4 with locks)`.
  - n = 2: 24 (none, cas_available) and 28 (locks, all_available).
  - n = 4: 40 / 44.
- **Validation.** Every correct protocol finishes on every contended template and control in every
  configuration that offers its primitive, using at most 80 % of the cap, with **0 cap endings**, on the
  validity seeds (4 instances × 8 schedules). Worst case at n = 2 is 18 calls (verify_and_compensate).
- **Back-off (V1 B2 knock-on).** With a think gap before every completion, v1's id-dependent back-off let
  verify-and-compensate livelock (write, verify, undo, in step) into the cap. The reference back-off is now
  randomized per (schedule seed, agent, attempt) with a rank offset of 5 + 2·attempt reads for odd ranks, and
  verify-and-compensate re-reads the records it saw change and declines as soon as fresh values make its guard
  false. Purely random back-offs (U{1..2+a}, U{0..4}, {0,4}, exponential) left 1–5 % of write-skew episodes above
  80 % of the cap. **Residual tail, reported, not hidden:** on 8 instances × 50 schedules, verify-and-compensate
  on budget exceeds 80 % of the cap in 1/400 episodes (1 cap ending at cap 24), promote_before_write on joint in
  5–9/400 (1 cap ending). Optimistic protocols livelock with geometric tails; no finite cap removes it.
- **n = 4 limit.** At n = 4 the write-skew protocols thrash (up to 40–68 calls), so Study 2 runs write-skew
  families at n = 2 only. The planner's n = 4 blocks exclude them.
- **Reporting.** Cap endings are reported per episode (`cap_endings`) and per cell (`summarize5.py`).

### 5. The checker (T1 §1–5, T4 M8)
**(a) `fs_nonserializable`** (renamed from `non_serializable`) is *specification-level final-state
serializability over agent sessions*. It asks whether some order of the committed intents reproduces the
final store. Rolled-back agents are treated as aborted. It is **not** Adya or Berenson serializability of the
executed history, and the README and the docstring say so.

**(b) `dsg_cycle`** is an Adya-style DSG.
- **Nodes:** every session with a read or a write.
- **Reads:** every successful read. The "effective read" filter is gone.
- **Versions:** every installed version.
- **Edges:** ww, wr and rw.
- **Variants:** `dsg_g1c` (cycle on ww/wr only) and `dsg_cycle_committed` (induced on committed agents).
- **Documented deviations:** sessions never abort, so the reads of retried attempts and post-write
  verification reads stay in the transaction, and every write is a version.

- **New variant, the per-write basis DSG (`dsg_basis_cycle`, V1 non-blocking 1).** Each committed write depends
  on its writer's latest successful read, before that write, of each record of its intent's reads; rolled-back
  sessions are aborted. It drops the reads of attempts that got a 409 and a rereader's dead first read.

Agreement over all 23,808 validity episodes (n = 2 and 4):

| | all-reads DSG acyclic | all-reads DSG cyclic | of which basis DSG cyclic |
|---|---|---|---|
| fs-serializable | 16,382 | **2,006** | 442 |
| fs-nonserializable | **0** | 5,420 | 5,420 |

- The 2,006 all-reads disagreements are definitional (session = transaction, no aborts): cas_retry 546,
  rereader 488, verify_and_compensate 396, promote_before_write 256, cas_claim 200, promote_after_write 98,
  reacquire_no_reread 16, lease_then_tokenless 6.
- The basis DSG removes 1,564 of them. Of the 442 left: 292 verify_and_compensate (288 flagged
  `compensation_exposed`, a G1a read of a compensated write), 124 promote_before/after_write (their no-op
  write-backs install versions), and 26 naive-policy episodes whose final state happens to be serializable.
- **Retracted:** v1 said "every fs failure is cyclic" and "the DSG is stricter by construction, always in the
  same direction". That holds only for these scripted policies. A half transfer is fs-nonserializable on an
  acyclic history (an atomicity failure has no cycle; test `test_fs_failure_can_be_acyclic`, and 36/64 episodes
  in the reviewer's C2, all 32 controls included).
- **`clean` is a specification-level outcome.** It can sit on a cyclic committed history (e.g. rereader and
  cas_retry on `inventory_still_valid`). Say so next to every table.

The paper must report all three graph verdicts (all-reads, basis, committed-only) next to fs and never call one a
cross-check of another.

**(c) Conservation.** A new `accounted` invariant on inventory, budget and joint accounts: the net change
equals the sum of `net_delta` over agents that committed and did not roll back. Transfers keep `conserved`. It
catches out-of-intent money creation (T1 CEX-2) and lost units.

**(d) Non-exclusive flags.** `missing_leg`, `compensated` (+`compensated_after_violation`,
`compensation_exposed`), `guard_violation`, `wrong_value`, `out_of_intent_write`, `stale_overwrite` (any,
blind included), `lost_update` (read-based P4 only), `laundered_cas` (an expected_version the writer never observed; the 409 body no
longer carries the version, Round 3, so this is now a guessed version),
`write_skew` (the A5B history pattern on value-changing writes, reported whether or not a constraint broke),
`ever_violated` (a constraint invariant failed after *any* committed write) and `violated_at_end`.
- **Outcome** = `clean` / `compensated` / `failed`. **Cap stratum (Round 3, V1b S3):** `cap_truncated` = failed
  and some agent ended at the call cap (e.g. a v&c agent cut between its write and its compensation);
  `outcome_stratum` = the outcome with those episodes as `cap_truncated`, for the pre-registered sensitivity
  analysis that excludes them. `rescore5.py` re-scores the lock configurations as if their cap were 24 (the cap of
  `none` / `cas_available`) from the logged ledgers: agents over 24 calls are cut after their 24th call; an
  episode in which another agent later touched a record the cut agent changed, locked or held is reported
  `indeterminate`, never imputed (tested: every determinate re-score equals a real run at cap 24).
- **`primary_label`** follows the precedence missing_leg > guard_violation > out_of_intent_write > lost_update
  > stale_overwrite > write_skew (with a violated constraint) > wrong_value > constraint_violation, for compact
  tables only.
- **T1 counterexamples now have tests.** CEX-1 (a double application masking a lost update: fs says fine, flags
  say `lost_update`, DSG cyclic), CEX-2, CEX-4 (now `guard_violation`, not partial), CEX-6 (laundered CAS) and
  the read-only snapshot cycle.

**(e) Rollback-only episodes** are `compensated`, not `partial_action`. `compensation_exposed` now counts only
reads of non-final, non-restoring versions (V1 text 6: reading a compensation version that restores the original
value is not a G1a read).

**(f) Timed choice codes (V2 F3, V1 text 4; Round 3, V2b C1).** Per agent: `first_protective` (lock or cas), its
own-call index, the own-call index of the first contention signal **caused by another agent**
(`score5.peer_signal_calls`: a 423; a 409 with `conflict` set, i.e. `version_conflict` or a `stale_fencing_token`
whose latest lock is another agent's; a held acquire; a lock grant on a record another agent had locked; a read of
a version another agent installed; an exposed-version write over another agent's version), `contention_signals`
(their number: the exposure measure of the manipulation check), `protect_before_contention` (the first protective
call at or before the first signal, or no signal) and, for reactive locking, `first_lock_call` and
`lock_after_contention`. V2 counted any 409/423 and any read value other than the initial one, so an agent reading
back its own write, its own lease expiry or its own bad `expected_version` was coded as having seen contention:
32/32 control agents of the verify habit, 32/32 of `lock_short_lease`. Now **0 control agents of every reference
policy** have a signal (validity gate), and a CAS write or acquire whose own response is the first signal counts
as protection *before* contention (V2 coded it as reactive). Per model agent: `first_reply`, the code of the first completion's
tool calls (`lock`, `cas`, `blind_write`, `read`, `message`, `no_call`). In both arms the first completion sees
the same input, so first-reply lock use is the manipulation check (expected equal) and the contended-vs-control
lock contrast measures *reactive* locking.

### 6. Configurations and peer cues (T2 F2, F5; V2 fixes V1 B1, V2 F1, F4)
- **Configs:** `none`, `cas_available`, `locks`, and `all_available` = **CAS + locks** side by side (V2 F4: v1
  also added messages, so its aware-off prompt listed the peer, "Agents you can message: a1", in that config
  only; every `all_available` vs `locks`/`cas_available` comparison was confounded with being told a peer
  exists). No grid configuration offers messages. The message channel survives only in the labelled
  `all_peer_informed` (CAS + locks + messages; peer-informed by definition), used solely for the dry-run channel
  rehearsal and the chaos-model gate, never in the paid grid and never compared with the grid configs.
- **`claim` is a plain overwrite in every configuration (V1 B1).** Under CAS configurations it takes an optional
  `expected_version` exactly like `update_record`. v1 made `claim` a server-side test-and-set under CAS configs,
  so a no-protocol agent was 100 % protected on seat/ticket by the API (98.9 % of Study 1 seat/ticket writes were
  `claim`), and the validity table could not see it. New rows: `naive_claim` (read, then claim; must fail; fails
  0.66–0.78 in every config) and `cas_claim` (correct).
- **Version-visibility confound (V1 text 5).** `locks` hides versions and `all_available` exposes them, so
  `locks` vs `all_available` is confounded with version visibility. Declare it.
- **Description salience (V2 M3).** `acquire_lock` is a long description; the CAS option is one property line.
  Lock share under `all_available` partly measures text salience. Declare it.

| cue in aware-off text | Study 2 |
|---|---|
| claim task "only if it is not held by anyone else" / "unless someone else already holds it" | "only if it has no holder yet" / "only if it is still unassigned" |
| peer record ids in task text (`spend-a1`, `partners-a1`, `dest-a0`) | neutral pool names; the control has the same shape |
| claim tool "Fails with 409 if the record is held by someone else" | removed (claim is a plain overwrite) |
| lock tool "other agents' writes to the record are rejected" (Study 1); "(others get 423)", "(in a round every agent makes at most one tool call)" (v1) | "(writes without it get 423)", "(a round is one scheduling step)" (V2 F1) |
| 423 "locked by another agent"; 409 "held by someone else" | "is locked; writes need the lock's fencing_token" |
| 409 for a stale `expected_version`: "X was modified (expected version 9); current version is 1" (V2; false cue in a control, where only an own invalid version can cause it) | Round 3: one neutral text in both arms, "409 Conflict: write to X rejected: expected_version does not match the record's current version." No version number, no `current_version` field; the CAS property says "otherwise 409." |
| `all_available` prompt "Agents you can message: a1." (v1) | gone: no messages in any grid config (V2 F4) |

**Cues that remain (documented):**
1. Any 423 and any `version_conflict` 409 the agent actually receives, and a peer's value it reads. That is
   observed contention, not a prior cue (the 409 text itself is the same whether a peer or the agent caused it). The 409 `stale_fencing_token` text ("locked again after your lease ended") is such an observed-event
   text.
2. "You are agent a0" and ticket holders equal to agent ids (`a0`, `a1`), visible once a peer has claimed.

A unit test scans every aware-off description, task text and prompt with a widened pattern (V2 F1: v1's pattern
could not match "every agent" or "others", so its test passed with the cue present; the new pattern is tested
against v1's lock text).

**Canonical record order (V2 F5).** Multi-record guard texts (`budget_write_skew`, `joint_account_write_skew`)
list their records in sorted order for every agent; v1 listed the agent's own record first, so a model that
locks in text order always locked in the opposite order from its peer and deadlocked. a0's text is still
identical across arms. **Deadlock is a recorded outcome:** the scheduler builds the lock wait-for graph every
round and records cycles (`deadlock`, `deadlock_rounds`); they resolve when the wait times out. The diagnostic
`lock_own_first` (hold-and-wait, own record first) deadlocks in 24–31 of 32 contended write-skew episodes and is
never failed; `lock_protected` (sorted order) never deadlocks.

### 7. Promotion and compensation are feasible protocols (T1 §5 and §7, T2 F7, T4 M1)
The validity table below is the built-in manipulation check.
- **`promote_before_write`** writes back every guard record conditionally in sorted order, its own record
  included, so all agents contend on the same first record. It is clean 64/64 on both write-skew templates.
  The naive variant `promote_after_write` (own write first) fails 22–34 %.
- **`verify_and_compensate`** works without versions, under `none` too. It ends clean or compensated, with
  the randomized, rank-offset back-off of §4.

### 8. Model settings recorded per completion (T2 §3; V2 fixes V2 §5, F6, F7)
- **Fields per turn:** `temperature_effective`, `reasoning_tokens` (OpenRouter and Gemini), Anthropic
  `thinking_blocks` and `thinking_chars`, `model_served`, `served_host` and `max_tokens_exceeded`. Thinking text
  is kept *when the API returns it*: Anthropic's 5.x migration guide says thinking blocks may arrive with an
  empty text and only a signature, so `thinking_chars` can be 0; the preflight prints it.
- **Unchanged from Study 1:** max_tokens 4096, temperature 0.0 requested, no reasoning or thinking parameter.
- **Truncation is its own end reason (V2 §5).** A reply without a tool call that was cut off ends the agent as
  `truncated` (max_tokens / length) or `provider_error` (finish reason `error`, e.g. Gemini
  `MALFORMED_FUNCTION_CALL`), never `returned`, and never counts as abandonment (`agent_errors` per episode).
- **Refusals and safety stops are their own end reasons (Round 4).** A reply without a tool call that stopped with
  Anthropic `stop_reason == "refusal"` ends the agent as `refusal`; one that stopped with OpenRouter
  `finish_reason == "content_filter"` ends it as `content_filter`. Gemini replies reach the harness through
  `src5_batch/gemini_translate.py`, which maps finishReason SAFETY, RECITATION, PROHIBITED_CONTENT, BLOCKLIST, SPII
  (and the image variants) and every blocked prompt to `content_filter`; the native reason stays in the turn's
  `provider_meta.native_finish_reason`. Same code on the sync, Anthropic batch and Gemini batch paths
  (`model_agent5.REFUSAL_END`, `scheduler5.AGENT_STOP_REASONS`, `score5.REFUSAL_ENDS`). Never abandonment, not
  in `agent_errors`. A refusal-stopped reply that does carry a tool call runs that call as before. Pre-registered
  rule: the harness never re-runs a written episode; an episode with an agent that ended `truncated`,
  `provider_error`, `error`, `refusal` or `content_filter` is excluded with its pair partner and counted per cell
  (`analysis5/analyze5.py`).
- **Qwen routing (V2 F6).** `{"order": ["alibaba"], "allow_fallbacks": false}`. With fallbacks on, an Alibaba
  429 or outage silently re-created Study 1's host mix (DeepInfra changed Qwen's H2 verdict). A completion
  served by another host aborts the episode (counted in spend, never scored, re-run), and the preflight fails
  unless Qwen's served host is Alibaba. Override with `STUDY2_QWEN_PROVIDER`; an empty value disables it.
- **Gemini temperature (V2 §5).** Google's Gemini 4 Argon migration checklist: sampling parameters are
  ignored if provided. The request still carries temperature 0 (Study 1 comparability; it changes nothing) and
  every Gemini completion records `temperature_effective = "ignored_by_provider"`. v1 said Study 2 "keeps
  temperature 0" as if it were applied; it never was, in Study 1 either (correct the Study 1 text and T2 §3).
- **Claude-family confound (carried over):** thinking on (Sonnet, Fable) vs off (Haiku); Haiku accepts
  temperature 0, Sonnet and Fable reject it and run at the default.

### 9 and 10. Planner, budget, runner
See below and `../run_conc_study2.sh`.

## Reference policy validity table (n = 2, 4 instances × 8 schedules per cell, contended and control)

Pass criteria:
- **Correct protocols:** contended outcomes only clean (clean or compensated for v&c), controls only clean,
  0 cap endings, at most 80 % of the cap.
- **Naive policies:** contended failure rate ≥ 0.10, controls clean.
- **Probes:** never failed.
- **Every row:** 0 cross-agent edges in controls, 0 lock-safety violations, and (Round 3) 0 control agents with a
  peer-caused contention signal.

Full per-config table: `validity/validity.md` (with lock attempt/grant/effective shares, stale-basis fenced
writes, lock waits and deadlocks per row, the three-verdict agreement and the write-skew tail).

| family | correct protocol (configs) | contended | max calls / cap | naive policies: contended failure rate |
|---|---|---|---|---|
| inventory_last_unit | cas_retry (cas, all) · lock_protected (locks, all) | 32/32 clean each | 3 · 4 / 24–28 | naive 0.75, rereader 0.59, reacquire_no_reread 1.00, lease_then_tokenless 0.94 |
| inventory_still_valid | cas_retry · lock_protected | 32/32 clean | 4 · 4 | naive 0.84, rereader 0.59, reacquire 1.00, tokenless 0.91 |
| seat_same | cas_retry · cas_claim · lock_protected | 32/32 clean | 3 · 3 · 4 | naive 0.66, naive_claim 0.66 (all 4 configs), rereader 0.56, reacquire 1.00, tokenless 0.91 |
| ticket_same | cas_retry · cas_claim · lock_protected | 32/32 clean | 3 · 3 · 4 | naive 0.78, naive_claim 0.78 (all 4 configs), rereader 0.53, reacquire 1.00, tokenless 0.94 |
| transfer_shared_source | cas_retry · lock_protected | 32/32 clean | 5 · 8 | naive 0.97, rereader 0.78, reacquire 1.00, tokenless 0.97 |
| budget_write_skew | promote_before_write (cas, all) · verify_and_compensate (all 4) · lock_protected (locks, all) | 32/32 · 13 clean + 19 compensated · 32/32 | 13 · 18 · 10 | naive 0.59, rereader 0.34, cas_retry 0.59, promote_after_write 0.59, lock_writes_only 0.50, reacquire 1.00, tokenless 0.94 |
| joint_account_write_skew | same three | 32/32 · 10 + 22 compensated · 32/32 | 13 · 15 · 7 | naive 0.69, rereader 0.50, cas_retry 0.69, promote_after_write 0.50, lock_writes_only 0.56, reacquire 1.00, tokenless 1.00 |

Results:
- **All 186 n = 2 rows pass; 372 rows in all (n = 2 and 4), 0 required failures, 23,808 episodes.**
- **Probes** (`lock_short_lease`, `lock_no_fence`, `lock_own_first`): 0 failed outcomes. `lock_own_first`
  deadlocks in 31/32 (budget) and 24/32 (joint) contended episodes, all resolved, none failed.
- **Locks:** 0 lock-safety violations; 0 of `lock_protected`'s waits end in 423; every `reacquire_no_reread` lost
  update carries `fenced_stale_basis` (1,024 stale-basis fenced writes at n = 2, all from that policy).
- **At n = 4** cas_retry and lock_protected pass everywhere; promote_before_write on joint and
  verify_and_compensate need 39–44 calls, so they are not required at n = 4, and Study 2 runs write-skew at n = 2
  only.
- **Fulfilment is reported per row** (goodput apart from integrity).

## Grid, cost and power under the prepaid caps (V2 grid, review V2 §7, §9)

The caps are per provider (prepaid credit), plus a total, all enforced by `budget5` in `run5.py` and in the
batch driver over every spend log. The plan keeps **at least 10 % headroom** below every family cap after the
1.15 safety factor (`plan5.py --margin 0.10`).

| provider | cap | balance |
|---|---|---|
| Anthropic | $19 | $21.30 |
| OpenRouter | $28 | $31.15, shared with Paper 1 |
| Gemini | $22 | $40 prepaid minus about $15 used |
| total | $69 | |

Each core block also gets a per-model sub-cap of 1.3 × its cumulative estimate.

**Execution paths.** Haiku, Sonnet and Fable run on Message Batches; Gemini on the Google Batch API; Qwen and
GPT-5.5 sync on OpenRouter.

**Cost model (`plan5.py`; Round 3, V2b finding 3).** Episodes: Study 1's observed mean cost for the same model,
n, aware arm, matching config (`all_available` = the dearer of Study 1 `locks`/`cas_available`) and family, × the
execution-price ratio (Haiku 0.5; Gemini 1.0 in November, 2.0 from Dec 1) × the call-cap uplift, **plus the input
cost of the longer Study 2 tool text**: completions × extra tokens × input price. The extra tokens are computed
from the code (`json.dumps(world5.tool_schemas(config))` minus the Study 1 menu, at 3.5 characters per token:
`locks` 3,537 vs 1,976 characters, `all_available` 3,917 vs 1,976, `cas_available` 1,655 vs 1,550), so the
150-round wait text and any later text change are priced. Completions = Study 1 completions per agent × n × the
completions cap uplift; price = the uncached input price on the Study 2 path × the model's Study 1 cache mix
(Sonnet 0.86, Fable 0.53, 1.0 otherwise). This replaces V2's flat 1.10 on `all_available` only (the reviewer
measured +15–30 % on `locks` and +19–38 % on `all_available`). GPT-5.5 also carries its Study 1 re-run waste
(× 1.04). **Probes:** Study 1's mean first-completion cost plus one completion's extra menu tokens. Safety × 1.15;
every provider must keep ≥ 10 % headroom; if not, the planner cuts the descriptive-only models first (GPT-5.5,
Fable) and never the confirmatory cells.

**First-reply probes (priority 0).** One completion per agent from its initial prompt and tool menu; nothing is
executed (`run5 --probe`, same request bodies on the batch path, tested). Per (config × aware off/on × family ×
instance): a0's contended prompt, a1's contended prompt and a1's control prompt (a0's control prompt is
byte-identical to its contended one). Probe K is fixed per model (Round 3: GPT-5.5 cut from 4 to 2; it is at the
lock ceiling in Study 1).

| block | prio | model | grid (n = 2) | episodes | est. $ |
|---|---|---|---|---|---|
| probes | 0 | Qwen / Haiku / GPT-5.5 / Gemini / Sonnet | 4 configs × aware off+on × 7 families × K instances (K = 6 / 4 / **2** / 8 / 4; Fable **0**) | 672 / 448 / 224 / 896 / 448 | 0.95 / 0.66 / 2.80 / 1.55 / 1.25 |
| core | 1 | Qwen, Haiku, Sonnet | 4 configs × aware off × 7 families × (contended + control) × 4 inst × 2 sched | 448 each | 3.10 / 3.02 / 6.91 |
| core | 1 | Gemini 4 Argon | none, cas_available aware off; **locks, all_available aware off and on in the same block** | 224 + 448 | 2.06 + 12.41 |
| core | 1 | GPT-5.5 | 3 families × 2 inst × 2 sched | 96 | 14.52 |
| core | 1 | Fable 5 | **2 families** × 1 inst × 1 sched (descriptive only; Round 3 cut from 3 families) | 16 | 1.92 |
| extensions | 4 | GPT-5.5 / Fable 5 | next levels, only while money is left | 144–192 / 48–96 | — |

Estimated spend by provider (`plan_study2.txt`, "FINAL COST TABLE"):

| provider | estimate | × 1.15 safety | cap | headroom after safety |
|---|---|---|---|---|
| Anthropic | $13.76 | $15.82 | $19 | 16.7 % |
| OpenRouter | $21.37 | $24.58 | $28 | 12.2 % |
| Gemini | $16.02 | $18.42 | $22 | 16.3 % |
| total | $51.15 | $58.82 | $69 | 14.8 % |

Notes on the grid:
- **Why Fable shrank.** With the tool text priced, Anthropic was at $18.80 after safety (limit $17.10). The
  planner's descriptive cuts dropped the Fable probes (saves $1.10), then Fable's third family (16 instead of 24
  episodes). Qwen, Haiku and Sonnet keep 56 episodes per config × arm and their probe K.
- **Gemini pricing.** If Gemini batches end after 2026-11-30T00:00Z the Gemini price doubles ($32.03, × 1.15 =
  $36.83, above the $22 cap); the cap then stops the lane. The runner starts the Gemini lane first.
- **Not covered:** aware on in full episodes for the five non-Gemini models (their aware contrast comes from the
  probes), and n = 4.
- **Families differ by model:** GPT runs 3 families and Fable 2 in full episodes. Cross-model comparisons of
  episodes must be restricted to those families or adjusted for family; probes cover all 7 (not Fable).

**Power (pre-register the cluster as the unit; V1 text 4, V2 M1).** Minimum detectable difference at 80 % power,
α 0.05 two-sided, p = 0.5 worst case. Cluster = family × instance (schedules, agents and arms within a cluster are
correlated, and the two agents of a contended episode interact):

| per model (aware off, episodes) | eps per (config, arm) | clusters | lock use contended vs control (clusters) | integrity config vs none (clusters, paired r 0.3) | agent-level figure (reference only) |
|---|---|---|---|---|---|
| Qwen, Haiku, Sonnet, Gemini | 56 | 28 | 0.37 | 0.31 | 0.19 |
| GPT-5.5 | 12 | 6 | 0.81 | 0.68 | 0.40 |
| Fable 5 | 2 | 2 | not estimable | not estimable | descriptive only |

| probes (per config × aware cell) | a0 probes | all probes | aware on vs off, first reply (all probes, paired r 0.3) |
|---|---|---|---|
| Gemini | 56 | 168 | 0.13 |
| Qwen | 42 | 126 | 0.15 |
| Haiku, Sonnet | 28 | 84 | 0.18 |
| GPT-5.5 | 14 | 42 | 0.26 |
| Fable 5 | 0 | 0 | no probes (Round 3 cut) |

- Lock use contended vs control measures **reactive** locking (the first completion sees identical input in both
  arms). The plausible effect, a fraction of the agents that hit a 409 or 423, is likely 0.05–0.15, below every
  cluster MDD: pre-register it as an **equivalence/bounding** analysis with a stated margin, plus lock use before
  vs after the first contention signal (`protect_before_contention`), not as a superiority test.
- First-reply lock use in contended vs control is the **manipulation check** (expected equal).
- GPT-5.5 is descriptive for M1 and M2 in full episodes (cluster MDDs 0.68–0.81 exceed most achievable effects;
  the naive write-skew failure rate, 0.59–0.69, caps any config-vs-none reduction); Fable is descriptive for
  everything. Both are inferential only through the probes.

## Runner (author's Mac)

`bash run_conc_study2.sh` from the repo root (`~/Desktop/idempotencybench`):
- **Environment:** `.env` holds `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` and `GEMINI_API_KEY`; `.venv` is
  created once.
- **Pattern:** the same autorun pattern as `src4_batch/run_rest.sh` (single-instance guard, lock dir,
  `caffeinate`, log, resume, retry until done).
- **Gates before spending:** `src5/FREEZE.md`, then the validity gate (no cost), then the preflight (Qwen must be
  served by Alibaba; Gemini runs a single-turn and a two-turn parallel-call check).
- **Block order per lane:** priority 0 probes (`--probe`, output `results5/study2/probe-<provider>/`), then the
  core blocks, then extensions. **Gemini first (Round 3):** the Gemini lane is started first (and runs first with
  `--sequential`), since its batch price doubles from 2026-11-30.
- **Pairs (Round 3, V2b finding 4).** Inside a block the grid visits schedule → instance → family → config →
  aware → arm, so every contended episode is followed by its matched control. Both runners admit a pair only if
  the estimate of both fits (per-config estimate: 1.5 × the dearest finished episode in the same config), the
  batch driver advances the pair together through its worst-case gate, and an episode is written to
  `transcripts/` and `results.csv` only together with its partner (until then it waits in `held_for_pair/`; the
  next run completes the pair). A cap stop therefore never leaves a contended cell without its control (tested
  with a fake model and a low fake cap on both paths); `summarize5` and `dry_check5` also check it.
- **Three provider lanes in parallel.** Each provider has its own cap, so lanes cannot overspend each other.
  Blocks run in priority order. Sync models are re-run until every cell is done; rate limits are retried and
  never dropped. Batch models get 5 attempts per block.
- **When a cap binds,** that lane moves on.
- **At the end** it writes `results5/study2/summary.md`.
- **Rehearsal:** `--dry-run` runs the whole grid with fake models (which lock and message when offered) and no
  keys, then a channel rehearsal under the labelled `all_peer_informed` config and `src5_verify/dry_check5.py`.

## Optional free local model (an extra, not a replacement)
- **Setup.** An Ollama-served open-weight model runs through the same OpenAI-compatible path:
  `ollama pull qwen3:8b`, then `python3 src5/run5.py --models ollama:qwen3:8b --out results5/study2/n2 …`
  (`OLLAMA_URL` overrides `localhost:11434`). Cost is 0, its provider family is `local` and no cap applies.
- **Hardware fit.** On a MacBook Air with 16 GB, an 8B model at 4-bit runs at about 10–20 tokens/s, so about
  30–60 s per n = 2 episode, or about 4–7 h for a 448-episode grid overnight. Tool calling is reliable on
  `qwen3:8b` and `llama3.1:8b`; smaller models often emit malformed calls.
- **Status.** Tested offline only (unit test with a mocked endpoint).

## Verification (2026-11-03, after the Round 3 fixes)
See `../CHANGES_V2.md` (Round 3) for the run logs. Summary:
- **tests5:** 87 tests OK (16 new in `Round3Fixes`; each fails on the V2 code).
- **tests_batch + tests_gemini:** 57 tests OK (new: the batch-path low-cap pairing test), with the
  byte-identical-input equivalence gate.
- **Mutation testing** (`src5_verify/mutate5.py`, repo layout copied): **115/115 mutants killed** (24 new for
  Round 3).
- **Validity table:** 372 rows, 0 required failures, 23,808 episodes, 0 control agents with a contention signal.
- **Full dry run** (`run_conc_study2.sh --dry-run`): every lane exit 0, Gemini lane first; 5,160 transcripts
  (2,688 probes); `dry_check5.py` OK (1,180 matched pairs, 0 unpaired, 0 held, 134 version 409s all with the
  neutral text, 0 control contention signals, 0 lock-safety violations).
- **Freeze:** 38 files (`FREEZE.md`), `freeze5 --check` OK.

## Deviations and limits to declare in the Study 2 pre-registration
- **Unequal per-model sample sizes.** Fable (16 episodes, no probes) and GPT-5.5 (96) are small; aware on in full episodes
  is Gemini only (locks, all_available); n = 2 only. Probes cover every model, both aware arms, all 7 families.
- **The graph verdicts and fs disagree** (2,006 of 23,808 validity episodes for the all-reads DSG, 442 for the
  basis DSG), in both directions in general: report all of them.
- **`clean` is specification-level** and can sit on a cyclic committed history.
- **Fencing protects writes, not read-modify-write;** stale-basis fenced writes are flagged, lock use is reported
  as attempted / granted / effective.
- **`locks` vs `all_available` is confounded with version visibility,** and lock share under `all_available`
  partly measures description salience.
- **Write-skew protocols have a livelock tail** (§4).
- **Gemini temperature is ignored by the provider** (sent, recorded as `ignored_by_provider`); Study 1's Gemini
  text must be corrected likewise.
- **Qwen is pinned to Alibaba without fallbacks;** a completion from another host aborts the episode.
- **Lock configurations have a 28-call cap, the others 24:** report cap endings per config and the 24-call
  re-score (`rescore5.py`, with its `indeterminate` count); report `cap_truncated` failures as a stratum.
- **Exposure is the manipulation check of contention:** report the share of contended agents with a peer-caused
  signal per model × config × family (0 in controls by construction and by test); ITT equivalence is
  uninformative where exposure is low.
- **The Gemini model id stays `openrouter:google/gemini-4-argon-20261013`** for continuity with Study 1. It is
  served by the Google Gemini Batch API (`gemini-4-argon`), never through OpenRouter.
- **The OpenRouter key is shared with Paper 1.** The $28 cap counts only Study 2's own spend logs.
- **Not yet written:** the Study 2 pre-registration document itself (review V2 F3). The measures it must define
  now exist in code (`lock` attempt vs `lock_granted`, `first_reply`, `first_protective`,
  `protect_before_contention`, `deadlock`, the `truncated`/`provider_error` end reasons); the rules to state are
  listed in the sections above.
