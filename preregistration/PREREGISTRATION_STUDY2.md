# OSF Preregistration: Study 2

Fields follow the OSF Preregistration template, as in the Study 1 registration (osf.io/a5vec). Each `##`/`###` heading below is one OSF form field.

This registration is filed before any paid Study 2 call, the preflight included. The frozen code (see Freeze) implements what it describes. If code and text disagree, this text governs, and we report the difference as a deviation.

Counts and costs come from the final `src5/plan_study2.txt`. Hashes come from `src5/FREEZE.md` and from sha256 of the files listed under Freeze.

## Title

Do LLM agents coordinate on shared records? Study 2: matched uncontended controls, fenced locks and first-reply probes

## Authors

Sanjana Gopnal Swamy, independent researcher.

Linked registration: Study 1, osf.io/a5vec.

## Description

Several LLM agents, each in its own conversation, act on the same versioned records through tool calls. A seeded scheduler interleaves their calls. We vary which coordination primitives are offered and whether the prompt mentions other agents. Every contended task has a matched control in which each agent has a private copy of the records. We measure whether agents use the primitives, when they use them relative to observed contention, and whether the committed outcome is serializable at the specification level. Scoring is deterministic, from a ledger and the server call log. There is no LLM judge.

**Why Study 2 exists.** Four reviews of Study 1 (T1 database, T2 agent evaluation, T3 statistics, T4 adversarial) found flaws that re-analysis cannot fix:

- The only control template, `budget_control`, read peers' records under a shared guard. It was contended in the concurrency sense (G2 cycles in 140 of 144 `cas_available` episodes). Study 1 had no uncontended condition.
- Lock leases counted global scheduler rounds that the agent could not see, and writes were not fenced.
- The 12-call cap ended 20 to 21 % of GPT, Gemini and Fable agents and decided several outcomes.
- Under the CAS configs, `claim` was a server-side test-and-set. The API, not the agent, protected the seat and ticket tasks.
- Aware-off texts still named other agents in several places.
- The two schedules gave almost the same interleaving.
- `non_serializable` was described as Adya serializability. It is final-state equivalence to a serial order of the specified intents.
- Qwen was served by several hosts, and the host mix changed a verdict.
- The registered bootstrap returned its minimum p whenever all clusters sat on one side, and it was liberal on sparse data.

Study 2 uses a new harness (`src5`, `src5_batch`) built to fix these. Pre-spend reviews of that harness (V1, V2, V1b, V2b) and of this registration (T3b, then T3c on the final decision tests) led to further fixes before this freeze. Study 1 data enter no Study 2 estimate.

## Hypotheses

### Common definitions

- **Arm.** Contended (template `T`) or control (`T_ctrl`). In `T_ctrl` each agent has a private copy of `T`'s record group, with the same record count, amounts and wording and a different group tag. No two agents share a record. a0's prompt is byte-identical in the two arms. a1's prompt differs only in the group tag.
- **Pair.** A contended episode and its control with the same model, config, aware level, family, instance and schedule index. The two share the schedule seed and run as a pair.
- **Cluster.** Family × instance, within a model. Qwen, Haiku, Sonnet and Gemini have 7 families × 4 instances = 28 clusters. Schedules, agents and arms are aggregated inside a cluster first.
- **Primitive.** A lock (`acquire_lock`) or a conditional write (a write with `expected_version`). The `locks` config offers only locks, `cas_available` only CAS and `all_available` both.
- **Confirmatory models.** Qwen3.6-27B, Claude Haiku 4.5 and Claude Sonnet 5. GPT-5.5, Gemini 4 Argon and Claude Fable 5 are descriptive only, in every hypothesis. GPT has 6 clusters and Fable 2, which cannot support a test. Gemini locked in its first reply in 128 of 128 Study 1 `locks` agents, its config blocks run in different batch waves (a time confound), and its provider ignores sampling parameters.
- **Eligibility for H4, fixed now.** For each (model, config) we compute the first-reply primitive-use rate: the share of aware-off contended probe agents (a0 and a1) whose `first_reply` code has a `lock` or `cas` token. A model enters **H4** in that config only if this rate is below 0.80. H1 is tested for every confirmatory model.
  - Reason: a model that protects before it has seen anything has no room to respond to contention, so H4's contrast cannot show a response there. H1 asks whether contention adds integrity failures, whatever the protocol, so no eligibility rule applies to it.
  - Denominator: probes excluded under Data inclusion and exclusion leave it. `no_call`, `message`, `read`, `blind_write` and `other` count as no primitive.
  - The rate is computed only if at least 75 % of the registered aware-off contended probes for that (model, config) remain. Otherwise the model is not tested in H4 in that config.
  - The rate is computed by the frozen `analyze5.py eligibility` from probe transcripts only, before any episode result is opened. Its output (`eligibility.json`) and sha256 are posted when the probe block ends (see Freeze). The same file fixes eligibility in every sensitivity analysis.
  - The pooled H4 estimand is the equal-weight mean over the models eligible in that config. It is fixed when `eligibility.json` is posted.
  - Expectation from Study 1 (first-reply lock under `locks`, aware off): Gemini 1.00, GPT 0.98, Sonnet 0.06, Qwen 0.01, Haiku 0.00. We expect all three confirmatory models to be eligible. Fable is not probed (see Study design).
  - Under `cas_available` the rate is near 0 by construction, since a first reply has seen no version.
- **Holm families and gatekeeping.**
  - **H1-eq, stage 1:** the pooled TOST in each of `cas_available`, `locks` and `all_available` (3 tests), Holm at α = 0.05.
  - **H1-eq, stage 2:** the per-(model, config) TOSTs (up to 9), Holm at α = 0.05. They are tested only if all three stage-1 tests were run and rejected. Otherwise each stage-2 cell is reported with its estimate and 90 % interval and labelled "not tested (gate closed)".
  - **H4-eq:** the same scheme, with 2 pooled tests (`locks`, `all_available`) and then up to 6 cells.
  - **Strong control.** Serial gatekeeping controls the familywise error of each equivalence hypothesis at 0.05. If any stage-1 null is true, stage 2 opens only after a stage-1 error.
  - **Difference tests.** H1-diff and H4-diff are each one Holm family over their pooled and per-cell tests (H1-diff up to 12, H4-diff up to 8). H2 is one Holm family over 12 tests. H3 is one Holm family over 3 tests.
  - **No correction across hypotheses.** Sensitivity 6 applies Holm across all confirmatory families within each model, with H1-eq, H1-diff, H4-eq and H4-diff counted as separate members.

### Confirmatory

**H1. Contention adds at most δ integrity failures (equivalence to the matched control).**

- Setting: each confirmatory model; configs `cas_available`, `locks`, `all_available`; aware off; n = 2; 7 families × 4 instances × 2 schedules; both arms.
- Statistic: per cluster, d = mean over the cluster's complete schedule pairs of [`fs_nonserializable`(contended) − `fs_nonserializable`(control)]. Δ = mean of d over clusters.
- Pooled: per config, over the 3 confirmatory models (those that meet the 75 % rule in that config). The pooled cluster value is the mean of the models' d, on the clusters that enter for every pooled model. The pooled Δ is the mean of these values.
- Test H1-eq (TOST): H0 |Δ| ≥ δ, with δ = 0.25 per (model, config) and δ = 0.15 pooled. The TOST p is the larger of the two one-sided p. Equivalence is declared when the test rejects under the gatekeeping above.
- Test H1-diff: H0 Δ ≤ 0 against Δ greater than 0 (contention adds failures), one-sided.
- **Reading per cell, and the claim allowed** (the same for H4, with "primitive uptake" in place of "integrity failures"; pooled tests are read the same way):

  | H1-eq | H1-diff | claim |
  |---|---|---|
  | rejects | does not | "Contention did not add integrity failures beyond ±δ (Δ = x, 90 % [l, u])." |
  | does not | rejects | "Contention added integrity failures (Δ = x, 95 % [l, u])." |
  | rejects | rejects | "Contention added integrity failures, by less than δ (Δ = x, 90 % [l, u])." |
  | does not | does not | "Inconclusive (Δ = x, 90 % [l, u])." No direction is claimed. |

  - "H1-eq rejects" here also needs the cell to be informative (calibration, below) and the equivalence to hold under sensitivity 9 (Statistical models; the exclusion rules are under Data inclusion and exclusion). A cell that fails either is read as if H1-eq did not reject, and the reason is stated. A gate-closed cell counts as "does not".
  - The 90 % interval is the bootstrap-t interval of the TOST. The 95 % interval is the percentile interval of the difference test.
  - Every claim is conditional on these 7 templates, n = 2, this scheduler and these tool texts.
- **Headline claims.**
  - A bound on added integrity failures in a config requires the pooled reading "did not add integrity failures beyond ±δ" for that config (pooled H1-eq rejects with its gates; pooled H1-diff does not). It is written as "contention added at most δ failures (90 % [l, u])". The words "robust" and "no effect" are not used.
  - "Contention added integrity failures: these agents did not protect shared records well enough to prevent them" requires the pooled H1-diff for that config and is stated per config. H1 makes no claim about how often agents used a primitive (H2, H4).
  - A per-model statement requires the per-model test.
  - A model or config that is not tested, gate-closed or inconclusive is named as such in the same sentence.
- Expected direction: Δ greater than 0 for models that rarely protect. H1 is stated as equivalence so that a claim that contention adds at most δ integrity failures needs positive evidence. No result here supports "no added failures".
- **Calibration under `none`** (not part of H1, no Holm): the same two tests, for each confirmatory model and pooled, at raw α = 0.05, with the same margins and no eligibility rule. With versions hidden and no primitive, 5 of 7 families have no correct protocol, so we expect Δ greater than 0. This checks that the contrast can detect failures. It is not a finding about agents.
  - If a model's calibration H1-diff does not reject, an H1-eq equivalence for that model, in any config, is reported as uninformative. The same holds for the pooled tests and the pooled calibration.
  - Per cell and arm we also report the share of episodes with `interleaving.reads_overlap` True.
- Margin: see Sample size rationale.

**H2. Primitive use differs by config.** Two-sided, no predicted sign.

- Setting: confirmatory models; aware off; n = 2. H2a to H2c use episodes, both arms. H2d uses a0 aware-off probes.
- Units and aggregation. For agent-level outcomes (`lock`, `cas`, `first_protective`), an episode's value is the share of its agents with the outcome. H2a to H2c: a unit is (family, instance, schedule, arm) with an episode in both configs; its value is the difference of the two episode values. A cluster's value is the mean over its units (up to 2 arms × 2 schedules). An episode's arm partner is not needed here, but a pair excluded under Data inclusion and exclusion leaves H2 too. H2d: one unit per (family, instance), a0's first reply in both configs.
- Contrasts (Δ = mean over clusters of the cluster value):
  - H2a: lock attempt (`lock`), `all_available` − `locks`.
  - H2b: CAS use (`cas`), `all_available` − `cas_available`.
  - H2c: any primitive (`first_protective` is not None), `locks` − `cas_available`.
  - H2d: first-reply lock (`first_reply` has a `lock` token), `all_available` − `locks`.
- Test: H0 Δ = 0, two-sided sign-flip (see Statistical models). Holm over the 12 tests (4 contrasts × 3 models).
- Why no sign: under `all_available` CAS can replace locks (H2a less than 0). The longer lock description can also draw agents to locks.
- H2c also differs in version visibility (`locks` hides versions). See Declared confounds.

**H3. The aware notice raises first-reply lock use.** One-sided; the confirmatory test of the aware notice.

- Data: first-reply probes, a0 only; configs `locks` and `all_available`; aware off and on. The two prompts of a pair differ only by the notice sentence.
- Statistic: per (family, instance) unit, d = mean over the two configs of [lock_on − lock_off], where lock means `first_reply` has a `lock` token. A unit enters only with an on/off pair in both configs. Δ = mean of d over the (family, instance) units that enter.
- Test: H0 Δ ≤ 0 against Δ greater than 0, sign-flip. Holm over the 3 confirmatory models.
- Claim: a model that rejects is reported as "the notice raised first-reply lock use by x". Nothing is said about a model that does not reject.
- Per-config estimates (over the units with that config) are reported without a test.
- Why probes: aware-on episodes exist only for Gemini. Probes give every model with K greater than 0 both aware levels at the first decision. Probes cannot code CAS, since a first reply has seen no version.

**H4. Reactive primitive use after contention is small (equivalence).**

- Setting: eligible confirmatory models; configs `locks` and `all_available`; aware off; episodes; both arms.
- Agent outcome: under `locks`, `lock` (attempt); under `all_available`, `first_protective` is not None.
- Statistic: Δ = mean over clusters of [contended rate − control rate], each rate over the cluster's agents in its complete pairs (4 per arm when both schedules are present).
- Δ is the total (intention-to-treat) effect of contention on uptake. The first completion's input is the same in both arms (a0) or differs only by a tag (a1, Check 1), so Δ arises after the first completion. It includes uptake caused by contention the agent did not register as a signal.
- Pooled: per config, over the eligible models, as for H1.
- Test H4-eq (TOST): δ = 0.25 per (model, config), 0.15 pooled. Gatekeeping as above.
- Test H4-diff: H0 Δ ≤ 0 against Δ greater than 0.
- Reading and claims: the table under H1, with "primitive uptake".
- **Informativeness gate.** For each H4 cell, q is the mean over its clusters of the share of contended agents that are at risk: `contention_signals` greater than 0 and `protect_before_contention` not True (H4b's denominator). For a pooled test, q is the mean over the pooled models of their q on the pooled clusters. An H4-eq equivalence in a cell with q ≤ δ is reported as uninformative. Otherwise it is reported with the implied bound on the reacting share of at-risk agents, δ / q.
- "Small reactive uptake" requires the pooled H4-eq and the informativeness gate for that config. If either fails, the paper says "reactive uptake could not be bounded below δ".
- Expected: a small positive Δ, about 0.05 to 0.15. At that size H4-eq is often inconclusive, even pooled: pooled power is 0.64 to 0.82 at Δ = 0.05 and 0.22 to 0.32 at Δ = 0.10, and at most α at Δ = 0.15 (Sample size rationale). The registered deliverable is the estimate and its interval. H4-eq can bound reactive uptake only if it is near 0.
- H4b (descriptive, no test): among at-risk contended agents, the share with `protect_before_contention` False, that is, whose first primitive (`first_protective`, lock or CAS, under `locks` too) came after the first signal. Cluster value = that share; clusters with no agent at risk are dropped. Cluster bootstrap 95 % interval. We also report how many at-risk agents have `lock_after_contention` True.
- A lock or CAS call whose own response is the first signal (an acquire that waited, a CAS refused with `version_conflict`) was decided before the signal. `score5` counts it as protection before contention (`≤`), so that agent is not at risk and not reacting.

### Pre-specified checks (not hypotheses)

1. **Leakage check, from the first-reply probe** (not a manipulation check). a0's prompt is byte-identical across arms (checked for every pair by `src5_verify/dry_check5.py`), so the arms cannot differ before the first observation. a1's two prompts differ only in the group tag.
   - Units: (config, aware, family, instance) under `locks` and `all_available`, both aware levels, with both a1 probes. Under `none` and `cas_available` the first-reply lock share is 0 by construction.
   - d = first-reply lock (a1 contended) − first-reply lock (a1 control). Two-sided sign-flip test on the unit values, per model with probes, α = 0.05, no Holm.
   - A rejection means the tag may leak the arm. For that model, H4 is then described as the total effect of the contended template, not as reactive uptake. A non-rejection is reported with its 95 % interval. It is not evidence of no leakage.
2. **Exposure check.** This is the manipulation check of contention: the share of contended agents that actually see another agent's write or lock. An agent is exposed if `contention_signals` is greater than 0 (then `first_contention_call` is not None). Reported per model × config × family with cluster bootstrap 95 % percentile intervals. Controls must show 0. A control agent coded as exposed is a scorer bug: it is fixed, all episodes are rescored and the fix is a deviation.
3. **Isolation and lock safety.** `cross_agent_edges` = 0 in every control episode. `mutual_exclusion_violations` is empty in every episode.

### Pre-specified descriptive (no test, no Holm)

- Integrity by config vs `none` per model, paired by cluster, reported jointly with fulfilment, cap endings, deadlock and agent errors. Also the same contrast among episodes in which every agent ended on its own (`returned`).
- Under `all_available`: the `first_protective` category (none, cas, lock) on update templates (both inventory templates, transfer, budget, joint). The claim templates (seat, ticket) are reported apart.
- Lock use as attempted, granted and effective per model × config × arm; `lock_waits_423`; `fenced_stale_basis`; lock goodput with deadlock episodes as a separate stratum.
- Outcome classes per cell, with the `cap_truncated` stratum (`outcome_stratum`).
- GPT, Gemini and Fable: all of the above and all H1 to H4 statistics, with intervals and no tests, from core and probe blocks only. Extension blocks are reported separately.
- Gemini aware-on episodes (`locks`, `all_available`): failure, fulfilment and the CAS-vs-lock choice. Never pooled with other models or with aware off.
- If the planner cuts a descriptive model's block, its pre-specified descriptive items are reported as not run. Fable has no probe block, so its eligibility rate, H2d, H3 and Check 1 are not run.

## Design plan

### Study type

Experiment on software agents. No human participants. All factors are crossed; nothing is assigned at random. The randomised elements are the instance draws and the schedule seeds (Randomization).

### Blinding

No blinding is involved. Scoring is automated from ledgers and call logs. The harness, scorer, instances, price tables, plan, run scripts and analysis script are frozen before any paid call (see Freeze).

### Study design

**Blocks.** All at n = 2. Probes are priority 0 and run first in each lane. Core blocks are priority 1.

| model | probe cells (config, aware, family, instance): configs × aware × families × K; 3 probed agents each | core: configs × families × arms × instances × schedules | aware in core |
|---|---|---|---|
| Qwen3.6-27B | 4 × 2 × 7 × 6 | 4 × 7 × 2 × 4 × 2 | off |
| Claude Haiku 4.5 | 4 × 2 × 7 × 4 | 4 × 7 × 2 × 4 × 2 | off |
| GPT-5.5 | 4 × 2 × 7 × 2 | 4 × 3 × 2 × 2 × 2 | off |
| Gemini 4 Argon | 4 × 2 × 7 × 8 | `none`, `cas_available`: 2 × 7 × 2 × 4 × 2 | off |
| | | `locks`, `all_available`: 2 × 7 × 2 × 4 × 2 | off and on, same batch waves |
| Claude Sonnet 5 | 4 × 2 × 7 × 4 | 4 × 7 × 2 × 4 × 2 | off |
| Claude Fable 5 | no probe block (cut by the planner) | 4 × 2 × 2 × 1 × 1 | off |

GPT runs the 3 common families: `inventory_last_unit`, `transfer_shared_source`, `budget_write_skew`. Fable runs 2 of them, `inventory_last_unit` and `transfer_shared_source`, because the planner cut Fable's probes and core grid to keep the cost margin (`descriptive_cuts` in `plan_study2.json`). Priority-4 extension blocks (larger GPT and Fable grids) run only while money is left. They are descriptive and never enter a statistic of H1 to H4.

**Models and execution paths:**

| model id | path | note |
|---|---|---|
| `openrouter:qwen/qwen3.6-27b-20260422` | OpenRouter, sync | routed `{"order": ["alibaba"], "allow_fallbacks": false}` |
| `claude-haiku-4-5-20251001` | Anthropic Message Batches | |
| `openrouter:openai/gpt-5.5-20260423` | OpenRouter, sync | host not pinned |
| `openrouter:google/gemini-4-argon-20261013` | Google Gemini Batch API, as `gemini-4-argon` | the Study 1 id, kept for continuity; never through OpenRouter |
| `claude-sonnet-5` | Anthropic Message Batches | undated alias |
| `claude-fable-5` | Anthropic Message Batches | undated alias |

**Configs.**

- `none`: blind writes, versions hidden, last writer wins.
- `cas_available`: versions visible; `update_record` and `claim` take an optional `expected_version` (409 on mismatch).
- `locks`: fenced locks with own-call leases; versions hidden.
- `all_available`: CAS and locks side by side.

No grid config offers messages. The `claim` tool is a plain overwrite in every config.

**Locks.** `acquire_lock(record_id, lease_calls)` returns a per-record `fencing_token`. The lease covers the holder's next `lease_calls` calls of any kind (1 to 20). While a record is locked, writes need the live token. A refused acquire is held by the scheduler for up to 150 rounds and costs one call. A finished agent's locks are released.

**Aware prompt.** When on, one sentence is appended to the system prompt: "Other agents may be reading and writing the same records at the same time as you."

**Templates.** Seven contended templates, each with a matched control (`_ctrl`):

- conflict: `inventory_last_unit`, `seat_same`, `ticket_same`, `transfer_shared_source`;
- still valid: `inventory_still_valid`;
- write skew: `budget_write_skew`, `joint_account_write_skew`.

**Instances.** Instance i of a family uses wording i mod 2. Record names come from neutral word pools, with no agent ids. Multi-record guard texts list records in sorted order for every agent. Every instance is disjoint from Study 1 and its pilot (tested).

**Probes.** One completion per agent from its initial prompt and tool menu. Nothing is executed. For each (config, aware, family, instance) we probe a0 contended, a1 contended and a1 control. a0 is not probed under the control because its prompt is identical.

**Fixed settings** (`design5.py`, `world5.py`, `model_agent5.py`):

- call cap per agent: `call_cap(2, config)` = 24 under `none` and `cas_available`, 28 under `locks` and `all_available`; at most cap + 1 completions;
- max_tokens 4096; temperature 0 requested; no reasoning or thinking parameter sent;
- lock lease 1 to 20 own calls; lock wait 150 rounds;
- scheduler: start offset U{0..6}; think time U{0..4} before every completion; extra call latency U{1..2} with probability 0.3; round order reshuffled every round; stall after 6 idle rounds; max 3,000 rounds;
- Anthropic prompt caching on.

### Randomization

- Instances: `random.Random("src5-study2-v1|{family}|{i}")`, with a suffixed redraw key on a clash with Study 1. A control uses its family's draw, so `T@i` and `T_ctrl@i` have identical numbers.
- Schedules: seed = sha256 of ("src5-schedule-v1", family, instance, schedule index, n). A contended episode and its control share it. Draws are indexed by each agent's own counters, so the same seed and the same behaviour give the same ledger (tested).
- Visit order: schedule index first, then instance, family, config, aware, model and arm. The contended episode and its control run as an adjacent pair.
- Model outputs are not seeded. Seeds control the environment only.

## Sampling plan

### Existing data

Registration prior to creation of data. No Study 2 model call has been made.

### Explanation of existing data

- **Study 2 runs with no model.** Scripted reference policies (validity table, 23,808 episodes, $0) and a full dry run with fake models ($0). These test the harness and the analysis script. They contain no model behaviour and are not data.
- **Study 1** (5,760 episodes, six models) is complete, and the author has seen all of it. It shaped this design: the cost estimates, the confirmatory model set, the eligibility expectation and the H3 effect sizes (Study 1 aware effect on first-reply lock use: Sonnet +0.60, Qwen +0.28). Study 1 data enter no Study 2 estimate. Lock semantics, tool texts and the scheduler changed, so we make no cross-study comparison of lock rates.

### Data collection procedures

`bash run_conc_study2.sh` runs three provider lanes in parallel: Anthropic (batch), OpenRouter (sync), Gemini (batch).

1. Before the script starts, `python3 analysis5/balance5.py --phase before` logs the OpenRouter key's usage (see Starting and stopping rules). It makes no model call.
2. Gates before any spend: `freeze5.py --check` against `src5/FREEZE.md`, then the validity gate (scripted agents, no cost).
3. Preflight: one small request per model. Qwen must be served by Alibaba. Gemini must pass a two-turn parallel-call check. Preflight output is not data.
4. The Gemini lane starts first (`LANES=(gemini anthropic openrouter)`). Each lane runs its blocks in priority order: probes, then core, then extensions. Order inside a lane: Gemini aware-off `none`/`cas_available`, then `locks`/`all_available` with both aware levels; Anthropic Haiku, Sonnet, Fable; OpenRouter Qwen, GPT.
5. When the OpenRouter lane ends, `balance5.py --phase after --lane-exit {code}` logs the key's usage again. The same two lines are logged around any resumed run of that lane.
6. Every transcript, ledger, spend log, balance log and failure log is kept.

### Sample size

| model | probe episodes | a0 probes per (config, aware) | core episodes | episodes per (config, arm), aware off | clusters |
|---|---|---|---|---|---|
| Qwen | 672 | 42 | 448 | 56 | 28 |
| Haiku | 448 | 28 | 448 | 56 | 28 |
| GPT-5.5 | 224 | 14 | 96 | 12 | 6 |
| Gemini | 896 | 56 | 448 aware off + 224 aware on | 56 (also 56 per arm aware on, `locks` and `all_available`) | 28 |
| Sonnet | 448 | 28 | 448 | 56 | 28 |
| Fable | 0 | 0 | 16 | 2 | 2 |

Total: 2,688 probe episodes (4,032 probed agents) and 2,128 core episodes. A probe episode is one (config, aware, family, instance, template): the contended one probes a0 and a1, the control one probes a1, so each (config, aware, family, instance) has 2 probe episodes and 3 probed agents. The 75 % rule for eligibility counts contended probe episodes; the eligibility rate itself is over probed agents.

- The confirmatory cells (Qwen, Haiku, Sonnet) have 56 episodes per config × arm: 7 families × 4 instances × 2 schedules.
- GPT has 12 per config × arm (3 families × 2 instances × 2 schedules).
- Fable has 2 per config × arm (2 families × 1 instance × 1 schedule) and no probes. Fable is descriptive only. It enters no test, no pooled estimate and no eligibility rate.
- Gemini and GPT are descriptive too (Common definitions).

### Sample size rationale

Sample size is set by prepaid credit, not by a power target. The power below says what each test can and cannot show. All figures come from the registered procedures (bootstrap-t TOST, sign-flip, the Holm and gatekeeping levels), simulated on the T3b generator: 28 clusters, ICC ρ = 0.3 within an arm-cluster, correlation r between the two arms of a pair, cross-model cluster correlation ρ_m for pooled tests; 1,000 to 4,000 runs each, B = 1,000. Scripts and outputs: `analysis5/power_sims/` (archived with this registration; numpy and scipy, not part of the analysis).

**Why these margins.** δ is not a negligible effect.

- In the validity table, scripted policies with no protocol (`naive`, `rereader`) raise `fs_nonserializable` under contention by 0.34 to 0.97 in every family, against 0 in the controls. Both margins lie below 0.34, so an equivalence result excludes effects of the size an agent with no protocol produces.
- Within that bound, each margin is the smallest multiple of 0.05 that this sample can reach: 80 % TOST power at a true Δ of 0 at the first step of its stage (α/3 pooled, α/9 per cell for H1), at a stated common failure rate.
  - H1 pooled, δ = 0.15 reaches 80 % up to a common rate of about 0.10 (ρ_m = 0.3) or 0.07 (ρ_m = 0.6).
  - H1 per model, δ = 0.25 reaches 80 % up to a common rate of 0.05 at the first step (α/9), and up to 0.15 at the last step (α).
  - H4 uses the same margins. Per model, δ = 0.25 reaches 80 % at α/6 up to a common rate of about 0.15. Pooled, δ = 0.15 reaches 80 % at α/2 up to about 0.20 (ρ_m = 0.3).
  - The reference rates are a judgement: a model that coordinates well has low failure in both arms, and that is the case the equivalence tests are for.
- **δ = 0.10 pooled, the margin of an earlier draft of this registration, cannot be reached.** Its stage-1 power is 0.66 at a common rate of 0.05 and 0.30 at 0.10 (ρ_m = 0.3). δ = 0.20 per model reaches 80 % at the first stage-2 step only at a common rate of about 0.03 to 0.04. We changed both margins before any data for this reason.
- The margins do not show that contention is harmless. Every equivalence result is written as "Δ excluded beyond ±δ (90 % interval [l, u])", never as "no effect" or "equivalent" alone.

**TOST power at a true Δ of 0, H1** (2 episodes per arm-cluster, r = 0 to 0.3):

| test | common rate | α (last step) | first step of its stage |
|---|---|---|---|
| per model, δ = 0.25 (first step α/9) | 0.03 | 0.99 | 0.94 |
| | 0.05 | 0.97 | 0.82 to 0.84 |
| | 0.07 | 0.96 | 0.74 |
| | 0.10 | 0.90 to 0.93 | 0.53 to 0.62 |
| | 0.15 | 0.84 to 0.87 | 0.32 to 0.40 |
| pooled over 3 models, δ = 0.15 (first step α/3), ρ_m = 0.3 / 0.6 | 0.05 | 0.99 / 0.95 | 0.94 / 0.86 |
| | 0.07 | 0.98 / 0.93 | 0.91 / 0.80 |
| | 0.10 | 0.93 / 0.88 | 0.80 / 0.69 |
| | 0.15 | 0.86 / 0.75 | 0.61 / 0.46 |
| for comparison: pooled, δ = 0.10 | 0.05 | 0.85 / 0.74 | 0.66 / 0.54 |
| | 0.10 | 0.59 / 0.46 | 0.30 / 0.20 |

**TOST power at a true Δ of 0, H4** (4 agents per arm-cluster, r = 0.5):

| test | common rate | α (last step) | first step of its stage |
|---|---|---|---|
| per model, δ = 0.25 (first step α/6) | 0.10 | 0.99 | 0.88 |
| | 0.20 | 0.96 | 0.73 |
| | 0.30 | 0.92 | 0.61 |
| | 0.50 | 0.87 | 0.47 |
| pooled over 3 models, δ = 0.15 (first step α/2), ρ_m = 0.3 / 0.6 | 0.10 | 0.99 / 0.97 | 0.97 / 0.93 |
| | 0.20 | 0.94 / 0.85 | 0.86 / 0.75 |
| | 0.30 | 0.87 / 0.76 | 0.78 / 0.62 |
| | 0.50 | 0.80 / 0.65 | 0.66 / 0.45 |

**The whole procedure** (true Δ = 0 in every cell, ρ_m = 0.3):

- H1: the gate opens with probability 0.99, 0.95 and 0.81 at common rates 0.02, 0.05 and 0.10. A given cell is then declared equivalent with probability 0.98, 0.90 and 0.68.
- H4: the gate opens with probability 0.95, 0.77 and 0.60 at common rates 0.10, 0.20 and 0.30; a given cell, 0.93, 0.69 and 0.47.
- One config where contention adds failures closes the gate for every cell of that hypothesis. Then no per-model equivalence is tested.

**With a true Δ greater than 0.** Pooled H4-eq at α/2: power 0.64 to 0.82 at Δ = 0.05 and 0.22 to 0.32 at Δ = 0.10 (common rate 0.10 to 0.20). Pooled H1-eq at α/3: 0.55 to 0.73 at Δ = 0.05 and 0.15 to 0.23 at Δ = 0.10 (common rate 0.05 to 0.10).

**Size at the boundary.** With contention adding exactly δ (a true null), at control rates 0 to 0.20:

- with the added failures spread evenly over clusters, bootstrap-t rejected 0.042 to 0.057 at α = 0.05 (4,000 runs, MC SE 0.0035), and at most 1.34 times nominal at the smallest level each test meets in its stage. With the added failures concentrated in a few clusters (cluster ICC of the contended rate 0.6 to 0.9; analysis5/power_sims/t3c/), a single per-cell H1 TOST rejected up to 0.028 at α/9 (5 times nominal; T3c); pooled and H4 tests stayed within 1.1 times nominal at the first step of their stage;
- the percentile bootstrap of that earlier draft rejected up to 0.081 at α = 0.05 and up to 2.2 times nominal at α/3;
- the whole two-stage procedure had a familywise error of 0.016 to 0.063 (1,000 runs each, MC SE 0.007) in 10 configurations with true nulls at the boundary. The largest, H4 pooled at its boundary, is the size of one test at α; a 4,000-run check of that test gave 0.056. With one model at its per-cell boundary in 1 or 3 configs and its added failures concentrated in a few clusters, the H1 procedure's familywise error was 0.006 to 0.031 (12 configurations, 2,000 runs each; T3c);
- the sign-flip test is exact. Under sparse symmetric nulls its size at α/12 was 0 to 0.0015 (nominal 0.0042).

**Reading the tables.**

- Per model, δ = 0.25 is powered at 80 % when the common failure rate is at most about 0.05 at the first Holm step, and at most about 0.15 at the last.
- Pooled, δ = 0.15 is powered at 80 % when the common rate is at most about 0.07 to 0.10, depending on how strongly the models' cluster effects are correlated.
- At higher rates, or with a true Δ greater than 0, "inconclusive" is the expected reading.
- If fewer than 3 models enter a pooled test, it has less power. It is still run with 2 models and reported as such. With fewer than 2 it is not run, and the gate is closed.

**Minimum detectable differences** for the other tests (two-sided normal approximation, p = 0.5, `plan5.py`):

- H2a to H2c: about 0.22 to 0.31 per contrast.
- H2d and H3, per config (a0 probes, paired r = 0.3): Qwen 0.256, Haiku 0.313, Sonnet 0.313. H3 pools two configs, which lowers these to about 0.18 to 0.22.
- GPT (6 clusters) and Fable (2 clusters) have MDDs above 0.6. They are descriptive.

The plausible reactive effect (0.05 to 0.15) is below every per-model MDD. That is why H4 is an equivalence test and not a superiority test.

### Starting and stopping rules

The design is fixed. There is no optional stopping on results.

**Budget caps.** One cap per provider (prepaid credit) plus a total, enforced by `budget5` over every Study 2 spend log:

| provider | estimate | × 1.15 safety | cap |
|---|---|---|---|
| Anthropic | $13.76 | $15.82 | $19 |
| OpenRouter | $21.37 | $24.58 | $28 |
| Gemini | $16.02 | $18.42 | $22 |
| total | $51.15 | $58.82 | $69 |

- Estimates price the tool text from the code and use Gemini's November batch price. After the 1.15 factor each provider stays at least 10 % below its cap (Anthropic 16.7 %, OpenRouter 12.2 %, Gemini 16.3 %).
- Before each pair (sync) or batch wave (batch), the worst-case estimate of the whole pair or wave must fit in what is left for the provider and the total. Overshoot is at most one completion (tested).
- Each core block also has a per-model sub-cap of 1.3 × its cumulative estimate.
- Caps are not raised after any model result exists.

**If a cap binds.**

- The lane stops that block and moves to the next one. Probes run first. In each lane the confirmatory models run before the descriptive ones (Haiku and Sonnet before Fable; Qwen before GPT).
- Episodes are visited schedule index first, then instance, then family. The contended episode and its control run as a pair, and a pair starts only if both fit. A stop therefore drops whole later replicates. A finished episode whose partner did not run is held back (`held_for_pair/`) and is never data.
- A cap stop changes precision, not the estimand. Which units a stop drops depends on visit order, not on outcomes. Tests with at least 75 % of their units run as registered.
- Cells not run are reported as "not tested", never as a null result. The rules for partial clusters are under Missing data.
- **Gemini price risk.** Google's batch price for Gemini 4 Argon doubles from 2026-11-30T00:00Z (`src5_batch/prices_batch.json`). At that price the Gemini blocks cost $32.03 ($36.83 after the 1.15 factor), above the $22 cap. The Gemini lane starts first and by 2026-11-25. If it is not done by 2026-11-30, the cap stops it and the rule for an incomplete lane applies: whole later pairs are not run, the cells run are reported, and a test below the 75 % rule is "not tested". Gemini is descriptive, so no confirmatory test changes.

**Shared OpenRouter key.** The OpenRouter key is shared with another project, and `budget5` counts only Study 2's spend logs.

- Spend by others is measured, not prevented. `analysis5/balance5.py` logs the key's usage before and after the OpenRouter lane, and around any resumed run (`openrouter_balance.jsonl`). In each window, spend by others = the change in key usage − the Study 2 OpenRouter spend logged in that window. `analyze5.py` reports it per window.
- If the lane stops on a credit or key limit (run5 exit 4, HTTP 402) and others spent in that window, the lane is reported as **stopped by an external cause**, with the time and the balance log. This is not a cap stop.
- The episodes of a stopped lane stay in the confirmatory tests. They are excluded only if their paired controls are incomplete, which the pair rule above already enforces: an episode without its partner is never data. Each test then runs under the 75 % rule.
- The lane may be resumed after a top-up, with no change to the plan. The top-up, the gap and the resume are reported as a manual intervention.

**Manual intervention.** The author does not stop, reorder or restart a lane except after a crash, a credit stop or a provider outage. Every manual intervention is logged with a timestamp and reported as a deviation.

## Variables

### Manipulated variables

Model; config (`none`, `cas_available`, `locks`, `all_available`); arm (contended, control); aware prompt (off, on; on in probes for every probed model and in core episodes for Gemini `locks` and `all_available` only).

### Measured variables

All measures come from `src5/score5.py` (`score` returns `EpisodeScore` with one `AgentScore` per agent) and `src5/model_agent5.py`, at the frozen hash.

**Episode level.**

- **`fs_nonserializable` (primary).** Specification-level final-state serializability over agent sessions: no serial order of the committed agents' intents, applied one after another starting from the initial state, reproduces the final store (`serial_witness` returns None). Committed agents have a value-changing write they did not roll back (`tasks5.rolled_back_agents`). It is not Adya or Berenson serializability of the executed history. It can be true on an acyclic history (a half transfer).
- **`dsg_basis_cycle` (secondary).** The per-write basis DSG (`basis_edges`, `find_cycle`). Each committed write depends on its writer's latest successful read, before that write, of each record its intent reads. Rolled-back sessions are aborted.
- Also reported, never as a cross-check of fs: `dsg_cycle` (all reads, `dependency_edges`), `dsg_cycle_committed`, `dsg_g1c`. On the validity runs fs and the all-reads DSG disagree in 1,992 of 23,808 episodes, and fs and the basis DSG in 428.
- **`outcome`**, one of:
  - `clean`: fs-serializable, no constraint ever violated, no hard flag, no rollback;
  - `compensated`: only rollback flags, final state fs-serializable and not violated;
  - `failed`: every other episode.
  `clean` is specification-level. It can sit on a cyclic committed history.
- **`cap_truncated`** (flag) and **`outcome_stratum`.** `cap_truncated` is True for a `failed` episode in which some agent ended at the call cap (`end_reason == "turn_cap"`), whether or not that agent fulfilled its intent. `outcome_stratum` is `outcome`, with such episodes shown as `cap_truncated`. The `outcome` itself stays `failed`.
- Non-exclusive flags: `missing_leg`, `compensated`, `compensated_after_violation`, `compensation_exposed`, `guard_violation`, `wrong_value`, `out_of_intent_write`, `stale_overwrite`, `lost_update`, `laundered_cas`, `write_skew`, `ever_violated`, `violated_at_end`, `fenced_stale_basis`. `primary_label` is for compact tables only.
- `cap_endings`, `deadlock`, `deadlock_rounds`, `agent_errors`, `cross_agent_edges`, `cross_agent_record_edges`, `stall`, `interleaving` (with `reads_overlap`).

**Agent level.**

- **`lock` (lock attempt, primary lock measure).** At least one well-formed `acquire_lock`, granted or refused with 423 after the wait. Malformed calls (for example lease above 20) do not count.
- `lock_granted`: at least one acquire granted.
- **`lock_effective`.** Defined for agents that were granted a lock and committed a write: True if every committed write was fenced, and each fenced write's basis (a read of that record, or the agent's own write) lies inside the lease of the token it carries (no `fenced_stale_basis`, no `fenced_unread_basis`). A blind fenced write is not effective. None otherwise.
- `lock_waits`, `lock_waits_granted`, `lock_waits_423`, `fenced_stale_basis`, `fenced_unread_basis`, `lock_leak`.
- **`cas`.** A write with `expected_version` that committed or was refused with `version_conflict`. A refusal for `invalid_version` (a version the record never had) does not count for `cas` but does count for `first_protective`. We keep this rule as coded and state it in every table.
- **Timing** (`score5._protection_timing` over `score5.peer_signal_calls`):
  - `first_protective` (lock or cas) and `first_protective_call` (own-call index);
  - `first_contention_call`: own-call index of the first signal caused by another agent. A signal is: a 423; a 409 for `version_conflict`, or for `stale_fencing_token` when another agent locked the record since; an acquire the scheduler held (`waited_rounds` greater than 0); a granted acquire on a record another agent had locked before; a read returning a version that another agent installed; a committed write whose response shows it overwrote another agent's version; or a delivered message from another agent (`all_peer_informed` only, never in the grid). The agent's own lease expiry, its own invalid version and a read of its own write are not signals;
  - `contention_signals`: the number of such calls (exposure);
  - `protect_before_contention`: True if the first protective call was at or before the first signal (`≤`), or the agent protected and saw no signal; False if after; None if it never protected;
  - `first_lock_call` and `lock_after_contention`: True if the agent's first well-formed `acquire_lock` came after its first signal, False if at or before it or with no signal, None if it never tried to lock.
- `fulfilled`, `rolled_back`, `end_reason`, `abandoned`, `unnecessary_give_up`, `turns`. `end_reason` is `returned`, `turn_cap`, `stalled`, `max_rounds`, `error`, `truncated`, `provider_error`, `refusal`, `content_filter` or `probe`. The end reasons `refusal` and `content_filter` mark a reply with no tool call that stopped for a refusal (Anthropic `stop_reason` `refusal`) or a safety filter (OpenRouter `finish_reason` `content_filter`; for Gemini, finishReason SAFETY, RECITATION, PROHIBITED_CONTENT, BLOCKLIST or SPII, or a blocked prompt). These agents never count as abandoning and are not in `agent_errors`.
- **`first_reply`** (`model_agent5.first_reply_code`): the code of the first completion's tool calls: `lock`, `cas`, `blind_write`, `read`, `message`, `other`, `no_call`, joined with `+`. "Has a `lock` token" means one of the `+`-separated parts is `lock`. A first reply cannot carry a version it has seen, so `cas` there is a guess.

**Per completion.** Tokens, cost, `model_served` (for Gemini, the response's `modelVersion`), `served_host`, `temperature_effective`, `reasoning_tokens`, `thinking_blocks`, `thinking_chars`, `stop_reason`, `max_tokens_exceeded`.

### Indices

None. Rates are cluster means of 0/1 outcomes as defined under each hypothesis.

## Analysis plan

### Statistical models

**Analysis code.** `analysis5/analyze5.py` implements the confirmatory tests, the claim per cell, the checks, H4b, the budget report and sensitivity analyses 1 to 9. Its `eligibility` command produces `eligibility.json` from probe transcripts only. It was written and tested before the first paid call (`analysis5/tests_analyze5.py`: planted effects, exclusions, determinism, and size and power checks of the decision tests), run on the dry-run transcripts, and is listed in the Freeze table. Its dry-run outputs are archived with this registration. `eligibility.json` is produced by the frozen script without change and posted with its sha256 when the probe block ends. The pre-specified descriptive tables, the cross-model regression and the exploratory analyses come from a separate script; they support no confirmatory claim. If code and text disagree, this text governs and the difference is a deviation.

**Aggregation.** A cluster enters a test only with the pairs the test needs (see Missing data). Inside a cluster, schedules, agents and paired conditions are aggregated first, which gives one value per cluster; the estimate is the mean of these values. The estimand is the mean over these 7 templates, each weighted equally (4 instances each). Clusters are resampled without stratification. That is conservative for this estimand, and no confirmatory claim extends to other templates. Sensitivity 7 is the template-level check.

**Pooled tests.** A pooled test uses the clusters that enter for every pooled model. Its cluster value is the mean of the models' cluster values, so one resample or one sign flip acts on all models at once. It runs only with at least 2 models and only if at least 75 % of the registered clusters enter.

**Decision tests.**

- **θ0 = 0** (H1-diff, H2, H3, H4-diff, the calibration H1-diff, Check 1): exact sign-flip permutation test on cluster values.
  - One-sided p is the share of the 2^m sign assignments whose sum is at or above the observed sum (at or below, for the other direction).
  - The count is exact: it is computed over all 2^m assignments by dynamic programming, with the cluster values written as integers over their common denominator. Only if that denominator exceeds 10,000 is the test Monte Carlo, with R = 100,000 sign vectors from `random.Random({key} + "|signflip").getrandbits(m)` (bit j flips the j-th cluster in sorted order) and p = (1 + #{S* ≥ S}) / (R + 1).
  - Two-sided p (H2, Check 1) is twice the smaller one-sided p, capped at 1.
- **TOST sides (θ0 = ±δ):** studentized cluster bootstrap (bootstrap-t), B = 10,000.
  - t = (Δ̂ − θ0) / SE, with SE = sd(d) / √m (sd with m − 1).
  - t*_b = (Δ̂*_b − Δ̂) / SE*_b. When SE*_b = 0 (a resample with no spread), the observed SE is used in its place.
  - For H0 Δ ≥ +δ: p = (1 + #{t*_b ≤ t}) / (B + 1). For H0 Δ ≤ −δ: p = (1 + #{t*_b ≥ t}) / (B + 1). Ties count against rejection.
  - TOST p is the larger of the two.
  - If all cluster values are equal (SE = 0), the decision p of each side is the exact one-sided sign test against θ0 (ties dropped).
  - Why the SE*_b rule: with rare failures many resamples have no spread. Setting their t* to ±∞, as T3b proposed, capped power at about 0.5 to 0.6 when both arms fail at a rate of 0.01 to 0.03, whatever δ. With the observed SE in their place, power there was 0.96 to 1.00 at α. The cost: when added failures are concentrated in a few clusters, a single per-cell TOST at its boundary is liberal at small levels (up to 5 times nominal at α/9), while the two-stage procedure keeps its familywise error at or below 0.031 (Sample size rationale). The registered error rate is the family's.
- **Reported for every test and never used for a decision:** the percentile-count bootstrap p (the Study 1 procedure, without its fallback), the exact sign test, and the 95 % and 90 % percentile intervals. For each TOST we also report the 90 % bootstrap-t interval and the Holm-consistent bootstrap-t interval at 1 − 2α_adj, where α_adj is the Holm level at which that test was compared.
- **Reason.** In the T3b simulation, at Δ = +δ the percentile bootstrap rejected 0.08 at α = 0.05 and 0.016 at α/12, against 0.05 and 0.006 for bootstrap-t. With 3 of 28 clusters at +0.5 and the rest at 0, it gave p = 0.040, against an exact p of 0.125.

**Bootstrap.** Cluster bootstrap over the cluster values, B = 10,000 resamples with replacement. The RNG is `random.Random("20261103|{test}|{model}|{config}")`:

- `{test}` ∈ {H1eq, H1diff, H1caleq, H1caldiff, H2a, H2b, H2c, H2d, H3, H4eq, H4diff, H4b, check1, check2};
- `{model}` ∈ {qwen, haiku, gpt, gemini, sonnet, fable, pooled};
- `{config}` is the config name; `cfgA-cfgB` for H2 (as listed under H2); `locks+all_available` for H3 and Check 1; `{config}|{family}` for Check 2, with `|aware` appended for aware-on cells;
- in sensitivity analysis k, `|sens{k}` is appended.

Clusters are taken in sorted key order. Resample b uses draws b·m to (b + 1)·m − 1 of `rng.choices(range(m), k = m·B)`. A percentile interval at level 1 − 2a is [s[⌊aB⌋], s[⌈(1 − a)B⌉ − 1]] of the sorted resample means s. The bootstrap-t interval is [Δ̂ − q_(1−a) SE, Δ̂ − q_a SE], with q taken from the sorted t* by the same rule.

**Monte Carlo resolution.** Every Monte Carlo p within 2 MC standard errors of the Holm level it is compared with is recomputed with 10 times the draws (B = 100,000; R = 1,000,000) under the key plus `|mc2`. The recomputed value governs, and Holm is applied once more. Exact sign-flip p-values are never recomputed.

**Cross-model comparisons.**

- Only on the 3 common families (`inventory_last_unit`, `transfer_shared_source`, `budget_write_skew`), aware off, all four configs. Fable contributes its 2 families.
- Model: Firth-penalized logistic regression (model, config, arm, family; model × config × arm). Intervals come from a wild cluster bootstrap (Rademacher weights, 9,999 draws, clustered on family × instance), with CR2 standard errors reported beside them. Cells with no events in either arm are reported as counts and left out of the model.
- Outcomes: `fs_nonserializable` (episode) and `lock` (agent).
- Contrasts among Qwen, Haiku and Sonnet are reported with 95 % intervals. GPT, Gemini and Fable estimates are shown with intervals and labelled descriptive.
- Nothing from this model supports a confirmatory claim. Models differ in decoding settings (Declared confounds), so we make no claim about a model's "disposition" without that caveat.
- Gemini aware-on episodes are excluded from every pooled estimate.

**Sensitivity analyses.** Each reruns the confirmatory tests, with the same Holm families and gatekeeping, and reports changed verdicts. Registered verdicts stand. A sensitivity that changes a verdict is reported next to it, in the main text.

1. **24-call cap.** Episodes under `locks` and `all_available` are re-scored from their logged ledgers as if each agent had stopped at its 24th own call (`score5.rescore_at_cap`, cap 24). Its status is `unchanged` (no agent made more than 24 calls), `rescored` (the cut is applied; peers' later calls are kept because none depended on the cut calls) or `indeterminate` (a peer's later call touched a record the cut agent changed, locked or held after its cut, a peer read a message it sent after the cut, or another agent ended stalled or at the round limit). An `indeterminate` episode is dropped with its partner. Counts are reported per cell and arm. This equalizes the cap across configs.
2. `cap_truncated` episodes excluded, with their pair partners.
3. Episodes excluded under Data inclusion and exclusion kept and scored as they are, with no partner excluded.
4. Within the majority served version, for any model whose `model_served` changed during the run: the majority is over episodes and probes; only rows served entirely by the majority value are kept; pairs whose two episodes differ are counted.
5. GPT episodes with any non-OpenAI host excluded (descriptive).
6. Holm across all per-(model, config) tests of H1-eq, H1-diff, H2, H3, H4-eq and H4-diff within each confirmatory model, without gatekeeping, in place of Holm within each hypothesis. Pooled tests are not within a model and are left out.
7. Template level, on the 7 family means of the cluster values (pooled cluster values for pooled tests). For TOST cells: a t-test (df 6) on the family means at −δ and +δ, the larger p. For θ0 = 0: the exact sign-flip test over 2^7 = 128 assignments (two-sided: twice the smaller side, capped at 1). Reported, not a decision.
8. H1 and its calibration with `dsg_basis_cycle` in place of `fs_nonserializable`.
9. **Against equivalence.** Every pair excluded under Data inclusion and exclusion enters as written, scored against equivalence: in the contended episode, `fs_nonserializable` = 1 and the errored agents count as having used a primitive (`lock` and `first_protective`); the control enters as scored. Probes enter as written.

**Rule.** An H1-eq or H4-eq equivalence is claimed only if it also holds under sensitivity 9. Sensitivities 1 to 3 drop or re-score contended episodes more often than controls, so they cannot support an equivalence claim.

Study 1 data are not reused in any sensitivity analysis.

### Transformations

None. Outcomes are 0/1 per episode or agent.

### Inference criteria

- One-sided α = 0.05 where directional (H1-diff, H3, H4-diff, each TOST side). Two-sided α = 0.05 for H2 and Check 1.
- Holm within each test family, with gatekeeping for H1-eq and H4-eq (Common definitions). Family members are the per-(model, config) tests and the pooled tests that the family covers.
- Each hypothesis family controls FWER at 0.05. Claims across families are not jointly controlled (see sensitivity 6). When different cells have different true nulls, the chance of at least one false H1 claim across H1-eq and H1-diff can reach 0.10, and across all confirmatory families about 0.3.
- H1 and H4 are read per cell by the claim table under H1. A non-rejection is never reported as evidence of absence. An equivalence in an uninformative cell (H1 calibration, H4 q gate) is reported as uninformative.
- For a model that does not reject, we make no claim.

### Data inclusion and exclusion

| event | rule | reported |
|---|---|---|
| Provider failure (no completion after the provider's retries) | Not written, not scored. Sync: the lane reruns the block until it is done, and stops after 10 attempts without progress. Batch: up to 5 tries per request, and the lane reruns the driver up to 5 times. | failures per cell |
| Qwen completion not served by Alibaba | `ProviderFailure`: the episode is aborted (spend counted), not written, never scored, and run again by the lane's retry loop as above. A written Qwen episode with another host is excluded with its partner. | per cell |
| An agent ends `truncated`, `provider_error` or `error` (harness error end) or `refusal` or `content_filter` (refusal or safety stop), or its last completion stopped with `content_filter` (OpenRouter, Gemini) or `refusal` (Anthropic) | The harness does not re-run written episodes. The episode (or probe) and its pair partner are excluded from the main analysis. Sensitivity 3 keeps them; sensitivity 9 scores them against equivalence. | per cell and arm |
| More than one transcript for one episode id | The earliest (`run_info.started_utc`, then file name) is used. The others are counted. | count |
| GPT completion from a non-OpenAI host | Kept and flagged. Sensitivity 5. | per cell |
| Model version drift (`model_served` changes; undated aliases `claude-sonnet-5`, `claude-fable-5`, `gemini-4-argon`) | Kept. Sensitivity 4. Pairs whose two episodes have different served versions are flagged. | served ids per model |
| Dated id served as a different id | Kept, flagged. | served ids per model |
| Turn-cap endings, invalid tool calls, refusals with a tool call, `cap_truncated` | Model behaviour: kept and scored. Sensitivities 1 and 2. | per cell |
| Extension-block (priority 4) and unplanned rows | Never enter H1 to H4. Counted. | count |
| Dry-run, preflight and validity rows | Never data. | |

- A probe's partner is the other-arm probe of the same model, config, aware level, family and instance (a1 only; an a0 probe has no partner and leaves alone).
- **Symmetry.** Exclusions are counted per arm and per cell. Errors and refusals scale with the number of completions, and contended episodes are longer, so they are excluded more often; the contended episodes that survive are those that did not fail that way, a bias toward equivalence. Sensitivity 9 and its rule guard against this.

### Missing data

- Missing episodes are not imputed.
- Paired tests use complete pairs only. An episode whose partner is missing or excluded is excluded and listed.
- A cluster enters a test if it has at least one complete pair for every condition the test needs. Its value is the mean over the pairs it has.
- A test runs for a model only if at least 75 % of its registered units enter: clusters for episode tests (21 of 28), (family, instance) units for probe tests (7 × K). For a test that spans two configs (H2, H3) the units must be present in both. Otherwise it is "not tested" for that model: it leaves its Holm family, the family shrinks, and its partial cells are reported descriptively.
- A pooled test applies the 75 % rule to the clusters that enter for every pooled model (Statistical models).
- Eligibility for a (model, config) is computed only if at least 75 % of its registered aware-off contended probes remain. Otherwise the model is not tested in H4 in that config.

### Exploratory analysis

Labelled exploratory. They support no confirmatory claim.

- Per-family and per-wording breakdowns of every measure.
- Configs vs `none` on `cas`, reread and `first_protective`; aware effects on `cas` and reread in Gemini episodes.
- `lock_effective` and `fenced_stale_basis` by model; lease lengths chosen; lock waits and deadlocks.
- Fulfilment, abandonment, `unnecessary_give_up`, cost, tokens and turns.
- Agreement of `fs_nonserializable` with the three DSG verdicts on model episodes.
- The aware-off probes against the first replies of the matching aware-off episodes (same request bytes): within-prompt variance per model.
- Extension blocks.

**Reporting rule.** Every number in the abstract, introduction, results and discussion that is not from a registered test carries an inline tag, *(exploratory)* or *(post hoc)*. No evidential verb and no absence claim attaches to such a number. No exploratory p-value appears in the main text. The paper states the total count of exploratory tests. Any analysis not listed here is post hoc.

## Other

### Declared confounds

- **Batch vs sync.** Haiku, Sonnet, Fable and Gemini run in batches; Qwen and GPT sync. Model inputs are byte-identical on both paths (tested), and the scheduler is simulated, so latency cannot change an interleaving. But the path is fixed per model, so path and model cannot be separated.
- **Temperature and thinking.** 0 is requested from every model. Haiku applies it. Sonnet and Fable reject it and run at the default. Qwen and GPT on OpenRouter are unverified. Gemini 4 Argon ignores sampling parameters (recorded as `ignored_by_provider`). Sonnet and Fable think by default; Haiku does not; Gemini thinks at its default level; GPT and Qwen use provider defaults. Within-prompt variance therefore differs by model. Model is a fixed factor.
- **Provider routing.** Qwen is pinned to Alibaba without fallbacks. GPT is not pinned (Study 1 had one Azure completion). Gemini is served by Google's Batch API under the Study 1 OpenRouter id. Three models are undated aliases.
- **Id-priority back-off in the reference policies.** The scripted back-off gives odd ranks a longer wait, so a0 almost always wins a retry. The validity result "every correct protocol finishes within 80 % of the cap" holds for that back-off. Under symmetric back-off, which two copies of one model may show, up to about 3 % of write-skew episodes end at the cap, and a capped verify-and-compensate agent can turn into a failure. This affects the cap's validation, not model behaviour. `cap_truncated` and sensitivities 1 and 2 address it.
- **Version visibility.** The `locks` config hides versions and `all_available` shows them, so `locks` vs `all_available` is confounded with version visibility.
- **Description salience and menu length.** The `acquire_lock` description is long. The CAS option is one property line. Lock share under `all_available` partly measures text salience. The tool menus are about 3,500 to 3,900 characters of JSON with locks, against about 1,300 to 1,700 without.
- **Call cap by config.** 24 vs 28. Sensitivity 1.
- **Gemini timing.** Gemini's `none`/`cas_available` blocks run in earlier batch waves than its `locks`/`all_available` blocks. Its config contrasts are confounded with time and serving version.
- **Affordance cues.** The primitives' texts imply concurrency ("If the record is already locked…", "otherwise 409"). They are equal across arms, but config vs `none` contrasts include them. "You are agent a1" implies an a0.
- **The version-mismatch 409 text.** Every `expected_version` mismatch gets one neutral text, in both arms and for both `version_conflict` and `invalid_version`: "409 Conflict: write to X rejected: expected_version does not match the record's current version." It names no agent and no version. We count `invalid_version` responses per arm. They are not contention signals.
- **Study 1 to Study 2 changes.** Lock semantics, tool texts, scheduler and cap all changed. No cross-study comparison of lock or failure rates.

### Deviations

A deviation is any departure from this document, and any change to a frozen file after the freeze, bug fixes included. Each is listed in an appendix table with:

- what changed and why;
- whether it was made before or after any Study 2 model result was seen;
- its effect;
- where feasible, the result under the registered plan.

**Bug fixes.** After a harness or scorer fix, the corrected scoring governs only if the bug fails a check in `tests5`, `validity5` or `dry_check5`, or Check 1 to 3 here. Otherwise the registered scoring governs. Both are reported. A bug that changed model inputs cannot be rescored: the affected cells are re-run in full (both arms), or reported as not tested.

"Seeing results" means opening any scored episode, any probe reply beyond `eligibility.json`, or `summary.md`. The sync runner prints each episode's outcome and label to its log. The author reads the logs only for failures, cost and progress. This exposure is declared here. The analysis code is frozen before spend and no lane is stopped or restarted by hand except as stated under Starting and stopping rules, so printed outcomes cannot steer any analyst choice.

### Freeze

sha256 of every frozen file, taken after all pre-registration edits and before any paid call. `src5/FREEZE.md` is the authoritative list for the harness; if the final freeze adds files, they appear there and are covered by its hash. The analysis files sit outside `src5` and are hashed at the same time.

| file | sha256 |
|---|---|
| `src5/FREEZE.md` | `e5834fb5b81565158493acda36b3fb5d32e2455a3504a86ffac646ba09681c6f` |
| `src5/agents5.py` | `ede3febcc06b692a61d25f65358086a359f44236d89517c2e10c5950cdcdd068` |
| `src5/budget5.py` | `9467988931db506f8fa834479a7e0631d8161582a995d5ae7d5b861486172a02` |
| `src5/design5.py` | `e2130ff0ac1be66774146fbf6d0d507f5f2dc7a300fef2aa7170e0ba697a51e7` |
| `src5/freeze5.py` | `8dd76b20d105bd62aec6eb0746354738a1d04cb2427fee70761e6154edc30f3b` |
| `src5/instances5.py` | `246da9d6f308c0a89b315e3b5b879cd19a5e9ccefc4a9c2508d297cec9573543` |
| `src5/model_agent5.py` | `93aea46dc1d55f1629e9119eebf9386a2970f9bf6edb9f454d36e27970b3a9d8` |
| `src5/plan5.py` | `277b944b70a111c0c99c7feb00ed1ad9004e9834a595ea5947ce50e789c0c720` |
| `src5/plan_study2.json` | `ae8e0a04b461fade24ab3d53c6500fbbae4f0ac42ddb303e588799d81f8df9d8` |
| `src5/plan_study2.txt` | `4db9c27f880d50a2d1864737b78cfae2d47f3111a3f299f4328c43554f83e466` |
| `src5/preflight5.py` | `b7671bbb1b66150bd65e5a35828bd45190363bae1a006b54ff62ccbb05c79e1c` |
| `src5/prices.json` | `9ab3087cd40283998b7bf82ae8409132a6d713d6a52e0789a2fb0f372e90b2f7` |
| `src5/providers5.py` | `cd50df65b3045ac3f86065ebe750a0200b19e004bf1d855e379bda5516ef2a05` |
| `src5/records5.py` | `e25b5c6fb853e887e4d3bac3c275f0ce8011a650c3bb5e28c8afdc392a4d391d` |
| `src5/rescore5.py` | `b697a09faa21b2ec9126dbe2e4001d849e6198ac718b9734a0c40b658c5f6243` |
| `src5/run5.py` | `608d2c7a0a115b89e4df31b95af8642d4fc3a781a5b1f59cb5c4709088e06f87` |
| `src5/scheduler5.py` | `450b94481f0b5297d4d6e5b7e73792539b85de66f599b0d9a92d6229e7f81ba6` |
| `src5/score5.py` | `5303df0db8f1c2a1e210e3137c94e4f8c3b9ab5af9721a9426237d6b8f6c8466` |
| `src5/study1_costs.json` | `f57c8e4c86b53ac7941a5c6e1be0cac14c0ac5fb684faae723da18748ae4998e` |
| `src5/summarize5.py` | `f8616658e44c569c97871173203400fa53107ce48d203a767ac9eef53d8e0734` |
| `src5/tasks5.py` | `9e13d74c82e555adaac0631dff453fa15213e6580c175a95f1203977e419cd6d` |
| `src5/tests5.py` | `1d98b119c7156c7d52d6cf68f7cebb3acd5da7668df1e305728357df7ed9252f` |
| `src5/validity5.py` | `ed269079ae5fa68caa7c0eb5e05f51acbdb7a65e499471e63326ee80c3095158` |
| `src5/world5.py` | `89dd9e70968c684588e275a11662277fbfad5c9c4a6b710b289a4130dbea4647` |
| `src5_batch/batch_driver.py` | `e6cda7786c58566c6b924b6a25f3bbf9057c677a145716e5556bebba08afdb38` |
| `src5_batch/cells_done.py` | `fd115e10f73aaccbf6f5ba820790f1b27059e5a7d468afd1bfea3b4bb5d8a707` |
| `src5_batch/fake_api.py` | `307e60e4997d9d10900f5cb168fcef7ea5459848d9ea253c6127d88e4b2c9bd0` |
| `src5_batch/fake_gemini.py` | `6651a67893563eba9ccf72da30dfda05a313b54d88ea412b6942ebfe98c6d83d` |
| `src5_batch/gemini_batch.py` | `c9deb55020798f27340a3a631782a829c4ff855a45ffab0447e4071b0308a6d3` |
| `src5_batch/gemini_preflight.py` | `841d996883ba1afc0ec03df96247e1c08ef8251192c4be367a0e037ea20ec1b6` |
| `src5_batch/gemini_replay.py` | `8c33186e72019513184a495b9d64d718a3d59bb5ed2635c2dcb737a38ba6b741` |
| `src5_batch/gemini_translate.py` | `2b8fddd92dbc7ca2ba75a8db263fc5adadb9f75bd351cb3c5510b67d536c482d` |
| `src5_batch/harness.py` | `1b4c5bc1f1311b96fbc7546e8e55475e8280250a002bcedd3510ea1dc595b5bb` |
| `src5_batch/prices_batch.json` | `480525b2bdf65bedc9b3496db7ee2c3032349d6f98d95964b645c87f1eaf100e` |
| `src5_batch/replay.py` | `4e0e617facc4d6e4e793ae1700c77e8c787d68a99d7b2795e33f2b30556c3d7e` |
| `src5_batch/run_rest.sh` | `1ee7a35c2d25e528b68315ae21bde9e1edc5fd22b84c11d9068336e895938a86` |
| `src5_batch/tests_batch.py` | `ace162f294ee663856f34d03a7f9e0df44fce2dbb70ff89c15dede6c5f273f76` |
| `src5_batch/tests_gemini.py` | `6d16506cc511f53e5e4b294cdcbcc3c816c11dcfbfaae827c387463d89135b07` |
| `src5_verify/dry_check5.py` | `7490386fa03274a30ea2ba08d91a32fffabec47e622ce6df081a3aaee3dd3bf5` |
| `src5_verify/mutate5.py` | `f03c51569f5afbc2f4d2855c6b8f30eb4a2dcd0428d908b81a28feb2ad1b7fb6` |
| `run_conc_study2.sh` | `76bcfa3f6e2c518ba0dafa50f702f68512490a9eee37f5c24bd0fe6443f9ead9` |
| `analysis5/analyze5.py` | `99dff56a75c925e48bff0f676bfc60f0ed52c4d3aaa1df88cb6f2c9b609a1357` |
| `analysis5/balance5.py` | `b387791ec7f530b12f18191b7bf333f78236c512e24591ee27b1cd4dfa4e8e87` |
| `analysis5/tests_analyze5.py` | `f2c5ffaf4716f81a7589b9c995c466d1af76b3527c1208d4bfcd46aac08ca4f1` |

Posted after filing, before any episode result is read: `eligibility.json` and its sha256, uploaded to the linked OSF project's storage (versioned and timestamped) and recorded in a registration update.

### Data and code availability

For review, an anonymized artifact holds the code and all run outputs (transcripts, ledgers, result CSVs), the analysis script with its dry-run outputs, the power simulations and `src5/FREEZE.md`. It links to a view-only copy of this registration. Public release follows the venue's decision. Code is under the MIT licence; instances, transcripts and results are under CC BY 4.0, subject to provider terms for model outputs.

### AI assistance

AI coding assistants helped write and test the harness and the analysis script, run the design reviews cited here (T1 to T4, V1, V2, V1b, V2b, T3b, T3c) and the power simulations, and draft this registration from the author's decisions. The author chose the research questions and the budget, approved the hypotheses and margins, reviewed this plan before filing, and runs the experiments.
