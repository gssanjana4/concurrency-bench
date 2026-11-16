# Pre-spend review of Study 3 (design, harness, analysis): findings and fixes

Internal review, 2026-11-14, done as a separate pass after the build: the design note, the registration draft,
the src6 diff against the frozen src5, src6_batch, the runner, dry_check6, analyze6 and its tests were read again
from the start, from three angles (database semantics, agent evaluation, statistics), as in the Study 2 reviews
V1, V2 and T3b. Severity: **B** blocker (would make a registered claim wrong or a test uninformative by
construction, or would spend money wrongly), **S** should fix, **N** note. Every B and S below is fixed; the last
column names the check that shows it.

## Agent-evaluation angle

| id | sev | finding | fix | shown by |
|---|---|---|---|---|
| AE1 | B | **S3-H3 equivalence can be guaranteed by a ceiling.** If the control late agent already protects with probability near 1, contention cannot raise uptake by δ, so the TOST rejects whatever the agents' reactivity. Study 2 uptake was 0.69 to 0.96 under `locks` and 0.92 to 1.00 under `all_available`. The q gate alone (Study 2's) does not catch this. | Second informativeness condition: the control uptake u must leave 1 − u ≥ δ; a cell failing it is "uninformative (ceiling)". Two quantities that are not at a ceiling are added as pre-specified descriptives: D4b (the conditional reaction: at-risk contended late agents against their paired control twins, valid because the at-risk event precedes any divergence of the arms) and D6 (reactive re-read: read-before-lock of late lock users, contended minus control). The registration states the expected ceiling under `all_available`. | `tests_analyze6.H3.test_ceiling_makes_an_equivalence_uninformative`; registration S3-H3, D4b, D6 |
| AE2 | B | **Without a read-visible lock the staggered start would not make S3-H3 informative under `locks`.** In Study 2 a lock or CAS token was in 0 to 12 % of first replies; agents read first. Under `locks` versions are hidden, so a late agent's first read shows nothing, and its only perceivable signal before protecting would be a blind write into a 423. | Bundle part 3: `get_record` returns `locked: true` while another agent holds the lease (never in a control). | `tests6.Study3LockBundle.test_read_shows_locked_only_under_another_holders_lease_and_the_s3_text`, `test_controls_never_see_a_study3_signal`; `dry_check6` (106 locked reads in the dry run, none in a control or under `locks_s2text`) |
| AE3 | S | A first read showing version 2 was counted as a contention signal (Study 2 rule); the agent has no baseline and cannot perceive a change. Using it for q would overstate how many late agents met a signal. | The perceivable set requires a version above one the agent had already seen. The Study 2 set is kept and reported (S8). | `tests6.Study3Scoring.test_first_read_of_a_peer_version_is_a_study2_signal_but_not_perceivable` |
| AE4 | S | A waited acquire under `locks_s2text` is a Study 2 signal but not perceivable (the response looks like an immediate grant). | Only a response that reports `waited_rounds` counts as perceivable. | `tests6.Study3Scoring.test_waits_locked_reads_and_423_are_perceivable_and_timed` |
| AE5 | S | Including a0 in S3-H3 dilutes Δ and q: a0 starts first and rarely meets a signal. | S3-H3 on the late agent a1; both agents in S7. | `tests_analyze6.H3.test_late_agent_only_and_s7_both_agents` |
| AE6 | S | The dry-run fake model of the batch path (`fake_api`) still used the Study 2 fake (lock first, then read), while the sync path used the new varied fake, so the two lanes ran different "agents" and the dry run did not exercise read-then-lock or reactive locks on the batch path. | `fake_api` uses the same `varied_policy`; `dry_check6` rule 17 requires identical call logs for every cell across the three models (the fake does not depend on the model id). | `dry_check6` rule 17 (all 896 cells identical on the final dry run) |
| AE7 | N | The Study 3 lock description is a strong protocol hint ("lock every record your decision depends on"). | Intended (the reviewers asked for a text that asks for reads under the lease); S3-H2 claims are worded as the effect of the bundle, never the text alone; declared confound. | registration, Declared confounds |
| AE8 | N | Staggered episodes are less contended by design (naive and rereader reference policies fail 0 to 63 % of contended episodes, against 47 to 100 % under the together start). | S3-H3 compares arms within the staggered start only; the validity requirement for naive policies applies to the together start. | `validity6` rows |

## Database angle

| id | sev | finding | fix | shown by |
|---|---|---|---|---|
| DB1 | B | **`locks_s2text` must be the Study 2 lock service byte for byte**, or S3-H2 compares two changed texts. | The Study 2 descriptions are kept as constants; the tool schemas of `none`, `cas_available`, `locks_s2text` and `cas_available+locks+s2text` are checked against a fixture written from the frozen src5 (`tools/make_study2_fixtures.py`), as is the system prompt; no Study 3 response field appears under `locks_s2text`. | `tests6.Study3LockBundle.test_s2text_is_the_study2_text_byte_for_byte`, `test_waited_acquire_reports_the_wait_only_under_the_s3_text`; `validity6` gate (b); `dry_check6` rule 13 |
| DB2 | S | `locked: true` is computed from the lock table, where a lease whose last unit was used stays until the holder's next call. | Same semantics as Study 2's writes and waits (such a lock still refuses others' writes); stated in the code. | `tests6.Locks.*` (Study 2 lease tests, unchanged and passing) |
| DB3 | S | A 423 after the full 150-round wait under the Study 3 text carried no `waited_rounds`. | It now does (the 423 itself was already perceivable). | `test_waited_acquire_reports_the_wait_only_under_the_s3_text` |
| DB4 | S | `read_before_lock` must not count a lock holder's correct "lock, read, write" or a write by an agent without a lock. | Defined from `fenced_stale_basis` (a committed fenced write whose basis read precedes its token's grant), only for agents granted a lock that committed a write. | `tests6.Study3Scoring.test_read_before_lock_and_lock_scope` |
| DB5 | N | Distinct amounts change no invariant: "each fits alone, both do not" holds in every distinct-amount family and instance; the post-peer value never equals the agent's own target. | — | `tests6.Study3Instances.*` |
| DB6 | S | The validity gate's call budget (the maximum per row within 80 % of the cap) failed on one clean `promote_before_write` joint-account episode of 32 (24 of 24 calls), the documented livelock tail of optimistic protocols. | The gate uses the 95th percentile of per-episode maxima and still requires 0 cap endings; episodes above 80 % are counted per row and in the tail table. Decided before any Study 3 model data. | `validity6`: 466 rows, 0 required failures |

## Statistics angle

| id | sev | finding | fix | shown by |
|---|---|---|---|---|
| ST1 | B | **One schedule per cluster leaves one binary per arm-cluster.** At 48 clusters (the draft's 6 instances) per-model S3-H2a power at a drop of 0.20 was 0.25 to 0.44 and pooled S3-H3-eq at uptake 0.70 was 0.58. | 8 instances (64 clusters), paid for by dropping `cas_available@staggered`, which no confirmatory test used. Power now 0.36 to 0.59 and 0.80. | `analysis6/power_sims/power6_out.json` |
| ST2 | B | **Size of the TOST with values in {−1, 0, 1}.** A first check put the rejection rate at the boundary at 0.17 to 0.21; that check added the shift to a probability and clipped it at 1, so the realized difference was below δ (not a null). | The shift is calibrated so that the realized mean difference equals δ: size 0.043 to 0.053 at α per model and pooled, at most 1.2 × nominal at α/6 and α/2. | `power6.py` rows `H3-eq-size-at-boundary` |
| ST3 | S | S3-H2b conditions on being a lock user that committed a write; the bundle can change who that is (selection). | S9 reruns S3-H2b with every agent in the denominator; eligible counts are reported; declared. | `analyze6.sensitivities` S9; `tests_analyze6.EndToEnd` |
| ST4 | S | The statistical core must be the frozen Study 2 code (the registration says so). | `analyze6` carries it verbatim; a test compares `signflip`, `boot`, `tost_side`, `t_interval`, `family_level` and `holm` with `analysis5/analyze5.py` on random inputs; only the seed string differs. | `tests_analyze6.Core.test_statistical_core_equals_the_frozen_study2_code` |
| ST5 | S | S3-H1's family has 16 members, but the power table was computed at the first step of 12. | Recomputed at α/16. | `power6_out.json` |
| ST6 | S | The registration cited Study 2 definitions "osf.io/zj3an", whose registration is embargoed until 2027, so readers could not check them. | The registration points to the public copy (repository `preregistration/PREREGISTRATION_STUDY2.md` and the archived record) and restates every new definition in full. | registration, Measured variables |
| ST7 | N | The S3-H1 family contains cells that will almost surely reject (Study 2: 0.21 to 0.80); the replication is a check of the new instances and seeds, not a new finding. | Stated in the registration. | — |
| ST8 | N | Clusters are instances of a family; with the family as the unit the smallest attainable p over 8 families is 2⁻⁸ = 0.0039 (S4 reports it for every cell). | — | `analyze6` S4 |

## Money and process

| id | sev | finding | fix | shown by |
|---|---|---|---|---|
| MP1 | B | With 8 instances the Anthropic lane at the first caps ($28 / $17) had 9.3 % headroom after the 1.15 factor, below the 10 % rule. | Caps $29.50 / $15.50 / $45 total (13.9 %, 13.5 %, 13.7 %); the total cannot pass $45 plus one completion; $5 of the $50 stays unspent. | `plan6.py`, `tests6.Runner.test_planner_fits_every_cap_with_margin_and_the_study3_grid` |
| MP2 | S | The registration gate lived in a non-frozen wrapper in Study 2. | `run_conc_study3.sh` itself refuses a paid run without `.study3_registered`. | runner, line "Study 3 is not registered yet" |
| MP3 | N | The Mac's paid interpreter (`.venv/bin/python`, macOS) cannot be exercised from the device bridge (a Linux VM). The no-cost rehearsal ran on the Mac's frozen files in the VM (Python 3.10): 2,688 transcripts, dry_check6 OK, analysis identical to `analysis6/out`. | The rehearsal with the paid interpreter is one command for the author (`PYTHON=../../.venv/bin/python bash run_conc_study3.sh --dry-run --base results6/study3_dry_mac`). | `STUDY3_RUN_NOTES.md` |

## Re-review

After the fixes, the same files were read again against this list. Results of the final checks:

- `src6/tests6.py`: 105 tests OK (also under Python 3.10 on the Mac's VM); `src6_batch/tests_batch.py`: 24 tests OK
  (equivalence gate of the sync and batch paths included).
- `analysis6/tests_analyze6.py`: 18 tests OK, with the end-to-end block on the final dry run.
- Validity table (`validity6.py`): 432 rows, 0 required failures.
- Final dry run (`run_conc_study3.sh --dry-run`): both lanes exit 0; 2,688 transcripts; `dry_check6` OK, including the
  identical call logs of all 896 cells on the sync and batch paths, 318 locked reads and 462 reported waits under the
  Study 3 text and none in a control or under `locks_s2text`, 0 stagger violations.
- Registered analysis on the final dry run: 38 tests run (6 stage-2 cells gate-closed), all checks pass; outputs in
  `analysis6/out/` (hashes in the registration's Freeze table).
- `freeze6.py --check`: FREEZE OK (32 files); `tools/freeze_table.py --check PREREGISTRATION_STUDY3.md`: OK.
- No open blocker. Items left to the author are listed in `STUDY3_RUN_NOTES.md` and the report.
