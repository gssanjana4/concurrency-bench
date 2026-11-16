# OSF Preregistration: Study 4

Fields follow the OSF Preregistration template, as in the Study 1 (osf.io/a5vec), Study 2 (osf.io/zj3an) and Study 3
(osf.io/3pa4k) registrations. Each `##`/`###` heading below is one OSF form field.

This registration is filed before any paid Study 4 call, the preflight included. The frozen code (see Freeze)
implements what it describes. If code and text disagree, this text governs, and we report the difference as a
deviation. No paid call is made until the OSF reports this registration as archived (Data collection procedures).

## Title

Do LLM agents coordinate on shared records? Study 4: which part of the lock bundle lowers integrity failures

## Authors

Sanjana Gopnal Swamy, independent researcher.

Linked registrations: Study 1, osf.io/a5vec; Study 2, osf.io/zj3an; Study 3, osf.io/3pa4k.

## Description

Two LLM agents, each in its own conversation, act on the same versioned records through tool calls. A seeded
scheduler interleaves their calls. Scoring is deterministic, from a ledger and the server call log. There is no LLM
judge.

In Study 3, a lock bundle lowered contended integrity failures against the Study 2 lock text in all three models
(pooled drop 0.57). The bundle has three parts, and Study 3 could not say which part did it:

1. an instruction in the `acquire_lock` description (lock before reading; lock every record the decision depends on);
2. a held `acquire_lock` reports its wait (`waited_rounds`);
3. a read of a record locked by someone else shows `locked: true`.

Parts 2 and 3 are signals; part 1 is an instruction. Study 4 crosses the instruction with the two signals in a 2 × 2
design, replicates the Study 3 bundle effect on new instances, and adds a fourth model (Claude Fable 5). It uses a new
harness (`src7`, a copy of the Study 3 harness `src6` with the two new configs). Study 1 to 3 data enter no Study 4
estimate.

## Hypotheses

### Common definitions

- **Configs** (all four use the same fenced-lock service, versions hidden; only the texts and responses below differ):

  | config | instruction (part 1) | signals (parts 2 and 3) |
  |---|---|---|
  | `locks_s2text` | no | no |
  | `locks_instr` | yes | no |
  | `locks_signals` | no | yes |
  | `locks` (the Study 3 bundle) | yes | yes |

- **Episode.** Contended only (no controls), n = 2 agents, together start.
- **Cluster.** Family × instance, within a model: 8 families × 16 instances = 128 clusters. The four configs of a
  cluster share the instance and the schedule seed; the interleaving can still differ once the agents' calls differ.
- **fs.** `fs_nonserializable` of the episode (0/1), as in Studies 2 and 3.
- **Pooled.** The equal-weight mean over the models whose own test of that hypothesis runs (at least 2), on the
  clusters that enter for all of them. One sign flip acts on all pooled models at once.
- **Floor.** Fewer than 5 failed episodes (of 128) under `locks_s2text`, counted on `fs_nonserializable`. For Fable this
  decides whether its other three configs run at all (the Fable stage rule, Starting and stopping rules); in Study 2,
  Fable failed in 0 of 12 contended episodes under the Study 2 lock text. For any other model at the floor, its tests run,
  and a non-rejection is labelled "floor: the test could not show a drop".

### Confirmatory

Each cluster value is computed from the episodes of the cluster that the test needs. S4-H1 to S4-H5 are one-sided
sign-flip tests (H0: the cluster values are symmetric about 0; the alternative, a positive mean); S4-H6 is two-sided.

**Primary.**

- **S4-H1 (replication).** d = fs(`locks_s2text`) − fs(`locks`). The Study 3 bundle lowers contended integrity
  failures against the Study 2 lock text.
- **S4-H2 (instruction).** d = [fs(`locks_s2text`) + fs(`locks_signals`)]/2 − [fs(`locks_instr`) + fs(`locks`)]/2.
  The instruction lowers failures, averaged over the two signal levels.
- **S4-H3 (signals).** d = [fs(`locks_s2text`) + fs(`locks_instr`)]/2 − [fs(`locks_signals`) + fs(`locks`)]/2. The
  two signals lower failures, averaged over the two instruction levels.

**Secondary** (the simple effects and their interaction; they say whether either part alone is enough):

- **S4-H4 (instruction alone).** d = fs(`locks_s2text`) − fs(`locks_instr`).
- **S4-H5 (signals alone).** d = fs(`locks_s2text`) − fs(`locks_signals`).
- **S4-H6 (interaction, two-sided).** d = [fs(`locks_s2text`) − fs(`locks_instr`)] − [fs(`locks_signals`) − fs(`locks`)]:
  the instruction's effect without the signals minus its effect with them.

Each hypothesis is tested per model (Qwen3.6-27B, Claude Haiku 4.5, Claude Sonnet 5, Claude Fable 5) and pooled: up to
5 tests per hypothesis, one Holm family per hypothesis (six families).

**Expected direction.** Study 3's lock failures under the Study 2 text were mostly reads made before the lock
(read-then-lock) and locks on only the written record (own-only). Both are what the instruction targets, so we expect
S4-H2 to reject in more models than S4-H3. This is an expectation, not a hypothesis.

**Claims.**

- A rejected one-sided test: "[the contrast] lowered contended integrity failures in [model] by [estimate] (one-sided
  95 % lower bound, unadjusted)". A non-rejection: no claim, never evidence of no effect (at the floor: the floor
  label).
- S4-H2 and S4-H3 are averages over the other part's two levels. A rejection says the part lowers failures on that
  average, not that it adds to the other part.
- S4-H6 rejected with a positive estimate: "on the failure-rate scale, the drop from one part is smaller when the other
  part is present". This is expected near zero failures, and whenever each part removes a share of the failures (power
  table), so it is not evidence that the parts overlap. With a negative estimate: "the drop from one part is larger when
  the other part is present". S4-H6 not rejected: no claim about the interaction, and not evidence that the effects add
  up. If S4-H4 and S4-H5 both reject, each part alone lowers failures.
- We do not rank the two parts by their estimates.

### Pre-specified checks (not hypotheses)

- **C1. Lock safety** (the src7 scorer's check, in every episode): every committed fenced write carries a token
  granted to its writer on that record and lies inside that token's lease; no one but the holder writes a record while
  its lock is live; per record, the tokens of committed fenced writes never decrease. A model with any violation, or
  with an episode the check could not run on, is reported as invalid: its tests are not run and it enters no Holm
  family and no pooled test.
- **C2. Signals only where offered.** No `waited_rounds` and no `locked: true` in any `locks_s2text` or `locks_instr`
  episode. A failure means the configs were not what this plan describes; it is reported as a deviation with the
  affected cells.
- **C3. Served model and host.** Qwen served by Alibaba; served model versions reported per model and config (for
  Fable, so per stage).

### Pre-specified descriptive (no test, no Holm)

- **D1.** fs per model and config (failed / episodes).
- **D2.** Lock-failure mechanisms per model and config (read-then-lock, own-only, no lock; an episode with none or
  more than one of these counts as other), as in Study 3.
- **D3.** Protocol per model and config: share of agents that lock first, read then lock, never lock; lock scope
  `all` in the multi-record families; `read_before_lock` among agents granted a lock that committed a write.
- **D4.** Signal counts (`waited_rounds`, `locked: true`) per model and config.

## Design plan

### Study type

Experiment on software agents. No human participants. All factors are crossed; the randomised elements are the
instance draws and the schedule seeds.

### Blinding

No blinding is involved. Scoring is automated from ledgers and call logs. The harness, scorer, instances, price
tables, plan, run script and analysis script are frozen before any paid call (see Freeze).

### Study design

**Models and execution paths:**

| model id | path | note |
|---|---|---|
| `openrouter:qwen/qwen3.6-27b-20260422` | OpenRouter, sync | routed `{"order": ["alibaba"], "allow_fallbacks": false}` |
| `claude-haiku-4-5-20251001` | Anthropic Message Batches | |
| `claude-sonnet-5` | Anthropic Message Batches | undated alias |
| `claude-fable-5` | Anthropic Message Batches | new in Study 4 |

**Config texts.** `locks_s2text` is the Study 2 lock text byte for byte, and `locks` is the Study 3 bundle byte for
byte (tool menus tested against the frozen Study 2 and Study 3 harnesses). The other two take exactly one part of the bundle:

- `locks_instr` adds to the `acquire_lock` description, after its first sentence: "Acquire the lock before you read a
  record you will update, and lock every record your decision depends on: the records your condition reads as well
  as the ones you write. A value you read before the lock was granted may be out of date." Responses are the Study 2
  ones.
- `locks_signals` adds "; a call that waited says so in its response (waited_rounds)" to the `acquire_lock`
  description and "While the record is locked under a lease you do not hold, also returns locked: true." to the
  `get_record` description; a held acquire returns `waited_rounds` and the Study 3 wait note, "The record was locked
  when you asked; this call waited k rounds before the lock was granted. Values you read before this grant may be out
  of date."; a read of a record locked by another agent returns `locked: true`.

Tool menus are 3,537 (`locks_s2text`), 3,773 (`locks_instr`), 3,682 (`locks_signals`) and 3,918 (`locks`) characters
long. Lock semantics are Study 2's: per-record fencing tokens, leases counted in the holder's own calls (1 to 20), a
refused acquire held up to 150 rounds, locks released when an agent ends. No config offers messages or conditional
writes.

**Templates.** The eight Study 3 contended templates: `inventory_last_unit`, `seat_same`, `ticket_same`,
`transfer_shared_source`, `transfer_same_amount`, `inventory_still_valid`, `budget_write_skew`,
`joint_account_write_skew`, with Study 3's amount rules (distinct amounts except in `transfer_same_amount`).

**Instances.** 16 per family, new draws (seed space `src7-study4-v1`). Every numeric shape (family, sorted initial
values, sorted amounts) differs from every Study 1, 2 and 3 instance and from the other Study 4 instances of its
family (tested). `seat_same` and `ticket_same` have no numbers and differ by record names only.

**Grid.** 4 models × 4 configs × 8 families × 16 instances × 1 schedule = 2,048 episodes, n = 2, together start,
aware off.

**Fixed settings** (as Study 3): call cap 28; max_tokens 4096; temperature 0 requested (in Study 3 the Anthropic API rejected
the parameter for both Claude models, so requests are resent without it, the Claude models run at the provider default,
and this is logged; Qwen's effective temperature on OpenRouter is unverified); no reasoning or thinking parameter sent; think time
U{0..4} before every completion; extra call latency U{1..2} with probability 0.3; round order reshuffled every round;
stall after 6 idle rounds; max 3,000 rounds; each agent starts in round 1 + U{0..6}; Anthropic prompt caching on.

### Randomization

- Instances: `random.Random("src7-study4-v1|{family}|{i}")`, with a suffixed redraw key on a shape clash.
- Schedules: seed = sha256 of ("src7-schedule-v1", family, instance, schedule index 0, n). The four configs of a
  cluster share it.
- Visit order: per model block, instance, then family and config, so a cost-cap stop drops whole later instances.
  Fable runs in two stages (Starting and stopping rules).
- Model outputs are not seeded.

## Sampling plan

### Existing data

Registration prior to creation of data. No Study 4 model call has been made.

### Explanation of existing data

- **Study 4 runs with no model.** Scripted reference policies (validity table, $0) and a full dry run with fake models
  ($0). They test the harness and the analysis script and contain no model behaviour.
- **Studies 1 to 3** are complete; the author has seen all of their data. Study 3's result motivated this design and
  its costs and failure rates set the cost estimate and the power simulation. They enter no Study 4 estimate.

### Data collection procedures

`bash run_conc_study4.sh` runs two provider lanes in parallel: Anthropic (batch: Haiku, Sonnet, then Fable) and
OpenRouter (sync: Qwen).

1. **Registration gate** (`src7/gate7.py`, called by the run script and again before the preflight, and by
   `run7.py`, the batch driver and the preflight script in any non-dry run). After filing, the OSF API record of this
   registration, read in the author's signed-in browser (the registration is embargoed), is saved byte for byte as
   `.study4_osf_api.json`, and `.study4_registered` records its URL, `archiving: complete`, the record's sha256 and the
   time of the read. The gate refuses unless the hash matches and the saved record shows `archiving` false, not
   withdrawn, no pending approval, a `date_registered`, a title naming Study 4, and an id other than the Study 1 to 3
   registrations. The saved record is self-attested (the embargo keeps it from public view); it is released with the data
   so that its `date_registered` can be checked against the time of the first paid call. (Study 3's run started before
   its registration had archived, and that registration failed.)
   The run script also refuses caps above the registered caps and any plan file other than the frozen one.
2. Gates before any spend: the freeze check against `src7/FREEZE.md`, then the validity gate (scripted agents, no
   cost; rerun whenever `FREEZE.md` changed).
3. Preflight: one small request per model; Qwen must be served by Alibaba. Preflight output is not data.
4. The OpenRouter key's usage is logged before and after the OpenRouter lane (no model call).
5. Every transcript, ledger, spend log, balance log and failure log is kept.

### Sample size

Per model: 512 episodes, 128 per config (8 families × 16 instances), 128 clusters. Total 2,048 episodes (1,664 if
Fable stops at the floor).

### Sample size rationale

Sample size is set by the approved budget, not by a power target. Power was simulated (`tools/power7.py`, 200 runs per
scenario) with the registered tests, Holm families, pooling and the Fable stage rule, using Study 3's failure rates under
the Study 2 text and the bundle (Qwen 40/64 → 0/64, Haiku 57/64 → 7/64, Sonnet 24/64 → 4/64) and, for Fable, a rate of
10 %, 5 % or 2 % under the Study 2 text and 0 % under the bundle. Scenarios split the drop from the Study 2 text to the
bundle between the two parts. Power per test (Qwen, Haiku, Sonnet; pooled), Fable at 10 %:

| scenario | H1 | H2 | H3 | H4 | H5 | H6 |
|---|---|---|---|---|---|---|
| all from the instruction | 1.00 | 1.00 | ≤ 0.01 (null) | 1.00 | ≤ 0.01 (null) | ≤ 0.01 (null) |
| all from the signals | 1.00 | ≤ 0.02 (null) | 1.00 | ≤ 0.01 (null) | 1.00 | ≤ 0.01 (null) |
| half each, additive | 1.00 | 0.98 to 1.00 | 1.00 | 0.70 (Sonnet) to 1.00 | 0.73 (Sonnet) to 1.00 | ≤ 0.01 (null) |
| each part alone removes the same share (together, the product) | 1.00 | 0.99 to 1.00 | 0.99 to 1.00 | 0.99 to 1.00 | 0.98 to 1.00 | 0.46 (Sonnet), 1.00 (others) |
| either part alone suffices | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 75 % instruction, 25 % signals | 1.00 | 1.00 | 0.56 (Sonnet) to 1.00 | 0.98 to 1.00 | 0.17 (Sonnet), 0.61 (Qwen), 0.94 (Haiku), 0.96 (pooled) | ≤ 0.01 (null) |

Fable: its stage 2 runs in 99 to 100 %, 75 to 81 % and 9 to 16 % of simulated studies at a 10 %, 5 % and 2 % rate,
which caps the power of its own tests at those shares. The pooled power changes by at most 0.03 across the three Fable
rates.
A part that carries a quarter of the drop is often missed in Sonnet and Fable.

### Starting and stopping rules

The design is fixed. There is no optional stopping on results.

**Budget caps** (`budget7`, over every Study 4 spend log):

| provider | estimate | × 1.15 | cap |
|---|---|---|---|
| Anthropic (Haiku $6.27, Sonnet $6.90, Fable $48.28: stage 1 $11.93, stage 2 $36.35) | $61.44 | $70.66 | $100.00 |
| OpenRouter (Qwen) | $7.52 | $8.65 | $9.50 |
| total | $68.96 | $79.30 | $109.50 |

- Estimates: the observed Study 3 mean cost of the same model, family and lock text (contended, together start); a
  config with one part of the bundle takes the larger of the two Study 3 lock texts. Fable has no Study 3 cost: 7 ×
  the Sonnet estimate (its list price is 5 × Sonnet's; in Study 2 its cost per lock episode was 6.7 × Sonnet's).
- Before each episode (sync) or batch wave (batch), the worst-case estimate must fit in what is left for the provider
  and the total. Overshoot is at most one completion.
- Each model has a sub-cap of 1.6 × its estimate, never above its lane cap (Haiku $10.03, Sonnet $11.03, Fable
  $77.24 over both stages, Qwen $9.50). Estimates are rounded to the cent.
- The caps equal the approved budget: $100 of the Anthropic API credit already on the account (the account holds more
  than that) and $9.50 of the OpenRouter balance. The caps count Study 4's own spend logs. Caps are not raised after any
  model result exists.

**Fable stage rule.** Fable runs `locks_s2text` for all 128 clusters first (stage 1, estimate $11.93). `src7/floor_gate7.py`
then counts its failed episodes, and nothing else, and the run script continues with Fable's other three configs
(stage 2) only if at least 5 of the 128 failed. Below that, or if stage 1 is incomplete, stage 2 is not run, Fable's
tests are reported as "not run: floor" (or "not tested"), and the pooled tests use the other models. The count and the
decision are logged. This saves about $36 if Fable is at the floor, where its tests could not show a drop.

**If a cap binds.** The lane stops that block. Episodes are visited instance first within a block, so a stop drops
whole later instances across all families and configs of that block. Tests with at least 75 % of their clusters run as registered (Missing
data). Cells not run are reported as "not tested".

**Manual intervention.** The author does not stop, reorder or restart a lane except after a crash, a credit stop or a
provider outage. Every manual intervention is logged with a timestamp and reported as a deviation.

## Variables

### Manipulated variables

Model; config (`locks_s2text`, `locks_instr`, `locks_signals`, `locks`), that is, instruction (absent, present) ×
signals (absent, present).

### Measured variables

All measures come from `src7/score7.py` and `src7/model_agent7.py` at the frozen hash, with their Study 3 definitions
(the Study 3 registration, Measured variables): `fs_nonserializable` (primary), `dsg_basis_cycle`, `outcome`,
`cap_truncated`, `lock`, `lock_granted`, `lock_scope`, `read_before_lock`, `lock_waits_reported`, `locked_reads`, the
lock-failure mechanisms, `end_reason` and the per-completion fields.

### Indices

None. Rates are cluster means of 0/1 outcomes.

## Analysis plan

### Statistical models

**Analysis code.** `analysis7/analyze7.py` implements the confirmatory tests, the claims, the checks, D1 to D4 and the
sensitivity analyses. Its statistical core and transcript reader (`analysis7/core7.py`) are the frozen Study 3
analysis with the Study 4 grid constants. It was tested before the first paid call (`analysis7/tests_analyze7.py`:
planted effects, the one-sided direction, the interaction, the cluster rule, Holm families, pooling, invalid models,
the floor stop, selection) and run on the dry-run transcripts.

**Tests.** Exact sign-flip permutation test on cluster values, counted over all 2^m assignments (Monte Carlo with
R = 100,000 only if the common denominator exceeds 10,000), as in Studies 2 and 3; the two-sided p of S4-H6 is twice
the smaller one-sided p, capped at 1. Reported, never used for
a decision: the percentile bootstrap p, the exact sign test, the 95 % and 90 % percentile cluster-bootstrap intervals
(unadjusted; the lower end of the 90 % interval is the one-sided 95 % lower bound).

**Bootstrap.** B = 10,000; RNG `random.Random("20261117|{test}|{model}|s4")`, with `{test}` ∈ {H1, …, H6},
`{model}` ∈ {qwen, haiku, sonnet, fable, pooled}, and `|sens{k}` appended in sensitivity analysis k; resampling as in
Study 3.

**Sensitivity analyses.** Registered verdicts stand.

- S1. Excluded episodes kept and scored as they are (changed verdicts reported).
- S2. Template level: the p of the family-mean test of every confirmatory cell (exact sign-flip over 2^8 assignments;
  reported, no Holm and no verdict; no p can fall below 1/256).
- S3. Holm across S4-H1 to S4-H3 within each model (changed verdicts reported).
- S4. `dsg_basis_cycle` in place of `fs_nonserializable` (changed verdicts reported; the floor stays on
  `fs_nonserializable`).
- S5. `cap_truncated` episodes excluded (changed verdicts reported).

### Transformations

None. Outcomes are 0/1 per episode or agent.

### Inference criteria

α = 0.05 (one-sided for S4-H1 to S4-H5, two-sided for S4-H6); Holm within each hypothesis over its tests that run
(up to five). Each family controls FWER at 0.05; claims across
families are not jointly controlled (S3 reports Holm within model). A non-rejection is never reported as evidence of
absence.

### Data inclusion and exclusion

| event | rule | reported |
|---|---|---|
| Provider failure (no completion after the provider's retries) | Not written, not scored; the lane reruns the block (as Study 3). | failures per cell |
| Qwen completion not served by Alibaba | The episode is aborted, not written, and run again. A written Qwen episode with another host is excluded. | per cell |
| An agent ends `truncated`, `provider_error`, `error`, `refusal` or `content_filter`, or its last completion stopped with `content_filter` or `refusal` | The episode is excluded from the main analysis (its cluster then leaves every test that needs that config); S1 keeps it. | per cell |
| More than one transcript for one episode id | The earliest is used; the others are counted. | count |
| Model version drift (`model_served`) | Kept; served versions reported per model. | per model |
| Turn-cap endings, invalid tool calls, `cap_truncated` | Model behaviour: kept and scored. S5. | per cell |
| Dry-run, preflight and validity rows; any unregistered config, unit or model; any control or staggered episode | Never data. | count |

### Missing data

Missing episodes are not imputed. A cluster enters a test only if it has every config the test needs. A test runs
only if at least 96 of its 128 clusters (75 %) enter; otherwise it is "not tested" and leaves its Holm family. The
pooled test applies the rule to the clusters that enter for every pooled model.

### Exploratory analysis

Labelled exploratory; they support no confirmatory claim: per-family breakdowns; the interaction per family;
lease lengths, lock waits, fulfilment, cost, tokens and turns; replies of agents that saw a wait or a locked read.

## Other

### Declared confounds

- **Menu length.** The configs differ in tool-menu length (up to 381 characters). The contrasts cannot separate a
  part's content from its length.
- **The two signals together.** S4-H3 tests the wait report and the locked read as one part; it cannot attribute an
  effect to one of them.
- **Signals depend on behaviour.** A signal appears only when the other agent holds a lock at the right moment. The
  signals contrast measures offering the signals, not seeing them (D4 reports how often they occurred).
- **The wait note repeats part of the instruction.** Its last sentence ("Values you read before this grant may be out
  of date.") is close to the instruction's last sentence. Under `locks_signals` an agent that waited therefore reads
  part of the instruction. S4-H3 and S4-H5 include this.
- **Fable's stages.** Fable's `locks_s2text` episodes run before its other three configs, possibly hours apart; for the
  other models the configs are interleaved by instance. A change in the served model between stages would confound
  Fable's contrasts (C3 reports it); `claude-fable-5` is an undated id.
- **Batch vs sync, temperature and thinking, provider routing.** As in Study 3; Fable runs in batches like Haiku and
  Sonnet. Model is a fixed factor.
- **Studies 1 to 3 to Study 4.** New instances and a new model; no cross-study comparison of rates. S4-H1 replicates
  the Study 3 contrast within Study 4.

### Deviations

A deviation is any departure from this document, and any change to a frozen file after the freeze, bug fixes
included. Each is listed in an appendix table with what changed and why, whether it was made before or after any
Study 4 result was seen, its effect, and where feasible the result under the registered plan. After a harness or
scorer fix, the corrected scoring governs only if the bug fails a check in the frozen tests, the validity table, the
dry-run check or checks C1 and C2; otherwise the registered scoring governs, and both are reported. "Seeing results"
means opening any scored episode or the summary; the logs are read only for failures, cost, progress and the Fable stage
decision.

### Freeze

sha256 of every frozen file, taken after all pre-registration edits and before any paid call. `src7/FREEZE.md` is the
authoritative list for the harness (every `*.py` and `*.json` in `src7`, the gates `gate7.py` and `floor_gate7.py`
included, every `*.py`, `*.json` and `*.sh` in `src7_batch`, `src7_verify/dry_check7.py`, `run_conc_study4.sh`); its
own hash is listed here.

| file | sha256 |
|---|---|
| `src7/FREEZE.md` | `a14bba8e0a99ce0918f1a56bbbae2cc926256dd25bd9b25ec7498f8987b0e00e` |
| `run_conc_study4.sh` | `56f9d459925ab539e3ec9c6baecea879e02585d2c7eef0b70f36aaeb2e617098` |
| `analysis7/analyze7.py` | `eec68bbac58a213230dab31efdbd83222b75d37c0aae499ac02a518b241168cc` |
| `analysis7/core7.py` | `937a139df4efd90d60d2a5339f3a824b2ce0d5ee6fa0c76ce9d6b48aab8b081e` |
| `analysis7/balance7.py` | `2d278aa0e763c2d78855afa92f4f540499ddc40ebe2b32461d0530a009435afe` |
| `analysis7/tests_analyze7.py` | `f0509cd7f8abe4a7cd7432b8dddd61f392972fcbda2d8966585782fded0bd6dc` |
| `analysis7/out/results.json` | `79084c5d040fc368ef81724df6b27f9843b74ed796ca9e0e44bd394c8a7e6628` |
| `analysis7/out/numbers.tex` | `3fdd83d44629e3cf456a49152a9cf27e03537493f258297dd338ce6c5039e8b9` |
| `analysis7/power_study4.json` | `55fc19509796ac9da69fd98616275e27ed8ff3b37423ce79e521d1b65707c7cd` |
| `tools/freeze_table.py` | `df742d6ddbc2f6091eaed072d3699871cbaa69569090ea84f09d10e03b5a2d5e` |
| `tools/make_prior_shapes.py` | `e1a283d18910ad85fab29bebcb9fe5c7645a3e098b096af24f0c955775d6f4cc` |
| `tools/make_study2_costs.py` | `6a14ab3e8c46e32993b49884e1a2ec1ccd3a177c852b7cdb26c25fcaaa144ea5` |
| `tools/make_study2_fixtures.py` | `1d0bda63a756aea82f45cadd665e324cfb0b9553a90bc1ab2e5acf60ed03c90d` |
| `tools/make_study3_costs.py` | `a2d5c6db3400b92143dda79d831e2e2e44dd8432d4c53f7a3e99241fb97d100d` |
| `tools/power7.py` | `fcad84ac0c6c4eeaa5ed76312453fde7e4198c67980ba7d5b0d8961764623353` |

### Data and code availability

The code (MIT licence) and all run outputs (transcripts, ledgers, result files; CC BY 4.0, subject to provider terms
for model outputs) are released with the paper's version 2 in the same public repository and archive as Studies 1
to 3.
