# OSF Preregistration: Study 3

Fields follow the OSF Preregistration template, as in the Study 1 (osf.io/a5vec) and Study 2 (osf.io/zj3an)
registrations. Each `##`/`###` heading below is one OSF form field.

This registration is filed before any paid Study 3 call, the preflight included. The frozen code (see Freeze)
implements what it describes. If code and text disagree, this text governs, and we report the difference as a
deviation.

## Title

Do LLM agents coordinate on shared records? Study 3: distinct amounts, a lock text that asks for reads under the lease, and a staggered start

## Authors

Sanjana Gopnal Swamy, independent researcher.

Linked registrations: Study 1, osf.io/a5vec; Study 2, osf.io/zj3an.

## Description

Two LLM agents, each in its own conversation, act on the same versioned records through tool calls. A seeded
scheduler interleaves their calls. Every contended task has a matched control in which each agent has a private copy
of the records. Scoring is deterministic, from a ledger and the server call log. There is no LLM judge.

**Why Study 3 exists.** Study 2 (osf.io/zj3an) left three limits that our internal reviews of the reported studies
named and that re-analysis cannot remove:

- Every numeric instance gave both agents the same amount. After the peer's write, a record then held exactly the
  value the agent's own write would have produced. The half-done transfers that reported success and the sales
  reported but never written may come from that coincidence.
- The lock text never asked the agent to read under the lease, and a lock granted after a wait looked like an
  immediate grant (only the token differed). Reading before locking was the commonest lock failure (post hoc).
- Both agents started together. Almost no agent met a perceivable sign of the other before it protected, so the
  Study 2 test of reactive uptake (S2-H4) was uninformative (q = 0.04 to 0.12).

Study 3 removes the three: distinct amounts, a lock bundle that asks for reads under the lease and reports waits and
locks, and a staggered start in which the second agent begins after the first. It uses a new harness (`src6`, a copy
of the Study 2 harness `src5` with these changes) and the same three confirmatory models and execution paths. Study 1
and Study 2 data enter no Study 3 estimate.

## Hypotheses

### Common definitions

- **Arm.** Contended (template `T`) or control (`T_ctrl`). In `T_ctrl` each agent has a private copy of `T`'s record
  group, with the same record count, amounts and wording and a different group tag. a0's prompt is byte-identical in
  the two arms; a1's differs only in the group tag.
- **Pair.** A contended episode and its control with the same model, config, start mode, family, instance and
  schedule index. The two share the schedule seed and run as a pair.
- **Cluster.** Family × instance, within a model: 8 families × 8 instances = 64 clusters. Agents, arms and configs
  are aggregated inside a cluster first.
- **Condition.** A config and a start mode (Study design).
- **Primitive.** A lock (`acquire_lock`) or a conditional write (a write with `expected_version`).
- **Confirmatory models.** Qwen3.6-27B, Claude Haiku 4.5 and Claude Sonnet 5. There are no descriptive models and no
  first-reply probes. Study 2 found all three models eligible for its reactive-uptake test, so Study 3 has no
  eligibility rule.
- **Late agent.** Under the staggered start, a1 (it starts 5 to 10 rounds after a0).
- **Perceivable signal.** A response that itself shows the agent that something else acted on its records (Measured
  variables): a 423; a 409 conflict (`version_conflict`, or `stale_fencing_token` after another agent's lock); an
  `acquire_lock` response that reports a wait (`waited_rounds`, Study 3 lock text only); a read showing `locked: true`;
  a read showing a version, installed by another agent, above the highest version of that record the agent had
  already seen. A first read of a record whose version another agent installed is not perceivable (no baseline).
- **Pooled.** The equal-weight mean over the three models, on the clusters that enter for every pooled model. One
  resample or sign flip acts on all models at once. A pooled test needs at least 2 models.
- **Holm families.**
  - S3-H1: one family over its per-model and pooled difference tests (up to 16).
  - S3-H2a: up to 4 (3 models, pooled). S3-H2b: up to 4.
  - S3-H3-eq, stage 1: the pooled TOST in `locks` and in `all_available` (2), Holm at α = 0.05. Stage 2: the
    per-(model, config) TOSTs (up to 6), tested only if both stage-1 tests were run and rejected; otherwise each
    stage-2 cell is reported with its estimate and 90 % interval and labelled "not tested (gate closed)".
  - S3-H3-diff: one family (up to 8).
  - No correction across hypotheses; sensitivity S3 applies Holm across all confirmatory tests within each model.

### Confirmatory

**S3-H1. Contention adds integrity failures (replication).**

- Setting: together start; configs `cas_available`, `locks_s2text`, `locks`, `all_available`; both arms.
- Statistic: per cluster, d = mean over its complete pairs of [`fs_nonserializable`(contended) −
  `fs_nonserializable`(control)]. Δ = mean of d over clusters.
- Test: H0 Δ ≤ 0 against Δ > 0, one-sided sign-flip; per model and pooled per config.
- Claim if it rejects: "Contention added integrity failures under config C (Δ = x, 95 % [l, u])." A non-rejection
  supports no claim and is not evidence of no effect.
- Expected: Δ > 0 in every cell (Study 2: 0.21 to 0.80 per model and config).
- **Calibration under `none`** (no Holm, raw α = 0.05, per model and pooled): the same test. With versions hidden and
  no primitive, most families have no correct protocol, so we expect Δ > 0. It checks that the contrast can detect
  failures; it is not a finding about agents.

**S3-H2. The Study 3 lock bundle against the Study 2 lock text.**

The two configs offer the same primitives and hide versions; they differ only in the lock bundle (Study design):
`locks_s2text` has the Study 2 lock text and responses, byte for byte; `locks` has the Study 3 bundle.

- **S3-H2a (integrity).** Together start, contended arm. Per cluster, d = `fs_nonserializable`(`locks_s2text`) −
  `fs_nonserializable`(`locks`), same family, instance and schedule. Δ = mean over clusters. H0 Δ ≤ 0 against Δ > 0
  (the bundle lowers failures), one-sided sign-flip; per model and pooled; Holm over 4.
- **S3-H2b (reads under the lease).** Together start, both arms. Among agents granted a lock that committed a write,
  the share with `read_before_lock` True (a committed fenced write whose basis read of the written record precedes the
  grant of the token it carries). Per cluster, d = share(`locks_s2text`) − share(`locks`), each share over the
  cluster's eligible agents of both arms; a cluster enters only with at least one eligible agent in each config.
  H0 Δ ≤ 0 against Δ > 0; one-sided sign-flip; per model and pooled; Holm over 4.
- Claims if a test rejects: "The Study 3 lock bundle lowered contended integrity failures (S3-H2a) / the
  read-before-lock share of lock users (S3-H2b) by x (95 % [l, u])." Each claim names the bundle, never the text alone.
- Expected: both Δ > 0. Study 2 read-before-lock shares among such agents under `locks` were 0.39 to 0.99 by model,
  and the contended failure shares 0.34 to 0.82.

**S3-H3. Reactive uptake of the late agent is small (equivalence), with an informativeness gate.**

- Setting: staggered start; configs `locks` and `all_available`; both arms; the late agent a1 only.
- Uptake: under `locks`, `lock` (a well-formed `acquire_lock` attempt); under `all_available`, `first_protective` is
  not None (lock or CAS).
- Statistic: per cluster, d = mean over complete pairs of [uptake(a1, contended) − uptake(a1, control)]. Δ = mean of
  d over clusters. a1's first completion sees the same input in both arms apart from the group tag (check C1), so Δ
  arises after the first completion: the total effect of contention on the late agent's uptake.
- Test S3-H3-eq (TOST): H0 |Δ| ≥ δ, δ = 0.25 per (model, config), 0.15 pooled; TOST p = the larger one-sided p;
  gatekeeping as above.
- Test S3-H3-diff: H0 Δ ≤ 0 against Δ > 0.
- **Informativeness gate, two conditions.**
  - Enough agents at risk: q = mean over the cell's clusters of the share of contended late agents at risk (a
    perceivable signal, `perceivable_signals` > 0, and `protect_before_perceivable` not True) must exceed δ.
  - Room for a reaction: u = mean over the cell's clusters of the control late agents' uptake must leave at least δ
    below 1 (1 − u ≥ δ). If nearly every control agent protects anyway, contention cannot raise uptake by δ, and an
    equivalence says nothing about reactivity.
  - For a pooled test, q and u are the means over the pooled models of their values on the pooled clusters.
  - An equivalence in a cell that fails either condition is reported as uninformative, with the reason. Otherwise it
    is reported with the implied bound on the reacting share of at-risk late agents, δ / q.
- **Reading per cell, and the claim allowed** (pooled tests read the same way):

  | S3-H3-eq | S3-H3-diff | claim |
  |---|---|---|
  | rejects | does not | "Contention changed the late agent's primitive uptake by at most ±δ (Δ = x, 90 % [l, u]; q = y)." |
  | does not | rejects | "Contention raised the late agent's primitive uptake (Δ = x, 95 % [l, u])." |
  | rejects | rejects | "Contention raised the late agent's primitive uptake, by less than δ (Δ = x, 90 % [l, u])." |
  | does not | does not | "Inconclusive (Δ = x, 90 % [l, u])." No direction is claimed. |

  "S3-H3-eq rejects" here also needs the cell to be informative (both conditions above) and the equivalence to hold
  under sensitivity S5. A cell that fails either is read as if S3-H3-eq did not reject, and the reason is stated. A
  gate-closed cell counts as "does not". If check C1 rejects for a model, its S3-H3 result is described as the total effect of the
  contended template, not as reactive uptake.
- "Small reactive uptake" in a config requires the pooled reading "at most ±δ" there. Otherwise the paper says
  "reactive uptake could not be bounded below δ".
- Expected: under `locks`, q well above δ (the late agent tends to read while a0 holds a lock and is shown
  `locked: true`) and Δ near 0. Study 2 uptake under these configs was 0.69 to 0.96 per arm under `locks` and 0.92 to
  1.00 under `all_available`, so the room condition is expected to fail under `all_available` and may fail for some
  models under `locks`; those cells are then uninformative, and the conditional reaction (D4b) and the reactive
  re-read (D6) are the reported quantities. Under `all_available` a0 locks less often (0.21 to 0.39 in Study 2), so q
  may also fall below δ there.
- A lock or CAS call whose own response is the first perceivable signal (an acquire that waited, a CAS refused with
  `version_conflict`) was decided before that signal: protection before contention (`≤`), so that agent is not at risk.

### Pre-specified checks (not hypotheses)

1. **C1 Leakage, from the late agent's first completion.** Units (config, start, family, instance) under
   `locks_s2text`, `locks` and `all_available`, both start modes, with both a1 episodes. d = first-reply lock token of
   a1 (contended) − of a1 (control). Two-sided sign-flip per model, α = 0.05, no Holm. A rejection means the group tag
   may leak the arm.
2. **C2 Exposure** (manipulation check of contention): per model × condition, the share of contended agents with a
   perceivable signal, with a Study 2 signal, and the share of late agents at risk. Every control agent must show 0
   on both signal definitions; a control agent with a signal is a scorer bug: fixed, all episodes rescored, reported
   as a deviation.
3. **C3 Isolation and lock safety.** `cross_agent_edges` = 0 in every control episode; `mutual_exclusion_violations`
   empty in every episode.
4. **C4 Stagger.** In every staggered episode a1's first call comes at least 5 rounds after a0's start round.

### Pre-specified descriptive (no test, no Holm)

- **D1 Amounts.** Per model × config (together) × family, contended: agents with a half-done multi-record write
  (`missing_leg`), how many of them reported success, and agents with no committed write that reported success.
  "Reported success": the agent's final reply matches the Study 2 success pattern and not its negation pattern
  (`analysis6/analyze6.py`, `SUCCESS_RE`, `NEGATION_RE`, copied unchanged from the Study 2 descriptive script).
  The amount contrast is `transfer_shared_source` (distinct amounts) against `transfer_same_amount` (the Study 2 rule),
  under `cas_available` and `all_available`; it is reported with counts and no test.
- **D2 Lock-failure mechanisms** (the Study 2 post hoc rules, now pre-specified), among fs-failed contended episodes
  under the three lock configs and both starts: read-then-lock (a stale overwrite by a fenced write whose basis read
  precedes its token's grant), guard records not locked (write skew and some agent not granted locks on every record
  its intent reads), no lock (a stale overwrite by an unfenced write); exactly one, more than one, none.
- **D3 Protocol order and lock scope** per model × lock config × start × arm: lock first, read then lock, no lock;
  lock scope all, own, none on the multi-record families; the read-before-lock share and the share of lock users with
  a fenced write not based on a read under its lease (`fenced_unread_basis`).
- **D4 Reacting share** among at-risk contended late agents (staggered, `locks` and `all_available`): the share whose
  first protective call came after the first perceivable signal, cluster bootstrap 95 % interval.
- **D4b Conditional reaction.** Among contended late agents at risk, uptake minus the uptake of the paired control
  late agent (same seed, so the same start round, first-call round and first-completion input: the at-risk event
  precedes any divergence of the two arms). Cluster value = mean over its at-risk pairs; cluster bootstrap 95 %
  interval; no test.
- **D6 Reactive re-read.** Among late agents granted a lock that committed a write (staggered), the read-before-lock
  share, contended minus control, per cluster (clusters with such an agent in both arms); cluster bootstrap 95 %
  interval; no test. It shows whether a reported wait or a locked read makes agents read again under the lease.
- **D5** `fs_nonserializable` per model × condition × family × arm.
- Outcome classes, fulfilment, cap endings, deadlocks, lock waits (reported and 423), cost and tokens per cell.

## Design plan

### Study type

Experiment on software agents. No human participants. All factors are crossed; the randomised elements are the
instance draws and the schedule seeds.

### Blinding

No blinding is involved. Scoring is automated from ledgers and call logs. The harness, scorer, instances, price
tables, plan, run script and analysis script are frozen before any paid call (see Freeze).

### Study design

**Models and execution paths** (as in Study 2):

| model id | path | note |
|---|---|---|
| `openrouter:qwen/qwen3.6-27b-20260422` | OpenRouter, sync | routed `{"order": ["alibaba"], "allow_fallbacks": false}` |
| `claude-haiku-4-5-20251001` | Anthropic Message Batches | |
| `claude-sonnet-5` | Anthropic Message Batches | undated alias |

**Configs.**

- `none`: blind writes, versions hidden, last writer wins.
- `cas_available`: versions visible; `update_record` and `claim` take an optional `expected_version` (409 on
  mismatch).
- `locks_s2text`: fenced locks with own-call leases, versions hidden, with the Study 2 lock text and responses byte
  for byte (tested against the frozen Study 2 harness).
- `locks`: the same lock service with the **Study 3 lock bundle**:
  1. the `acquire_lock` description adds: "Acquire the lock before you read a record you will update, and lock every
     record your decision depends on: the records your condition reads as well as the ones you write. A value you
     read before the lock was granted may be out of date." and "a call that waited says so in its response
     (waited_rounds)";
  2. an `acquire_lock` that the scheduler held returns `waited_rounds` and the note "The record was locked when you
     asked; this call waited k rounds before the lock was granted. Values you read before this grant may be out of
     date." (a 423 after the full wait also returns `waited_rounds`);
  3. while a record is locked under a lease the caller does not hold, `get_record` returns `locked: true`; its
     description says so.
  No other text or response differs from `locks_s2text`. In a control no other agent can lock an agent's records,
  so parts 2 and 3 never occur there (tested).
- `all_available`: CAS and locks side by side, with the Study 3 lock bundle.

No config offers messages. `claim` is a plain overwrite in every config. Lock semantics are Study 2's: per-record
fencing tokens, leases counted in the holder's own calls (1 to 20), a refused acquire held up to 150 rounds, locks
released when an agent ends.

**Start modes.**

- `together` (Study 2): each agent starts in round 1 + U{0..6}.
- `staggered`: a0 starts in round 1 + U{0..2}; a1 starts U{5..10} rounds after a0. The offset was chosen on Study 2
  control timelines (design data, not an estimate): a1's first call then tends to fall while a0 holds its lock.

**Conditions.** Together: `none`, `cas_available`, `locks_s2text`, `locks`, `all_available`. Staggered: `locks`,
`all_available`. Seven conditions.

**Templates.** Eight contended templates, each with a matched control (`_ctrl`):

- conflict: `inventory_last_unit`, `seat_same`, `ticket_same`, `transfer_shared_source`, `transfer_same_amount`;
- still valid: `inventory_still_valid`;
- write skew: `budget_write_skew`, `joint_account_write_skew`.

**Amounts.** In `inventory_last_unit`, `inventory_still_valid`, `transfer_shared_source`, `budget_write_skew` and
`joint_account_write_skew` the two agents get different amounts, each of which fits alone while both together do
not (in `inventory_still_valid` both fit, as in Study 2). a0 gets the larger amount in instances 0, 3, 4, 7 (2 per
wording). `transfer_same_amount` keeps the Study 2 rule (both agents move the same amount; one transfer fits, two do
not). `seat_same` and `ticket_same` have no amounts.

**Instances.** 8 per family, wording i mod 2, record names from neutral pools with no agent ids, multi-record guard
texts in sorted order. Seed space `src6-study3-v1`; every numeric shape (family, sorted initial values, sorted
amounts) differs from every Study 1 and Study 2 instance and from the other Study 3 instances of its family (tested).

**Grid.** 3 models × 7 conditions × 8 families × 8 instances × 2 arms × 1 schedule = 2,688 episodes, n = 2, aware off.

**Fixed settings** (`design6.py`, `world6.py`, `model_agent6.py`, as Study 2): call cap 24 under `none` and
`cas_available`, 28 under the lock configs; max_tokens 4096; temperature 0 requested; no reasoning or thinking
parameter sent; think time U{0..4} before every completion; extra call latency U{1..2} with probability 0.3; round
order reshuffled every round; stall after 6 idle rounds; max 3,000 rounds; Anthropic prompt caching on.

### Randomization

- Instances: `random.Random("src6-study3-v1|{family}|{i}")`, with a suffixed redraw key on a shape clash. A control
  uses its family's draw.
- Schedules: seed = sha256 of ("src6-schedule-v1", family, instance, schedule index, n), with "staggered" appended
  under the staggered start. A pair shares its seed; the five together configs share theirs, so S3-H2 compares the
  same environment.
- Visit order: instance, then family, condition and arm; a contended episode and its control run as an adjacent
  pair.
- Model outputs are not seeded.

## Sampling plan

### Existing data

Registration prior to creation of data. No Study 3 model call has been made.

### Explanation of existing data

- **Study 3 runs with no model.** Scripted reference policies (validity table, $0) and a full dry run with fake
  models ($0). They test the harness and the analysis script and contain no model behaviour.
- **Study 1 and Study 2** are complete and publicly posted; the author has seen all of their data. They shaped this design:
  the three limits above, the cost estimate (observed Study 2 cost per model, config, family and arm), the stagger
  offset (Study 2 control timelines), the expected uptake and read-before-lock rates. They enter no Study 3 estimate.
  Lock texts, amounts and the start mode changed, so we make no cross-study comparison of rates; the only
  comparisons across texts are S3-H2's, inside Study 3.

### Data collection procedures

`bash run_conc_study3.sh` runs two provider lanes in parallel: Anthropic (batch: Haiku, then Sonnet) and OpenRouter
(sync: Qwen).

1. The script refuses to spend unless the file `.study3_registered` exists (written only after this registration is
   filed).
2. Gates before any spend: `freeze6.py --check` against `src6/FREEZE.md`, then the validity gate (scripted agents, no
   cost).
3. Preflight: one small request per model; Qwen must be served by Alibaba. Preflight output is not data.
4. `analysis6/balance6.py` logs the OpenRouter key's usage before and after the OpenRouter lane (no model call).
5. Every transcript, ledger, spend log, balance log and failure log is kept.

### Sample size

Per model: 896 episodes, 64 per condition × arm (8 families × 8 instances), 64 clusters. Total 2,688 episodes.

### Sample size rationale

Sample size is set by the approved budget ($50), not by a power target. The power below says what each test can and
cannot show. All figures come from the registered procedures (sign-flip, bootstrap-t TOST, the Holm and gatekeeping
levels), simulated on the Study 2 generator with 64 clusters and one episode per arm-cluster: ICC 0.3 within an
arm-cluster, correlation r between the two members of a pair (0.3 for configs, 0.5 for arms), cross-model cluster
correlation 0.3 for pooled tests; 2,000 runs each, B = 1,000 (`analysis6/power_sims/power6.py`, archived with this
registration; numpy and scipy, not part of the analysis).

| test | setting | per model (first Holm step) | pooled (first step) |
|---|---|---|---|
| S3-H1-diff | control 0.02, Δ = 0.10 / 0.15 / 0.20 | 0.14 / 0.47 / 0.76 (α/16) | 0.83 / 0.99 / 1.00 (α/16) |
| S3-H2a | Study 2 text 0.35, drop 0.15 / 0.20 / 0.25 | 0.33 / 0.59 / 0.86 (α/4) | 0.79 / 0.98 / 1.00 (α/4) |
| S3-H2a | Study 2 text 0.80, drop 0.15 / 0.20 / 0.25 | 0.21 / 0.36 / 0.58 (α/4) | 0.64 / 0.87 / 0.98 (α/4) |
| S3-H2b | Study 2 text 0.40, drop 0.10 / 0.15 | 0.40 / 0.79 (α/4) | 0.83 / 0.99 (α/4) |
| S3-H2b | Study 2 text 0.95, drop 0.10 / 0.15 | 0.22 / 0.51 (α/4) | 0.60 / 0.93 (α/4) |
| S3-H3-eq at Δ = 0 | uptake 0.50 / 0.70 / 0.85 / 0.95 | 0.43 / 0.57 / 0.88 / 0.99 (δ 0.25, α/6) | 0.71 / 0.80 / 0.96 / 1.00 (δ 0.15, α/2) |
| S3-H3-eq, pooled | uptake 0.70 / 0.85, true Δ = 0.05 | | 0.63 / 0.90 (α/2) |
| S3-H3-eq, pooled | uptake 0.70 / 0.85, true Δ = 0.10 | | 0.32 / 0.79 (α/2) |

- S3-H1 per model detects added failures of about 0.20 with power about 0.76 at the first Holm step; Study 2's were
  0.21 to 0.80.
- S3-H2a per model detects only drops of 0.25 or more; pooled, drops of about 0.20. Smaller per-model effects are
  expected to read "no claim".
- S3-H3 per model is powered at 80 % only when uptake is about 0.85 or higher; pooled from about 0.70. These are
  powers of the test. Above an uptake of 1 − δ (0.75 per model, 0.85 pooled) the room condition fails and a
  rejection is read as uninformative, so an informative per-model equivalence is unlikely in this design; the pooled
  test is informative between uptakes of about 0.70 and 0.85.
- **Size at the boundary.** With contention changing uptake by exactly δ (a true null; the generator's shift
  calibrated so that the realized mean difference equals δ) and one binary per arm-cluster, the S3-H3 TOST rejected
  0.045 to 0.053 per model at α (0.006 to 0.009 at α/6) and 0.043 to 0.051 pooled at α (0.021 to 0.029 at α/2), at
  control uptake 0.25 to 0.70 (2,000 runs, MC SE 0.005). The sign-flip tests are exact.
- **Why δ = 0.25 per model and 0.15 pooled.** The Study 2 margins, kept so that the S3-H3 result reads on the same
  scale as S2-H4.

### Starting and stopping rules

The design is fixed. There is no optional stopping on results.

**Budget caps** (`budget6`, over every Study 3 spend log):

| provider | estimate | × 1.15 safety | cap |
|---|---|---|---|
| Anthropic (Haiku $9.17, Sonnet $12.91) | $22.09 | $25.40 | $29.50 |
| OpenRouter (Qwen) | $11.66 | $13.41 | $15.50 |
| total | $33.75 | $38.81 | $45.00 |

- Estimates: the observed Study 2 mean cost of the same model, matching config, family and arm (1,344 Study 2
  episodes), plus the input cost of the longer Study 3 tool text (109 tokens per completion) and 150 tokens per
  completion for the new response fields under `locks` and `all_available`, staggered episodes × 1.10. A dry run with
  fake models priced at the same price table (fake token counts, so a check of the pricing path, not an estimate):
  $19.99 (Anthropic $15.39, OpenRouter $4.60).
- Before each pair (sync) or batch wave (batch), the worst-case estimate must fit in what is left for the provider and
  the total. Overshoot is at most one completion. The caps sum to $45, below the $50 the author approved.
- Each model's block has a sub-cap of 1.6 × its estimate (Haiku $14.68; Sonnet is limited by the lane cap; Qwen by
  its lane cap).
- Caps are not raised after any model result exists.

**If a cap binds.** The lane stops that block. Episodes are visited instance first, so a stop drops whole later
instances across all families and conditions. A pair starts only if both of its episodes fit; a finished episode
whose partner did not run is held back and is never data. A cap stop changes precision, not the estimand. Tests with
at least 75 % of their clusters run as registered (Missing data). Cells not run are reported as "not tested".

**Shared OpenRouter key.** The key is shared with another project. Spend by others is measured (balance log before
and after the lane), not prevented. If the lane stops on a credit or key limit while others spent in that window, the
lane is reported as stopped by an external cause, and it may be resumed after a top-up without any change to the plan
(reported as a manual intervention).

**Manual intervention.** The author does not stop, reorder or restart a lane except after a crash, a credit stop or a
provider outage. Every manual intervention is logged with a timestamp and reported as a deviation.

## Variables

### Manipulated variables

Model; config (`none`, `cas_available`, `locks_s2text`, `locks`, `all_available`); start mode (together, staggered;
staggered only under `locks` and `all_available`); arm (contended, control); amount rule (distinct, or same in
`transfer_same_amount`).

### Measured variables

All measures come from `src6/score6.py` and `src6/model_agent6.py` at the frozen hash. Every Study 2 measure is kept
with its Study 2 definition (the Study 2 registration, Measured variables; its text is public in the repository,
`preregistration/PREREGISTRATION_STUDY2.md`, and in the archived record doi:10.5281/zenodo.24226165):
`fs_nonserializable` (primary), `dsg_basis_cycle`, the DSG variants, `outcome`, `cap_truncated`, the non-exclusive flags, `lock`, `lock_granted`, `lock_effective`,
`cas`, the timing measures (`first_protective`, `first_contention_call`, `contention_signals`,
`protect_before_contention`, `lock_after_contention`), `fulfilled`, `end_reason`, `first_reply`, and the per-completion
fields. Additions:

- **`peer_signal_calls`** also counts a read showing `locked: true`.
- **`perceivable_signals`, `first_perceivable_call`, `protect_before_perceivable`.** The perceivable signals are
  defined under Common definitions; `protect_before_perceivable` applies the `protect_before_contention` rule to them:
  True if the first protective call was at or before the first perceivable signal, or the agent protected and saw
  none; False if after; None if it never protected.
- **`read_before_lock`.** Defined for agents granted a lock that committed a write. True iff some committed fenced
  write of the agent is in `fenced_stale_basis`: its basis is a read (the agent's last successful read of the written
  record before the write, when no later own write of that record exists) made before the grant of the token the
  write carries. None otherwise. A blind fenced write and a write based on the agent's own earlier write are not
  counted (the first is `fenced_unread_basis`, reported in D3).
- **`lock_scope`.** `all` (granted locks on every record the agent's intent reads), `own` (on some), `none`.
- **`lock_waits_reported`, `locked_reads`.** Acquires whose response reported a wait; reads showing `locked: true`.

### Indices

None. Rates are cluster means of 0/1 outcomes as defined under each hypothesis.

## Analysis plan

### Statistical models

**Analysis code.** `analysis6/analyze6.py` implements the confirmatory tests, the claims per cell, the checks, D1 to
D6 and the sensitivity analyses S1 to S9. It was written and tested before the first paid call
(`analysis6/tests_analyze6.py`: planted effects, exclusions, gatekeeping, determinism), run on the dry-run
transcripts, and is listed in the Freeze table with its dry-run outputs. Its statistical core (sign-flip,
bootstrap-t, intervals, Holm with the Monte Carlo recompute) is the Study 2 code, unchanged.

**Aggregation.** A cluster enters a test only with the episodes the test needs (Missing data). Inside a cluster,
agents, arms and configs are aggregated first; the estimate is the mean of the cluster values. The estimand is the
mean over these 8 templates, each weighted equally. Clusters are resampled without stratification.

**Decision tests** (as in Study 2).

- **θ0 = 0** (S3-H1, S3-H2a, S3-H2b, S3-H3-diff, the calibration, C1): exact sign-flip permutation test on cluster
  values, counted over all 2^m assignments (Monte Carlo with R = 100,000 only if the common denominator exceeds 10,000).
  Two-sided p (C1) is twice the smaller one-sided p, capped at 1.
- **TOST sides (θ0 = ±δ, S3-H3-eq):** studentized cluster bootstrap (bootstrap-t), B = 10,000, with the Study 2 rules:
  t = (Δ̂ − θ0) / SE, SE = sd/√m; t*_b = (Δ̂*_b − Δ̂) / SE*_b, with the observed SE in place of a zero SE*_b; ties count
  against rejection; if all cluster values are equal, the exact one-sided sign test against θ0.
- Reported for every test, never used for a decision: the percentile bootstrap p, the exact sign test, the 95 % and
  90 % percentile intervals; for each TOST the 90 % bootstrap-t interval and the Holm-consistent interval.

**Bootstrap.** B = 10,000; RNG `random.Random("20261115|{test}|{model}|{config}")`, with `{test}` ∈ {H1diff,
H1caldiff, H2a, H2b, H3eq, H3diff, H3b, check1, check2}, `{model}` ∈ {qwen, haiku, sonnet, pooled}, `{config}` the
config name (`locks_s2text-locks` for S3-H2; `locks_s2text+locks+all_available` for C1; `{config}|conditional` for
D4b and `{config}|reread` for D6), and `|sens{k}` appended in sensitivity analysis k. Clusters in sorted key order;
resample b uses draws b·m to (b + 1)·m − 1 of `rng.choices(range(m), k = m·B)`; interval rules as in Study 2.

**Monte Carlo resolution.** A Monte Carlo p within 2 MC standard errors of its Holm level is recomputed with 10 times
the draws under the key plus `|mc2`; the recomputed value governs. Exact sign-flip p-values are never recomputed.

**Sensitivity analyses.** Each reruns the confirmatory tests with the same families and gates and reports changed
verdicts; registered verdicts stand.

- S1. `cap_truncated` episodes excluded, with their pair partners.
- S2. Excluded episodes kept and scored as they are.
- S3. Holm across all per-model confirmatory tests within each model, without gatekeeping.
- S4. Template level: the family-mean test of every confirmatory cell (8 families; t-test with df 7 for TOST sides,
  exact sign-flip over 2^8 assignments for θ0 = 0). Reported, not a decision.
- S5. **Against equivalence** (S3-H3): every pair excluded under Data inclusion and exclusion enters as written; in
  its contended episode `fs_nonserializable` = 1 and every errored agent counts as having used a primitive; the
  control enters as scored. An S3-H3 equivalence is claimed only if it also holds under S5.
- S6. S3-H1 and its calibration with `dsg_basis_cycle` in place of `fs_nonserializable`.
- S7. S3-H3 over both agents (a0 and a1) instead of the late agent.
- S8. The S3-H3 gate q computed with the Study 2 signal set (`contention_signals`, `protect_before_contention`).
- S9. S3-H2b with every agent in the denominator (an agent without an eligible lock counts as 0). S3-H2b conditions
  on being a lock user that committed a write, and the bundle may change who that is; S9 shows whether the verdict
  depends on that selection. The eligible counts per config are reported with S3-H2b.

### Transformations

None. Outcomes are 0/1 per episode or agent.

### Inference criteria

- One-sided α = 0.05 for S3-H1, S3-H2a, S3-H2b, S3-H3-diff and each TOST side; two-sided α = 0.05 for C1.
- Holm within each family, with the S3-H3-eq gatekeeping. Each family controls FWER at 0.05; claims across families
  are not jointly controlled (S3 reports Holm within model).
- A non-rejection is never reported as evidence of absence. An equivalence in an uninformative cell (q ≤ δ, or less
  than δ of room above the control uptake) is reported as uninformative. For a model that does not reject, we make no claim.

### Data inclusion and exclusion

| event | rule | reported |
|---|---|---|
| Provider failure (no completion after the provider's retries) | Not written, not scored. Sync: the lane reruns the block until done and stops after 10 attempts without progress. Batch: up to 5 tries per request, the lane reruns the driver up to 5 times. | failures per cell |
| Qwen completion not served by Alibaba | The episode is aborted (spend counted), not written, and run again. A written Qwen episode with another host is excluded with its partner. | per cell |
| An agent ends `truncated`, `provider_error`, `error`, `refusal` or `content_filter`, or its last completion stopped with `content_filter` or `refusal` | The harness does not re-run written episodes. The episode and its pair partner are excluded from the main analysis; S2 keeps them; S5 scores them against equivalence. | per cell and arm |
| More than one transcript for one episode id | The earliest (`run_info.started_utc`, then file name) is used; the others are counted. | count |
| Model version drift (`model_served`; `claude-sonnet-5` is an undated alias) | Kept; served versions reported per model. | per model |
| Turn-cap endings, invalid tool calls, refusals with a tool call, `cap_truncated` | Model behaviour: kept and scored. S1. | per cell |
| Dry-run, preflight and validity rows; any unregistered condition, unit or model | Never data. | count |

Exclusions are counted per arm and cell. Errors scale with the number of completions, so contended episodes are
excluded more often; S5 and its rule guard the equivalence claims against this.

### Missing data

- Missing episodes are not imputed. Paired tests use complete pairs only; an episode whose partner is missing or
  excluded leaves with it.
- A cluster enters a test if it has every episode the test needs (S3-H2: both configs; S3-H2b: an eligible agent in
  each config).
- A test runs only if at least 75 % of its registered clusters enter (48 of 64). Otherwise it is "not tested": it
  leaves its Holm family and its partial cells are reported descriptively. A pooled test applies the rule to the
  clusters that enter for every pooled model.

### Exploratory analysis

Labelled exploratory; they support no confirmatory claim.

- Per-family and per-wording breakdowns of every measure; the amount orientation (a0 with the larger amount or not).
- `cas_available` and `none` under the together start against the Study 3 lock configs, on uptake and failures.
- Lease lengths chosen, lock waits, deadlocks; fulfilment, abandonment, cost, tokens and turns.
- Agreement of `fs_nonserializable` with the three DSG verdicts.
- Final replies of agents with a reported wait or a locked read.

## Other

### Declared confounds

- **Selection in S3-H2b.** Its denominator (agents granted a lock that committed a write) can differ between the two
  texts; S9 reports the unconditional version.
- **The lock bundle.** `locks` differs from `locks_s2text` in three parts (description, reported wait, locked reads).
  S3-H2 tests the bundle; it cannot attribute an effect to one part. The new description also makes the tool menu
  about 380 characters longer.
- **Version visibility.** `locks` hides versions and `all_available` shows them.
- **Start mode.** The staggered start is a different schedule; staggered episodes are less contended by design
  (validity table: naive policies fail less often). S3-H3 compares arms within the staggered start only.
- **Batch vs sync, temperature and thinking, provider routing.** As in Study 2: Haiku and Sonnet run in batches, Qwen
  sync; Haiku applies temperature 0, Sonnet rejects it and thinks by default, Qwen's settings on OpenRouter are
  unverified; Qwen is pinned to Alibaba. Model is a fixed factor.
- **Call cap by config.** 24 vs 28, as in Study 2.
- **Affordance cues.** The primitives' texts imply concurrency; they are equal across arms. "You are agent a0" implies
  an a1.
- **Study 1 and 2 to Study 3 changes.** Amounts, lock texts and the start mode changed. No cross-study comparison.

### Deviations

A deviation is any departure from this document, and any change to a frozen file after the freeze, bug fixes
included. Each is listed in an appendix table with what changed and why, whether it was made before or after any
Study 3 model result was seen, its effect, and where feasible the result under the registered plan.

**Bug fixes.** After a harness or scorer fix, the corrected scoring governs only if the bug fails a check in `tests6`,
`validity6`, `dry_check6` or checks C1 to C4. Otherwise the registered scoring governs. Both are reported. A bug that
changed model inputs cannot be rescored: the affected cells are re-run in full (both arms) or reported as not tested.

"Seeing results" means opening any scored episode or `summary.md`. The sync runner prints each episode's outcome to
its log; the author reads the logs only for failures, cost and progress. The analysis code is frozen before spend and
no lane is stopped or restarted by hand except as stated under Starting and stopping rules.

### Freeze

sha256 of every frozen file, taken after all pre-registration edits and before any paid call. `src6/FREEZE.md` is the
authoritative list for the harness (every `*.py` and `*.json` in `src6`, every `*.py`, `*.json` and `*.sh` in
`src6_batch`, `src6_verify/dry_check6.py`, `run_conc_study3.sh`); its own hash is listed here. The analysis files and
the fixture builders sit outside `src6` and are hashed at the same time.

| file | sha256 |
|---|---|
| `src6/FREEZE.md` | `7dc10fab662462e12815eb89d9c379ad10d126c79aae13da565bc657c7f3b912` |
| `run_conc_study3.sh` | `6c9a79126a0d974673883bc80ed06cea501df14bf5b4e77ba691f42932342fbe` |
| `analysis6/analyze6.py` | `55f05ef1898a99dd7aade70e2a6132635fce590f020b18ecf1cb910c040e71a6` |
| `analysis6/balance6.py` | `87170d18eb270de1ccb751da317e7d143104a46ec30072c4e06bac9ee7d4728b` |
| `analysis6/tests_analyze6.py` | `0e6164f094ffe286ec33c55b2fda5ba29548d0725f3a38cc39b1a31d4c7ae99b` |
| `analysis6/out/results.json` | `0fe78e53cdefcf543d0e9e5d0b72fa260b2687a8045eb61ed2c785ad661816cf` |
| `analysis6/out/numbers.tex` | `ab78c14f408d4204775114446599c5946ece9a6ba372dd40cde24df734876ed1` |
| `analysis6/power_sims/power6.py` | `67a8c4c4925249f5232c2753a87017861a18f08330037674fab2710edc4e1b15` |
| `analysis6/power_sims/sim_tost.py` | `bb3b1c1dd6bde4bf3be44014349a3d5254364f0d9da2fb9cafa886bad82e87d7` |
| `analysis6/power_sims/simlib.py` | `38c61a19bebc15bbf4cd049afdb57a19f5c7462c302506577f1ad7803e79a87f` |
| `analysis6/power_sims/power6_out.json` | `ca7c0d3e6ac9f2370069a70d537444b770e6a01344f521683d0d6d023935efb4` |
| `tools/freeze_table.py` | `d5e516e919b5a9bc292e2f9b5d69bfb7c5a9951985938f320c3d8cdd70f8df60` |
| `tools/make_prior_shapes.py` | `6a4133e970e0a90f421a61d0ecaffa5cee8d61ffbaa8ca7d3be217f4f4d3ba91` |
| `tools/make_study2_costs.py` | `e4fbca5043cf14571dfbe9438860e27bbab821a61045e24e74b96e9a0654347a` |
| `tools/make_study2_fixtures.py` | `09ea622560d9270457e4667d81d2287ab4c4ff31ccadc09260f4876e12d484a0` |

### Data and code availability

The code (MIT licence) and all run outputs (transcripts, ledgers, result files; CC BY 4.0, subject to provider terms
for model outputs) are released with the paper's version 2 in the same public repository and archive as Studies 1
and 2.
