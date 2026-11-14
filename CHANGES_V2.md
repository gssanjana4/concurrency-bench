# CHANGES_V2: harness v2 pre-spend fixes (2026-11-03)

This file maps every blocker in the two pre-spend reviews to its fix and to the test that proves it:
- `paper-concurrency/review/V1_db_prespend.md` (DB / distributed systems: B1–B6 and the non-blocking items)
- `paper-concurrency/review/V2_agent_prespend.md` (agent evaluation: §8 F1–F9, the §5 settings, the §7/§9 grid)

Scope:
- Code changed: `src5/`, `src5_batch/`, `src5_verify/`, `run_conc_study2.sh`.
- `src4/` and `src4_batch/` were not touched; their sha256 are identical before and after.
- No API calls were made and no money was spent.

Tests are in `src5/tests5.py`, class `V2Fixes` unless another class is named. Mutants are in
`src5_verify/mutate5.py`.

## Blocker → fix → proof

### V1 (database review)

| blocker | fix | test(s) / mutant(s) |
|---|---|---|
| **B1** `claim` was a server test-and-set under CAS configs | `claim` is a plain overwrite in every config, with optional `expected_version` under CAS configs (as `update_record`); "Fails with 409…" removed from the text; conditional claims count as `cas`. New rows: `naive_claim` (naive) and `cas_claim` (correct) on seat/ticket. | `test_claim_is_a_plain_overwrite_in_every_config_and_cas_optional`, `test_naive_claim_fails_under_every_config`; mutants W12 (test-and-set back), W16, S30. Validity: naive_claim fails 0.66 (seat) / 0.78 (ticket) in **all four** configs (was 0.00 under cas/all). Reviewer's C1 script: 1.00 everywhere. |
| **B2** think gap only after a cycle's first read | Gap U{0..4} after every call that ends a turn: `ToolCall.ends_turn`, set by `ModelAgent` on the last queued call of each reply; every scripted yield is its own turn. Back-off is randomized per (schedule seed, agent, attempt) with a rank offset (5 + 2·attempt reads for odd ranks). verify-and-compensate re-reads the records it saw change and declines as soon as fresh values make its guard false. Re-validated. | `test_think_gap_follows_every_turn_not_only_the_first_read`, `test_model_agent_marks_the_last_call_of_each_reply`, `Validity.test_correct_policies_clean_within_cap_naive_fail`; mutants C07, M04, A04. Naive / rereader failure (none): 0.754 / 0.558 (v1 0.643 / 0.321; reviewer's every-read figure 0.754 / 0.558). |
| **B3** 6-round lock wait < correct hold | **48 rounds** (not the reviewer's 24, see "Deviations" below). Tool text states it. | `test_lock_wait_does_not_time_out_against_a_correct_holder` (0 refusals); mutant W17. With B2 in place, correct holds are median 14 / p90 28 / max 42 rounds; 24 refused 36/245 waits, 48 refuses 0/223. |
| **B4** shared token counter, global message ids, messages not edges, dry run never locked or messaged | Per-record fencing-token counters; per-recipient message ids; delivered messages counted in `cross_agent_edges` (`cross_agent_record_edges` and `messages_delivered` kept apart; controls with messages reported apart in summarize5). The dry-run fake model locks every task record (sorted), writes with the tokens, releases, and messages its peers when messaging is offered. Added a channel rehearsal (labelled `all_peer_informed`) and `src5_verify/dry_check5.py` to the dry run. | `test_fencing_tokens_are_per_record_so_controls_leak_nothing`, `test_message_ids_per_recipient_and_delivered_messages_are_cross_agent_edges`, `test_dry_run_model_locks_and_messages`; mutants W18, W19, S23, M05. Full dry run: see below. Reviewer's L4 script: a0's tokens are (1,) whether or not a1 locks (v1: 2 in 5/8). |
| **B5** fencing protects writes, not read-modify-write; steering 409; vacuous probes | 409 `lease_expired` text is now "your lock on X has ended." (renew 409 likewise). New naive rows `reacquire_no_reread` and `lease_then_tokenless`. New per-agent `fenced_stale_basis` count and episode flag; `lock_effective` per agent. The probes are labelled rejection probes. README §1 now says "fenced writes are exclusive; read-modify-write is safe only when the read is inside the same lease". | `test_lease_expired_text_is_neutral`, `test_reacquire_without_reread_is_flagged_and_fails`, `test_tokenless_write_after_lease_end_fails_and_is_not_effective_locking`; mutants W20, S24, A05. Validity: reacquire_no_reread fails 1.00 in every family, with 0 mutex violations and every one of its 1,024 fenced writes flagged; lease_then_tokenless fails 0.91–1.00. |
| **B6** mutex gate ignored leases | Every lock event carries the ledger `seq`. The gate requires each fenced write to lie inside its token's window (grant seq < write seq < end seq), and forbids a committed write by a non-holder (or by the holder without the live token) while a lock is live. | `test_lock_events_carry_ledger_seq`, `test_mutex_gate_catches_a_world_that_accepts_expired_tokens` (8/8; v1 0/8), `test_mutex_gate_catches_a_world_that_lets_non_holders_write`, `test_mutex_gate_catches_a_tokenless_non_holder_write_while_locked`, `test_mutex_gate_is_clean_on_correct_lock_use`; mutants W21, S25, S26. Reviewer's L5 script: 8/8 flagged. 0 violations in 23,808 validity episodes. |

**V1 non-blocking items**

| item | fix | proof |
|---|---|---|
| per-write graph check | `dsg_basis_cycle` (basis DSG; rolled-back sessions aborted), in the score, CSV and validity agreement table | `test_basis_dsg_removes_the_definitional_cas_retry_cycle`; mutant S28. All-reads vs fs: 2,006 disagreements of 23,808; basis vs fs: 442 (292 v&c, 288 of them `compensation_exposed`; 124 promotion no-op versions; 26 naive). |
| retract "every fs failure is cyclic" | README §5 and deviations corrected; score5 docstring says neither direction is implied | `test_fs_failure_can_be_acyclic` (half transfer: fs-nonserializable, acyclic) |
| cluster-level power | plan5 reports cluster (family × instance) MDDs as PRIMARY, agent-level as reference; probe MDDs; README power tables | `plan_study2.txt` |
| locks vs all_available confound | documented (world5 docstring, README §6, deviations) | — |
| `compensation_exposed` false positive (text 6) | only non-final, non-restoring versions count | `test_reading_a_restoring_compensation_version_is_not_exposure`; mutant S29 |
| `clean` includes cyclic committed histories (text 3) | stated in README §5 and deviations | — |
| lock use before/after first contention (text 4) | per agent: `first_protective`, `first_protective_call`, `first_contention_call`, `protect_before_contention` | `test_protection_timing_relative_to_first_contention`; mutant S32 |

### V2 (agent-evaluation review)

| blocker | fix | test(s) / mutant(s) |
|---|---|---|
| **1 (F1)** peer cues in aware-off `acquire_lock` text | "(others get 423)" → "(writes without it get 423)"; "(in a round every agent makes at most one tool call)" → "(a round is one scheduling step)". `PEER_CUES` widened (`every agent`, `others`, `other agent/caller/client`, `peer(s)`, `agents you can message`) and checked against v1's text. The test now scans every tool text, task text and **system prompt** of every grid config. | `ToolContract.test_peer_cue_pattern_catches_the_v1_lock_text`, `ToolContract.test_aware_off_texts_have_no_peer_cues`; mutant W22 |
| **2 (F2)** lock coded only when granted | `lock` (primary, a choice) = any well-formed `acquire_lock` (granted, or 423 after the wait); `lock_granted` is secondary. Also `lock_waits`, `lock_waits_granted`, `lock_waits_423`. CSV: `lock_attempt_agents`, `lock_granted_agents`, `lock_committed_agents`, `lock_effective_agents`, `lock_waits`, `lock_waits_423`. | `test_refused_acquire_counts_as_lock_attempt_not_grant`; mutant S27 |
| **3 (F4)** peer list in `all_available` aware-off prompt | `all_available` = `cas_available+locks` (no messages). No grid config offers messages. The message config survives only as the labelled `all_peer_informed` (peer-informed by definition; `CoordinationConfig.peer_informed`; `PEER_INFORMED_CONFIGS` is disjoint from the grid), used only in the dry-run rehearsal and the chaos-model gate. | `ToolContract.test_all_available_offers_cas_and_locks_without_messages`, `ToolContract.test_aware_off_texts_have_no_peer_cues`; mutant W23; dry_check5 rule 5 |
| **5 (F6)** Qwen fallbacks | `{"order": ["alibaba"], "allow_fallbacks": false}`. A completion served by any other host raises `ProviderFailure`: the episode is aborted (counted in spend, never scored, re-run). The preflight fails unless the served host is Alibaba. | `Runner.test_qwen_host_is_enforced`, `Runner.test_thinking_blocks_recorded_and_qwen_routing`; mutants M01, M02 |
| **6 (F5)** opposite lock orders from the task text | Budget and joint guard texts list their records sorted, the same for every agent (a0's text is still identical across arms). Deadlock is recorded: the scheduler builds a wait-for graph each round (`deadlock`, `deadlock_rounds`, `deadlock_first_step`, `deadlock_agents`; CSV `deadlock`, `deadlock_rounds`). New diagnostic probe `lock_own_first`. | `test_guard_records_listed_in_one_order_for_every_agent`, `test_lock_order_deadlock_is_recorded_and_resolved`; mutants K01, C08. Validity: `lock_own_first` deadlocks in 31/32 (budget) and 24/32 (joint) contended episodes, 0 failed; `lock_protected` 0 deadlocks. |
| **7 (F9)** Gemini aware arms in separate, later batches | The Gemini core block for `locks` and `all_available` runs `--aware both`; `build_grid` places aware off/on of a cell next to each other, so they share batch waves. `plan5 --blocks` emits `both`; the runner passes it. | `Runner.test_planner_fits_every_cap_with_margin_and_the_v2_grid` (Gemini aware-on only in locks/all_available, in `[False, True]` blocks) |
| **temperature** | Gemini 4 Argon ignores sampling parameters (Google's migration checklist). Temperature is still sent; `temperature_effective = "ignored_by_provider"` is recorded. README §8 and deviations corrected. Study 1's text and T2 §3 need the same correction (paper text, not code). | `test_gemini_temperature_recorded_as_ignored`; mutant P01 |
| **max_tokens** | A cut-off reply without a tool call ends the agent `truncated` (max_tokens/length) or `provider_error` (finish reason `error`), via `scheduler5.AgentStop`; it never counts as abandoned; `agent_errors` per episode. | `test_truncated_and_provider_error_end_reasons`; mutants C09, M03, S31 |
| **Gemini preflight** | Two-turn parallel-call check: turn 1 asks for two parallel `get_record` calls; turn 2 returns both function responses. It fails unless turn 1 made ≥ 2 calls, the turn-2 request carries the thought signature on the first functionCall, and turn 2 is answered. Resumable: no double payment. "$330" docstring fixed. Cost: two tiny requests. | `tests_gemini.Plumbing.test_preflight_reports_served_model_and_refuses_another` (runs against the strict fake, which 400s a missing or wrong signature or misordered responses; a model that makes one call fails) |
| **cheaper grid** | First-reply probes (`run5 --probe`, batch driver `--probe`): one completion per agent, nothing executed; for each (config × aware off/on × family × instance) it probes a0 + a1 contended and a1 control (a0's control prompt is byte-identical). The reduced grid is adopted as given. plan5 re-run: see "Final grid" below. | `test_probe_mode_one_completion_nothing_executed_a0_once`, `tests_batch.EquivalenceGate.test_gate_probe_mode_n2` (byte-identical bodies on the batch path); mutants M06, R01, L01 |

**Not in the apply list.** V2 #4 (F3) asks for a written Study 2 pre-registration. It was not in this task's
list and is not written. The measures it must define now exist in code (`lock` vs `lock_granted`, `first_reply`,
`first_protective`, `protect_before_contention`, `deadlock`, the end reasons). README "Deviations" lists the
rules to state.

## Deviations from the reviews' exact proposals (with reasons)

1. **Lock wait 48, not 24 (B3).** The reviewer measured holds under v1's scheduler. B2 adds think time before
   every completion, which lengthens correct holds to median 14 / p90 28 / max 42 rounds. At 24, 15 % of waits
   against `lock_protected` ended in 423, the defect B3 is about; at 48, none did. A longer wait costs rounds,
   not calls or money. Lock-order deadlocks now resolve when the wait times out, since waiting holders make no
   calls and so their leases do not run down.
2. **Back-off (B2 knock-on).** Randomized, as asked, plus a rank offset. Every purely random distribution tried
   (U{1..2+a}, U{1..4+2a}, U{0..4}, U{0..5}, {0,4}, {1,4}, {0,2,4}, exponential) left 1–5 % of write-skew
   episodes above 80 % of the cap on 240–800-episode samples. Raising the write-skew cap to 32 did not remove
   the tail either. The residual tail is reported in validity.md ("Write-skew protocol tail", 8 instances × 50
   schedules):
   - verify_and_compensate on budget: 1/400 above 80 % of the cap, 1 cap ending, 0 failed.
   - promote_before_write on joint: 9/400 (cas) and 5/400 (all) above 80 %, 1 cap ending.
   On the registered validity seeds every correct protocol passes (worst case 18/24 = 0.75).
3. **`lease_then_tokenless` makes 4 innocent calls before its tokenless write.** The reviewer's L2 used 6. With
   only 1, the homogeneous validity row failed in just 0–3/32 episodes.
4. **`lock_effective` is undefined (None) for agents that committed nothing.** An agent that holds a lock and
   correctly declines is neither effective nor ineffective.

## Validity table: what changed

Full table: `src5/validity/validity.md`.

| | v1 | V2 |
|---|---|---|
| rows / required failures | 264 / 0 | **372 / 0** (n = 2: 186 / 186 pass) |
| episodes | 16,896 | 23,808 |
| new rows | — | naive_claim, cas_claim (seat/ticket); reacquire_no_reread, lease_then_tokenless (naive, all families); lock_own_first (deadlock diagnostic) |
| naive failure, inventory_last_unit (none) | naive 0.75 / rereader 0.34 | naive 0.75 / rereader **0.59** |
| naive failure, budget_write_skew | naive 0.38 / rereader 0.34 | naive **0.59** / rereader 0.34 |
| naive failure, joint_account_write_skew | naive 0.31 / rereader 0.25 | naive **0.69** / rereader **0.50** |
| seat/ticket naive under cas_available, all_available | protected by the API (naive_claim 0.00) | naive_claim 0.66 / 0.78 |
| correct protocols, worst calls / cap (n = 2) | 17 / 24 (v&c) | 18 / 24 (v&c); promote 13; lock_protected 10 / 28 |
| v&c contended outcomes (budget / joint) | 80 + 48 comp. / 88 + 40 of 128 | 13 + 19 comp. / 10 + 22 of 32 per config |
| lock waits refused against a correct holder | 141 / 322 (44 %) | **0** |
| mutex gate | grant-only | lease-window and non-holder checks; 0 violations |
| checker agreement | fs vs DSG: 2,136 disagreements of 16,896 | fs vs all-reads DSG 2,006 of 23,808; fs vs basis DSG 442 |
| interleavings (naive, none, n = 2) | 12 patterns, reads overlap 81 % | 11 patterns, 85 %, first mover a0 114 / a1 110 |

## Final grid and cost per provider

`src5/plan_study2.json`, `src5/plan_study2.txt`; safety × 1.15, ≥ 10 % headroom per family, Gemini at the
November price:

| block | models | episodes | est. $ |
|---|---|---|---|
| P0 probes | Qwen K=6, Haiku 4, GPT-5.5 4, Gemini 8, Sonnet 4, Fable 1 (4 configs × aware off/on × 7 families) | 672 / 448 / 448 / 896 / 448 / 112 | 0.84 / 0.59 / 5.02 / 1.24 / 1.12 / 1.02 |
| P1 core | Qwen, Haiku, Sonnet: 4 configs × 7 families × 2 arms × 4 inst × 2 sched | 448 each | 2.70 / 2.67 / 6.09 |
| P1 core | Gemini: none + cas aware off; locks + all_available aware **both** | 224 + 448 | 2.03 + 9.58 |
| P1 core | GPT-5.5: 3 families × 2 inst × 2 sched | 96 | 13.28 |
| P1 core | Fable 5: 3 families × 1 inst × 1 sched | 24 | 3.25 |
| P4 | GPT / Fable extensions, only while money is left | — | — |

| provider | estimate | × 1.15 | cap | 90 % of cap | headroom |
|---|---|---|---|---|---|
| Anthropic | 14.74 | **16.95** | 19 | 17.10 | 10.8 % |
| OpenRouter | 21.84 | **25.12** | 28 | 25.20 | 10.3 % |
| Gemini | 12.85 | **14.78** | 22 | 19.80 | 32.8 % |

Risk: if Gemini batches end after 2026-11-30 the Gemini price doubles. The Gemini blocks would then cost
about 29.6 with safety, more than the $22 cap, and the cap would stop the lane. Run the Gemini lane first.

## Re-verification (final code, `src5/FREEZE.md` re-written, `freeze5 --check` OK, 20 files)

| check | result |
|---|---|
| `tests5` | **71 tests OK** (v1: 43; 28 new, class `V2Fixes` plus the rewritten contract and planner tests) |
| `tests_batch` + `tests_gemini` | **56 tests OK** (v1: 55; new probe-mode equivalence gate; the chaos gate now also runs `all_peer_informed`; the Gemini preflight test covers the two-turn parallel check and its failure) |
| `validity5` (n = 2 and 4, plus the 400-episode write-skew tail) | **372 rows, 0 required failures**, 23,808 episodes, 0 lock-safety violations, 0 cross-agent edges in controls |
| `mutate5` | **91/91 mutants killed** (v1: 58/58). The first run had one survivor, S26 (gate ignoring non-holder writes), which exposed a test that the lease-window check also satisfied; a direct test was added and S26 is now killed |
| full dry run (`run_conc_study2.sh --dry-run`, fake models that lock and message) | **exit 0, all three lanes exit 0**; 5,496 transcripts (anthropic 1,008 probes + 992 episodes, openrouter 1,120 + 640, gemini 896 + 672, channel rehearsal 168); freeze, validity gate and both preflights (incl. the Gemini two-turn parallel check) passed |
| `dry_check5` over the dry run | **OK**. Lock grants in 1,432 episodes, fenced writes in 1,432; 2,288 lock grants in controls, each record's tokens a private 1..k sequence; messages delivered in 56 rehearsal episodes (28 controls, all in `all_peer_informed`, reported apart); 0 control record edges; message ids 1..k per recipient; a0's prompt identical in all 1,180 contended/control pairs; 0 lock-safety violations; every probe one completion, nothing executed, a0 never probed under a control |
| reviewer scripts (`scratchpad/dbrev2`) on the fixed src5 | L4: a0's control tokens (1,) whether or not a1 locks (v1: 2 in 5/8). L5: broken world flagged 8/8 (v1: 0/8). C1: naive_claim fails 1.00 in all configs (v1: 0.00 under cas/all). L1/L2: lost updates remain, by design (fencing cannot prevent them); now flagged and covered by naive rows |
| `src4/`, `src4_batch/` | sha256 identical before and after (58 files) |

Logs: `/tmp/claude-0/-home-claude/7bd43847-0fad-5af6-9555-aaafd42abf90/scratchpad/v2fix/` (`validity_final.log`,
`mutate_final.log`, `batch_tests_final.log`, `dry_run_final.log`); dry-run transcripts in
`/tmp/claude-0/-home-claude/7bd43847-0fad-5af6-9555-aaafd42abf90/scratchpad/dry_v2/`.

---

## Round 3 (2026-11-03): fixes for the re-checks V1b (DB) and V2b (agent evaluation)

Reviews: `paper-concurrency/review/V1b_db_recheck.md`, `V2b_agent_recheck.md`. No API money spent (fake models,
dry runs only). `src4/` and `src4_batch/` untouched: sha256 of all 38 files identical before and after (and equal
to the V1b reviewer's baseline). Every fix has a test in `src5/tests5.py`, class `Round3Fixes` (unless named
otherwise) that fails on the V2 code (checked by running the new tests against a snapshot of V2) and passes now.

| item | fix | test(s) / mutant(s) |
|---|---|---|
| **1. R1 (V1b blocker)** lock wait tuned to the fastest holder | `LOCK_WAIT_ROUNDS = 150` ≥ (max_lease_calls + 1) × (1 + gap_max + latency_max) = 147: the longest hold one non-renewed lease allows. Tool text ("waits up to 150 rounds"), world5 docstring, README §1, `tests5.py:822` updated. | `test_lock_wait_covers_the_longest_lease_hold_slow_holders_never_refused` (bound + slow holders with 2/4/11 extra calls, 0 refusals), `test_longer_wait_changes_nothing_for_the_correct_lock_policy` (ledgers of `lock_protected` byte-identical at 48 and 150); mutants W17, W24. Reviewer probe re-run (`scratchpad/r3/probes/slow_holder.py`, all 7 families × k = 0, 2, 3, 4, 8, 11 × 4 inst × 25 sched): **0 / 4,200 waits refused** (V2: 865 / 4,200; budget k = 2 / 4: 10 % / 35 %, as V1b). Max calls 22 / 28 (budget, k = 11). Validity: every n = 2 row's outcomes and max calls unchanged; `lock_protected` 0 / 446 waits refused at n = 2 (n = 4, not in the grid: 30 / 1,358, was 496 / 1,818, a waiter queued behind three holders); `lock_own_first` episodes end by round 1,241 (`max_rounds` 3,000). Cost: the wait costs rounds, not calls; the one-word text change is priced (item 4). |
| **2. C1 (V2b blocker)** contention signal fired on own actions | `score5.peer_signal_calls`: a signal is a 423; a 409 with `conflict` (`version_conflict`, or `stale_fencing_token` whose latest lock is another agent's); a held acquire; a lock grant on a record another agent had locked (token > 1 not its own); a read of a version another agent installed; an exposed-version write over another agent's version; a delivered message from another agent. Never an own write read back, own `lease_expired`, own `invalid_version`. New per-agent `contention_signals` (exposure), `first_lock_call`, `lock_after_contention`. **Reactive-locking re-check:** a protective call whose own response is the first signal (CAS refused with `version_conflict`, acquire held) was decided before it, so `protect_before_contention` uses `<=` (V2 coded it as reactive). Validity gate: 0 control agents with a signal in every row; dry_check5 rule 9. | `test_contention_signal_is_peer_caused_never_own`, `test_controls_have_no_contention_signal_under_any_reference_policy` (every reference policy + a verify-own-write policy, every config, every family), `test_a_protective_call_that_meets_contention_was_decided_before_it`, `test_reactive_lock_after_a_peer_write`; mutants S33–S38. Reviewer scripts (`v2b/contention_signal.py`, `readback.py`, `v1b/p2_lockscore.py` P5/P5b): controls **0/32** in every case (V2: 32/32); contended exposure e.g. v&c budget 27/32, naive inventory 5/32. Validity: control exposure 0.00 in all 372 rows. |
| **3. V1b S1** locked blind overwrite credited as effective | `fenced_unread_basis`: a committed fenced write needs a successful read of its record by the writer with grant seq < read seq < write seq; `lock_effective` is False otherwise. | `test_locked_blind_overwrite_is_not_effective_locking` (lock → `claim` with token, no read: `lock_effective` False for every committing agent; read-then-lock-then-write: False; `lock_protected`: True); mutants S39, S40. Reviewer P4: 64/64 agents now `lock_effective = False` (V2: True). |
| **4. V2b finding 3** cost omitted the tool text | `plan5`: every estimate adds completions × extra menu tokens × input price, the menu measured from `world5.tool_schemas` (so the 150-round text is in it), Study 1 menu sizes, completions per agent and cache mix added to `study1_costs.json` (`--add-menu-stats`; cells unchanged); GPT re-run waste × 1.04. Probe K fixed per model, **GPT 4 → 2**. If a family misses 10 % headroom the planner cuts descriptive models only: here **Fable probes 1 → 0 and Fable core 3 → 2 families (24 → 16 episodes)**, because Anthropic was at $18.80 after safety (limit $17.10). Qwen / Haiku / Sonnet keep 448 core episodes (56 per config × arm) and their probe K. | `test_planner_prices_the_tool_text_and_keeps_headroom` (menu priced from the code; a longer tool text raises the estimate; ≥ 10 % headroom; GPT K = 2; confirmatory cells 448; input prices agree with `prices.json` and `prices_batch.json`), planner test updated; mutants P02–P04. |
| **5. V2b finding 4** a binding cap cut the grid unevenly | Grid order seed → instance → family → config → aware → model → arm: each contended cell is followed by its matched control (`run5.pair_key`, `pair_groups`). Both runners admit a pair only if the estimate of both fits (per-config estimate, `run5.episode_estimate`); the batch driver holds a pair's partner requests when the worst-case gate holds one arm; an episode is written to `transcripts/` and `results.csv` only with its partner (`run5.commit_episode`; until then `held_for_pair/`, completed by the next run). `summarize5` drops and counts unpaired rows; dry_check5 rule 11. Runner: `LANES=(gemini anthropic openrouter)`, so Gemini starts first (also with `--sequential`). | `test_grid_puts_every_control_right_after_its_contended_cell`, `test_a_cost_cap_stop_never_strands_a_contended_episode` (sync, fake model, four low fake caps: every stop between pairs, nothing held), `test_an_episode_is_written_only_together_with_its_matched_partner`, `test_runner_starts_the_gemini_lane_first`, `tests_batch.Money.test_cost_cap_never_strands_a_contended_episode_without_its_control` (batch path, four low caps, then resume completes the grid); mutants L02–L06. V2 code under the same sync test: 2 / 4 / 2 unpaired rows at three of the four caps. |
| **6. V2b finding 5** 409 "was modified" + current version | One text for every `expected_version` mismatch, identical for `version_conflict` and `invalid_version`: "409 Conflict: write to X rejected: expected_version does not match the record's current version." No `current_version` field; the CAS property says "otherwise 409." Reference policies re-read on 409 (unchanged). | `test_version_mismatch_409_is_neutral_and_identical_in_both_arms` (contended and control responses equal; no "modified", no number, no peer cue; claim too); `Checker.test_laundered_cas_flagged` now launders a guessed version; mutants W25, W26. Reviewer `cue_scan.py` re-run: 23 distinct response texts, only hit "they" (= writes), as before. dry_check5 rule 10. |
| **7. V2b finding 6** freeze did not cover the batch layer | `freeze5` freezes `src5/*.py|*.json` (itself included), `src5_batch/*.py|*.json|*.sh`, `src5_verify/dry_check5.py` and `run_conc_study2.sh` (38 files); `--check` and `harness.verify_freeze` also fail on a frozen file without a row. The runner and the batch driver refuse to start on any mismatch. | `test_freeze_covers_the_batch_layer_and_the_runner`; mutants F01, F02. `mutate5` now copies the repo layout so these run. |
| **8. V1b S3 / V2b note 10** cap stratum and 24-call sensitivity | `cap_truncated` (failed and some agent ended `turn_cap`) and `outcome_stratum` in the score and CSV. `score5.rescore_at_cap` / `rescore5.py`: cut agents after their 24th call and re-score from the logged ledger; `indeterminate` when another agent later touched a record the cut agent changed, locked or held after its cut (never imputed). | `test_cap_truncated_outcome_stratum`, `test_rescore_at_cap_24_equals_a_real_run_at_cap_24_when_determinate` (every determinate re-score equals a real run at cap 24, field for field; transcript round trip); mutants S41–S43. |

Also: per-config admission estimate (lock configs cost more than none/cas), validity table columns for exposure
and cap-truncated failures, README sections updated, `plan_study2.txt` ends with the FINAL COST TABLE and the
PER-CELL n.

**Not done (not in this round's list):** V2b C2 (the written pre-registration), V2b note 9 (Gemini
`content_filter` / Anthropic `refusal` still end `returned`), V1b N8 (malformed acquires excluded from `lock`).

### Final grid and cost (`src5/plan_study2.txt`)

| provider | estimate | × 1.15 | cap | 90 % of cap | headroom |
|---|---|---|---|---|---|
| Anthropic | 13.76 | 15.82 | 19 | 17.10 | 16.7 % |
| OpenRouter | 21.37 | 24.58 | 28 | 25.20 | 12.2 % |
| Gemini | 16.02 | 18.42 | 22 | 19.80 | 16.3 % |
| total | 51.15 | 58.82 | 69 | 62.10 | 14.8 % |

Gemini at the December price: $32.03 (× 1.15 = $36.83) > $22 cap, hence Gemini first.

| model | core episodes | per config × arm | aware on (episodes) | probe K | a0 probes per config × aware |
|---|---|---|---|---|---|
| Qwen | 448 | 56 | — | 6 | 42 |
| Haiku | 448 | 56 | — | 4 | 28 |
| Sonnet | 448 | 56 | — | 4 | 28 |
| Gemini | 672 | 56 | locks, all_available (56 per arm) | 8 | 56 |
| GPT-5.5 | 96 | 12 | — | 2 | 14 |
| Fable 5 | 16 | 2 | — | 0 | 0 |

### Round 3 re-verification (final code; `src5/FREEZE.md` re-written, `freeze5 --check` OK, 38 files)

| check | result |
|---|---|
| `tests5` | **87 tests OK** (V2: 71; 16 new in `Round3Fixes`, all failing on a snapshot of the V2 code) |
| `tests_batch` + `tests_gemini` | **57 tests OK** (V2: 56; new batch-path low-cap pairing test), 17 min |
| `mutate5` | **115/115 mutants killed** (V2: 91). First full run: 113/115. S37 in its first form ("a held acquire is not a signal") is an equivalent mutant (a held acquire always ends in a 423 or in a grant after another agent's lock, both signals) and was re-targeted to "a 423 is not a signal" plus a test; S40 survived because the world-level test helper `sc_of` did not copy the lock events into the ledger (so every fenced write looked unread); the helper now copies them as the scheduler does, and both were re-run against the final suite: killed. Final full run: 114/115 with S40 the only survivor before that helper fix. |
| `validity5` | **372 rows, 0 required failures**, 23,808 episodes, 0 lock-safety violations, 0 cross-agent edges and **0 contention-signal agents in controls**; n = 2 outcomes and max calls identical to V2 in every row |
| full dry run + `dry_check5` | **exit 0, every lane exit 0** (Gemini lane started first); 5,160 transcripts (2,688 probes); dry_check5 OK: 1,180 matched pairs, 0 unpaired, 0 held for a partner, 134 version 409s all with the neutral text, 0 control contention signals, 1,376 lock-config episodes re-scored at 24 (all `unchanged`: the fake model never exceeds 24 calls; the re-scorer is exercised by its unit test) |
| reviewer scripts | V1b `p10_wait`-style slow holder 0/4,200 refused; `p2_lockscore` P4 64/64 not effective, P5/P5b 0 control signals; V2b `contention_signal.py` 0/32 in every control row, `readback.py` 0/32, `cue_scan.py` clean |
| `src4/`, `src4_batch/` | sha256 identical before and after (38 files) |

Logs: `/tmp/claude-0/-home-claude/7bd43847-0fad-5af6-9555-aaafd42abf90/scratchpad/r3/` (`validity_r3.log`,
`mutate_r3_first.log`, `mutate_final.log`, `mutate_S40_final.log`, `batch_tests_final.log`, `dry_run_final.log`,
`probes/slow_holder.py`); dry-run transcripts in `.../scratchpad/r3/dry_final/`.

---

## Round 4 (2026-11-03): refusal and safety stops, H4 measures, filled registration

No API money spent (fake models, dry runs only). `src4/` and `src4_batch/` untouched (sha256 of all 58 files
identical before and after).

| item | fix | test(s) / mutant(s) |
|---|---|---|
| **1. V2b note 9** refusal and safety stops ended `returned` | `model_agent5.REFUSAL_END`: a reply with no tool call that stopped with Anthropic `stop_reason == "refusal"` ends the agent `refusal`; OpenRouter `finish_reason == "content_filter"` ends it `content_filter`. Gemini replies pass `src5_batch/gemini_translate.py`, which already maps SAFETY / RECITATION / PROHIBITED_CONTENT / BLOCKLIST / SPII (and image variants) and blocked prompts to `content_filter`, native reason kept in `provider_meta`. `scheduler5.AGENT_STOP_REASONS` and `score5.REFUSAL_ENDS` added; `NON_FINISH_ENDS` includes them (never abandonment), `ERROR_ENDS` does not (`agent_errors` unchanged). A refusal-stopped reply with a tool call runs its calls as before. One code path for sync, Anthropic batch and Gemini batch. README, score5 / records5 / summarize5 docstrings updated. | tests5 `Round4Refusals` (4 tests: Anthropic sync, OpenRouter sync, every Gemini native + blocked prompt through the translator, constants); `tests_batch.Retries.test_refusal_stop_inside_batches_equals_the_sync_path_and_ends_refusal`; `tests_gemini.Retries.test_every_safety_finish_inside_batches_ends_content_filter_like_the_sync_path` (5 natives, batch = sync) and an end-reason check added to the blocked-prompt test. All fail on a snapshot of the Round 3 code (each with `('returned', True) != (<end>, False)`), and the batch-vs-sync equality asserts in them pass on both. Mutants M07-M15. |
| **2. Analysis vs Round 3 measures** | `analyze5.agent_view` reads score5's columns as stored and recomputes nothing: exposed = `contention_signals` > 0; at risk = exposed and `protect_before_contention` not True; reacting (H4b) = `protect_before_contention` is False; `lock_after_contention` counted for at-risk agents in H4b's output. A transcript without the Round 3 fields raises `ScorerVersionError` (the old fallback that re-derived `<=` is gone). Exclusion also fires on the `refusal` / `content_filter` end reasons. Registration: H4 gate, H4b, Check 2 and Measured variables name these columns and the `<=` rule; Data exclusion names the new end reasons. | tests_analyze5 `Round3Measures` (4 tests: own reply = first signal counts as protecting; reacting read from the stored flag; pre-Round-3 scores refused; field names equal `score5.AgentScore`), exclusion case 9 (`content_filter` end). `DryRunEndToEnd` now runs on the Round 4 dry run with the final plan and fails (never skips) without it; the partial `dry_a5` class (old scorer) was removed; the eligibility test expects Fable (K = 0) uncomputed. |
| **3. Registration filled** | Every `{{N_}}`, `{{COST_}}`, `{{HASH_}}` placeholder filled from `plan_study2.txt`, `FREEZE.md` and sha256 of the analysis files. Per-cell n notes (Fable descriptive only), cost headroom, Gemini price risk ($32.03 / $36.83 at the December price vs the $22 cap; incomplete-lane rule), lane order (Gemini first). Stale facts fixed: fs vs DSG disagreements 1,992 and 428 (were V2's 2,006 / 442); the 409 text is neutral since Round 3 (the confound entry still said "was modified"). | `paper-concurrency/audit/prereg2_factcheck.py`: 0 placeholders, 195 backticked tokens, curated design claims recomputed from code / plan / price files / validity / power outputs, every other number grepped, 44 freeze rows re-hashed, OSF heading map: **0 mismatches**. |
| **4. T3b re-check** | `paper-concurrency/review/T3b_resolution.md`: one line per blocker, should and note (adopted, or deviated with the reason). | |
| **5. Style** | `release/ai_text_audit.py` on the registration: hedge, closer and uniform flags fixed (0 left); the models list became a table. Left: tricolon flags on exhaustive lists of models, fields and conditions, em-dash flags that are Markdown table rules, and the short-sentence profile (intended). | |

### Round 4 re-verification (final code; `src5/FREEZE.md` re-written, `freeze5 --check` OK, 38 files)

| check | result |
|---|---|
| `tests5` | **91 tests OK** (Round 3: 87) |
| `tests_batch` + `tests_gemini` | **59 tests OK** (Round 3: 57), 17.5 min; the batch-vs-sync equivalence gate passes |
| `mutate5` | **124/124 mutants killed** (Round 3: 115; new M07-M15), first run |
| full dry run + `dry_check5` | **exit 0, every lane exit 0**; 5,160 transcripts (2,688 probes), 1,180 matched pairs; dry_check5 OK |
| `tests_analyze5` on that dry run | **46 tests OK**, 0 skipped |

Logs: `/tmp/claude-0/-home-claude/7bd43847-0fad-5af6-9555-aaafd42abf90/scratchpad/r4/` (`batch_tests_r4.log`,
`mutate_r4.log`, `dry_run_r4.log`, `tests_analyze5_r4.log`); dry-run transcripts in `.../scratchpad/r4/dry_r4/`.

**Still open:** V1b N8 (malformed acquires excluded from `lock`, kept as coded and stated).

---

## Round 5 (2026-11-09): macOS bash 3.2 portability of the run script

Found by a no-cost dry run on the author's Mac (`.autorun_conc` job 002, `bash run_conc_study2.sh --dry-run`),
before registration. No Python changed; `src4/`, `src4_batch/` untouched.

| item | fix | check |
|---|---|---|
| `run_conc_study2.sh: line 154: pf[@]: unbound variable` ended every lane after its first block (exit 1) | macOS `/bin/bash` is 3.2, where an empty array expanded as `"${arr[@]}"` under `set -u` is an error (bash 4.4+ allows it). The two optional arrays `pf` (probe flag) and `mc` (model cap) are now expanded as `${arr[@]+"${arr[@]}"}` (5 places); a comment in the header says why. Nothing else changes: with a non-empty array both forms expand identically. | `bash -n`; the same dry run re-queued on the Mac with the paid run's interpreter (`PYTHON=.venv/bin/python`, see below); `freeze5.py` re-written (`run_conc_study2.sh` 76bcfa3f…, `FREEZE.md` e5834fb5…), the registration's Freeze table, `SHA256SUMS.txt` and the OSF files updated to match before filing. |
| Mac dry run also showed `'BatchesWithStreamingResponse' object has no attribute 'results'` in the Anthropic lane | Not a harness defect: in `--dry-run` mode the script uses the system `python3`, whose `anthropic` package on the Mac is old; the paid run uses `.venv/bin/python` (SDK with `messages.batches.with_streaming_response.results`, the path Study 1's batches ran through on the same Mac). The Mac rehearsal is re-run with `PYTHON=.venv/bin/python` through the non-frozen wrapper `run_conc_s2dry.sh` so the paid interpreter is the one exercised. | Mac dry run exit 0 expected; recorded in the run log. |
