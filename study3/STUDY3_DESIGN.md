# Study 3 design (version 2 of the concurrency paper)

Status: built and dry-run tested, not run. No paid call has been made. The registration text is
`PREREGISTRATION_STUDY3.md`; if the two disagree, the registration governs.

## Why Study 3

Both final internal reviews named the same three design limits of Study 2 (F1 S4, S12; F2 "Score"):

1. Every numeric instance gave both agents the same amount, so after the peer's write a record held exactly the value
   the agent's own write would have produced. The half-done transfers that reported success (35 of 35) and the
   Haiku 4.5 "sales" never written (22) both rest on that end-state matching.
2. The lock text never asked for reads under the lease, and a waited acquire looked like an immediate grant (only
   the token differed). Read-then-lock was the commonest lock failure (Study 2, post hoc).
3. With a simultaneous start, almost no agent met a perceivable signal before it protected, so S2-H4 was
   uninformative (q = 0.04 to 0.12).

## Design (what changed from the draft in the brief, and why)

| item | draft | Study 3 | reason |
|---|---|---|---|
| distinct amounts | transfer, budget, joint | also both inventory families | the inventory false-sale reports (F1 S2) have the same end-state-matching cause; cheap |
| same-amount contrast | `transfer_same_amount` | same | |
| lock bundle | text + reported wait | text + reported wait + **`locked: true` on reads** under another holder's lease | In Study 2 a lock or CAS token was in 0 to 12 % of contended first replies (agents read first); under `locks` versions are hidden, so a late agent's first read shows nothing and the only perceivable signal before protecting would be a blind write into a 423. Without a read-visible lock, q under `locks` would again be near the at-risk floor. Cost: S3-H2 tests a bundle of three parts, not the text alone (declared). |
| staggered conditions | cas, locks, all | **locks, all** | no confirmatory test used `cas_available@staggered`; the money went to more instances |
| instances | 6 per family (48 clusters) | **8** (64 clusters) | one schedule per cluster gives one binary per arm; at 48 clusters per-model H2a power at a 0.20 drop was 0.32 to 0.44, pooled H3-eq at uptake 0.70 was 0.58; at 64 clusters 0.36 to 0.59 and 0.80 |
| S3-H1 configs | cas, locks, all | cas, **locks_s2text**, locks, all | `locks_s2text` is the literal Study 2 lock condition: the cleanest replication |
| S3-H1 tests | difference | difference only | Study 2 found 0.21 to 0.80; equivalence is not in question |
| S3-H3 unit | both agents | **the late agent a1** | a0 starts first and rarely meets a signal; including it halves q and Δ |
| perceivable read signal | a read showing a version another agent installed | the same, **only above a version the agent had already seen** | a first read of version 2 has no baseline: the agent cannot perceive that anything changed |
| validity gate, call budget | max calls <= 80 % of cap | **95th percentile** <= 80 %, no cap ending | one clean `promote_before_write` joint episode of 32 used 24 of 24 calls (the known livelock tail) |
| registration gate | wrapper script | **inside the frozen runner** (`.study3_registered`) | |

Stagger: a0 starts in round 1 + U{0..2}; a1 starts U{5..10} rounds after a0. Calibration (design data only, no
estimate): in Study 2 control `locks` timelines, a1's first call at a0 start + 5 to 10 rounds falls inside a0's lock
window in 0.62 to 0.80 (Sonnet), 0.59 to 0.80 (Haiku), 0.43 to 0.61 (Qwen) of episodes; with the read flag that read
is a perceivable signal before a1 protects.

## Grid

Three confirmatory models, n = 2, aware off, one schedule (index 0) per start mode, both arms:

- together: `none`, `cas_available`, `locks_s2text`, `locks`, `all_available`
- staggered: `locks`, `all_available`
- 8 families (7 Study 2 families with distinct amounts where numeric, plus `transfer_same_amount`) x 8 instances

7 x 8 x 8 x 2 = 896 episodes per model, 2,688 in all. No probes, no descriptive models.

## Hypotheses (registered text governs)

- **S3-H1** (together): contention adds integrity failures (`fs_nonserializable`, contended minus control) under
  `cas_available`, `locks_s2text`, `locks`, `all_available`. One-sided sign-flip; per model and pooled; one Holm
  family of 16. Calibration under `none` at raw alpha.
- **S3-H2a** (together, contended): `fs` under `locks_s2text` minus under `locks` > 0. Holm over 4 (3 models + pooled).
- **S3-H2b** (together, both arms): read-before-lock share among agents granted a lock that committed a write,
  `locks_s2text` minus `locks` > 0. Holm over 4.
- **S3-H3** (staggered, `locks` and `all_available`, a1): Δ = uptake (contended) minus uptake (control); TOST
  (δ 0.25 per model, 0.15 pooled; pooled stage gates the per-model stage) and difference (Holm over 8); equivalence is
  informative only if q (share of contended a1 with a perceivable signal before any protection) > δ.
- Pre-specified descriptive D1 to D5: amounts (half-done transfers and success reports, distinct vs same), lock
  mechanisms (read-then-lock, guard records not locked, no lock), protocol order and lock scope, reacting share
  among at-risk late agents, failure by family.

## Power (analysis6/power_sims/power6.py, 2,000 runs, B = 1,000, 64 clusters, one episode per arm-cluster)

| test | setting | per model | pooled |
|---|---|---|---|
| S3-H1-diff | control 0.02, Δ 0.15 / 0.20 | 0.47 / 0.76 at α/16 | 0.99 / 1.00 at α/16 |
| S3-H2a | base 0.35 to 0.80, drop 0.20 | 0.36 to 0.59 at α/4 | 0.87 to 0.98 |
| S3-H2a | drop 0.25 | 0.58 to 0.86 | 0.98 to 1.00 |
| S3-H2b | base 0.40 to 0.95, drop 0.15 | 0.51 to 0.79 at α/4 | 0.93 to 1.00 |
| S3-H3-eq at Δ = 0 | uptake 0.70 / 0.85 | 0.57 / 0.88 at α/6 | 0.80 / 0.96 at α/2 |

Informativeness of S3-H3 also needs room: control uptake at most 1 − δ (review AE1). Study 2 uptake under
`all_available` was 0.92 to 1.00, so that cell is expected to be uninformative; D4b and D6 then carry the reaction.

Size of the TOST at its boundary with one binary per arm-cluster (realized difference = δ): 0.043 to 0.053 at α,
at most 1.2 x nominal at α/6 and α/2.

## Cost and caps

Estimate from the observed Study 2 cost of the same model, config, family and arm (`src6/study2_costs.json`, 1,344
Study 2 episodes, $12.61), plus the longer Study 3 tool text (109 tokens per completion under `locks` and
`all_available`) and 150 tokens per completion for the new response fields, staggered x 1.10:

| provider | estimate | x 1.15 | cap | headroom |
|---|---|---|---|---|
| Anthropic (Haiku $9.17, Sonnet $12.91) | $22.09 | $25.40 | $29.50 | 13.9 % |
| OpenRouter (Qwen) | $11.66 | $13.41 | $15.50 | 13.5 % |
| total | $33.75 | $38.81 | $45.00 | 13.7 % |

Approved budget $50; the caps sum to $45, so at least $5 stays unspent. Admission is per matched pair (sync) and per
batch wave (batch) against the worst case, so overshoot is at most one completion. Per-model sub-caps: 1.6 x the
estimate (Haiku $14.68, Sonnet capped by the lane). A binding cap drops whole later instances (instance-major visit
order); a test needs 48 of its 64 clusters.

## Files

- `src6/` harness (copy of src5, changes marked "Study 3" in each docstring), `src6_batch/` (batch path without
  Gemini), `src6_verify/dry_check6.py`, `run_conc_study3.sh`, `analysis6/analyze6.py`, `analysis6/balance6.py`,
  `analysis6/tests_analyze6.py`, `analysis6/power_sims/`, `tools/` (fixture builders, run once from the frozen
  Study 1 and Study 2 files).
- `PREREGISTRATION_STUDY3.md` (to file on OSF), `PRESPEND_REVIEW_S3.md` (internal review and fixes),
  `src6/FREEZE.md`.
