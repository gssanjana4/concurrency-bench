# OSF Preregistration (2026-10-31)

Fields follow the OSF Preregistration template. This text and the frozen code implement the same tests: `analyze4.confirmatory()` (src4/analyze4.py, "Confirmatory" in its docstring) computes exactly the tests below, and `run_full.sh` runs exactly the design below. If a discrepancy is found later, this text governs and the difference is reported as a deviation.

## Title

Do LLM agents coordinate on shared records? Optional concurrency control in multi-agent tool use

**Contributors.** Sanjana, independent researcher.

## Description

Several LLM agents, each in its own conversation, act on the same versioned records. A deterministic seeded scheduler interleaves their tool calls and forces a read-to-write gap. We vary the coordination options offered, whether the prompt mentions other agents, and the number of agents. We measure whether agents use the options and whether the committed outcome is serializable. Scoring is deterministic, from a ground-truth ledger and the server-side call log (no LLM judge). Prior work enforces concurrency control below the agent (e.g., CoAgent, arXiv 2606.15376); we measure what agents choose when protection is optional.

## Hypotheses

All hypotheses come from an exploratory pilot (see Existing data).

**Common definitions.**

- **Contended templates:** the seven non-control templates. The control template `budget_control` never enters any contended-rate numerator or denominator.
- **Unit:** the task instance (template, instance index), also called a cluster.
- **Families:** each confirmatory hypothesis is one Holm family of per-model one-sided tests, six if all models are tested, with familywise α = 0.05. We do not correct across hypotheses, which answer separate questions, and we report all results.
- **Episode-level labels:** every non-serializable episode has exactly one primary label (see Variables). Confirmatory tests use only `non_serializable` and the primary label.

**CONFIRMATORY**

- **H1 (no protection).**
  - Setting: config `none`, n = 2, aware off, contended templates, instances 0–3, seeds 0 and 1. That gives 28 clusters and 56 episodes per model.
  - Statistic: the proportion of episodes that are `non_serializable`.
  - Test: H0 p ≤ 0.50 vs p > 0.50.
  - Decision: supported if all six models reject after Holm.
- **H2 (locks unused).**
  - Setting: config `locks`, n = 2, aware off, contended templates, instances 0–3, seeds 0 and 1. That gives 28 clusters and 112 agents per model.
  - Statistic: the proportion of agents with at least one successful `acquire_lock`.
  - Test: H0 p ≥ 0.25 vs p < 0.25.
  - Decision: supported if at least 4 of 6 models reject after Holm.
- **H3 (prompt raises coordination).**
  - Setting: configs `locks` and `messages` pooled, n = 2, contended templates, instances 0–3, seeds 0 and 1, aware on and off (28 clusters).
  - Statistic: the agent-level rate of using the offered option, aware on minus aware off. The offered option is `lock` under `locks` and `message` under `messages`. Episodes pair exactly on (instance, seed, config).
  - Test: H0 difference ≤ 0.
  - Decision: we report which models reject after Holm and make no claim about the others.
- **H4a (conditional writes remove stale overwrites).**
  - Setting: n = 2, aware off, the single-record templates (`inventory_last_unit`, `inventory_still_valid`, `seat_same`, `ticket_same`), instances 0–3, seeds 0 and 1 (16 clusters).
  - Statistic: the rate of episodes whose primary label is `stale_overwrite`, under `none` minus under `cas_available`, paired on (instance, seed).
  - Test: H0 difference ≤ 0.
  - Decision: supported for each model that rejects after Holm.
  - Scope: this is an interface-level effect. Under `cas_available`, `claim` is a server-side test-and-set, so for seats and tickets the reduction need not reflect an agent choice. Agent-chosen `cas` is reported descriptively (exploratory).
- **H4b (conditional writes do not remove write skew).**
  - Setting: n = 2, aware off, the write-skew templates (`budget_write_skew`, `joint_account_write_skew`), instances 0–3, seeds 0 and 1 (8 clusters per model).
  - Each model is tested on two conditions, using the primary label `write_skew`:
    - (i) the `write_skew` rate under `cas_available` exceeds 0.50 (H0 p ≤ 0.50);
    - (ii) the drop from `none` to `cas_available` is below 0.25 (H0 drop ≥ 0.25), paired on (instance, seed).
  - Combining: the per-model p-value is the larger of the two (intersection-union), and Holm is applied across models.
  - Decision: supported for each model that rejects.
  - Rationale for the margin of 0.25:
    - The pilot write-skew rate was at ceiling under `cas_available`.
    - With 8 clusters a formal equivalence test has little power. The registered claim is that write skew stays common under per-record protection, not that it is unchanged.
    - 0.25 is half the H1 threshold.
    - A tighter margin cannot be tested with 8 clusters. With no drop in 7 clusters and a drop of 0.5 in one, the unadjusted one-sided p for (ii) is about 0.01 at margin 0.25 but about 0.27 at 0.10.
- **H6 (more agents).**
  - Setting: config `cas_available`, aware off, seed 0, the 14 contended instances (7 templates × instances 0 and 1), each run at n = 2, 4 and 8. The n = 2 episodes come from phase 1.
  - Statistic: the OLS slope of `non_serializable` (0/1) on log2(n). Every cluster has the same three design points, so the pooled slope equals the mean of per-cluster slopes.
  - Test: H0 slope ≤ 0.
  - Decision: supported for each model that rejects after Holm.
  - Rationale: we chose `cas_available` because the pilot rate under `none` was near ceiling at n = 2. With 14 clusters, a null result is not evidence of no trend.

**PRE-SPECIFIED DESCRIPTIVE (no test, no Holm family)**

- **H5 (partial actions).**
  - Denominator: agents with a multi-record write intent (only `transfer_shared_source`) under `cas_available`, `cas_required` or `locks`, at n = 2 and both aware levels, that had a write (`update_record` or `claim`) rejected with 409 `version_conflict` or 423 `locked_by_other` on a record their intent writes. A refused `acquire_lock` is not a rejected write.
  - Numerator: those agents that committed an action, ended, and did not fulfil their intent.
  - Reporting: counts and 95% Wilson intervals per model (read from the transcripts by `analyze4.h5_agents`).
  - Pre-specified outcome: at least one such agent, confirmed by transcript audit, in at least 3 of 6 models.
  - We make no claim about population rates.

## Design plan

**Study type.** Experiment on software agents. No human participants.

**Blinding.** Not applicable (automated scoring). The harness, scorer, analysis, instance file, price table and run scripts are frozen before any confirmatory episode. The sha256 of every file is in src4/FREEZE.md and in the Freeze section below.

**Design.** `run_full.sh` runs three phases under one total cost cap. Within each phase, aware off and aware on are run together (the `--aware both` grid axis), not in separate stages.

| phase | n agents | configs | aware | templates × instances | seeds | episodes per model | total (6 models) |
|---|---|---|---|---|---|---|---|
| 1 | 2 | `none`, `reread_only`, `cas_available`, `cas_required`, `locks`, `messages` | off + on | 8 × 4 (instances 0–3) | 0, 1 | 768 | 4,608 |
| 2 | 4 | `none`, `cas_available`, `locks` | off + on | 8 × 2 (instances 0, 1) | 0 | 96 | 576 |
| 3 | 8 | `none`, `cas_available`, `locks` | off + on | 8 × 2 (instances 0, 1) | 0 | 96 | 576 |

Totals are 5,760 episodes, 960 per model. In phases 2–3 the 16 instances per config and aware level are 14 contended (7 templates × 2) plus 2 `budget_control` controls. The controls are run and reported but never enter contended-rate denominators.

**Models.** Requested ids, exactly as in `run_full.sh`, in run order:

1. `openrouter:qwen/qwen3.6-27b-20260422` (Qwen3.6-27B, open weight)
2. `claude-haiku-4-5-20251001` (Claude Haiku 4.5)
3. `openrouter:openai/gpt-5.5-20260423` (GPT-5.5)
4. `openrouter:google/gemini-4-argon-20261013` (Gemini 4 Argon)
5. `claude-sonnet-5` (Claude Sonnet 5)
6. `claude-fable-5` (Claude Fable 5)

`claude-sonnet-5` and `claude-fable-5` are undated aliases that resolve server-side. Every completion records the served model id (`model_served`), and the paper reports the served ids. The confirmatory output lists them per requested id (`served_ids`). No reasoning or thinking parameter is sent, so each model runs at its provider's default reasoning setting. On OpenRouter, reasoning tokens count against max_tokens. Prices: `prices.json` keys match an exact id or that id plus a `-YYYYMMDD` suffix, so the `claude-fable-5` entry cannot price a `claude-fable-5.1` id (tested).

**Configs.** `none` (blind writes, silent last-writer-wins), `reread_only`, `cas_available`, `cas_required`, `locks` and `messages`, as defined in src4/README.md.

**Aware prompt.** When on, one sentence is appended to the system prompt: "Other agents may be reading and writing the same records at the same time as you."

**Templates (8).**

- Conflict: `inventory_last_unit`, `seat_same`, `ticket_same`, `transfer_shared_source`.
- Still-valid: `inventory_still_valid`.
- Write skew: `budget_write_skew`, `joint_account_write_skew`.
- Control: `budget_control`.

**Instances.** 4 parameterized instances per template. Instance i uses instruction paraphrase i mod 2, so each paraphrase has 2 instances. Paraphrase is not crossed with instance. All instances are disjoint from the pilot (tested). Phases 2–3 use instances 0 and 1, one per paraphrase.

**Fixed settings** (run4.py defaults; `run_full.sh` does not override them):

- read-to-write gap: 2 rounds;
- start jitter: 0;
- turn cap: 12 executed tool calls per agent (hard cap of 13 completions per agent);
- temperature: 0 requested;
- max_tokens: 4096 per completion;
- locks: lock expiry on, max lease 50 rounds;
- stall_rounds: 6;
- max_rounds: 2000;
- Anthropic prompt caching: on.

**Randomization.** The interleaving order of each round is drawn from `Random(seed)`. Instance parameters come from `random.Random("src4-full-v1|<template>|<i>")`. Any draw that coincides with the pilot task or an earlier instance is redrawn with a suffixed key, which happens deterministically. The instances are written to `instances_full.json` by `python3 instances4.py --write instances_full.json` (K = 4; n = 2, 4, 8) and hashed in the Freeze section.

## Sampling plan

**Existing data.** The only existing data is the pilot: 192 episodes covering Haiku 4.5 and Qwen3.6-27B, n = 2, aware off, all six configs, one instance per template, seeds 0 and 1. No confirmatory data exist. Pilot data are excluded from every confirmatory analysis (instance id `pilot`).

**Explanation of existing data.** The pilot was exploratory. It was used to fix the harness and to form the hypotheses.

- Without protection, 13–14 of 14 contended episodes per model per config were non-serializable.
- With conditional writes offered, agents used them and single-record conflicts disappeared, but write-skew tasks stayed non-serializable.
- With locks offered, about 2–3 of 28 episodes contained any lock use.
- The message channel was used in 1 of 28.
- One agent received a 409 on a transfer's debit and still credited the destination.

With one instance per template, none of these is an estimate.

**Data collection.** Episodes are run with src4/run_full.sh (which calls run4.py). Every transcript, ledger and spend log is saved. Preflight calls are not data.

**Sample size.** Set by budget; no power analysis. Clusters per model:

| hypothesis | clusters per model |
|---|---|
| H1, H2, H3 | 28 each |
| H4a | 16 |
| H4b | 8 |
| H6 | 14 |

**Stopping rule.** The design is fixed, with no optional stopping on results.

- **Budget.** The total budget is $350; the pilot spent $1.60. `run_full.sh` enforces one hard cap of $330 over everything it spends (preflight plus all phases).
- **Pre-run estimates** (`plan_full.py`, from pilot cost per episode) are $146.61 for phase 1, $40.32 for phase 2 and $88.70 for phase 3, $275.63 in total.
- **Run order.** Phases run in order 1, 2, 3. Within each phase the models run in the order listed above (Qwen, Haiku 4.5, GPT-5.5, Gemini, Sonnet 5, Fable 5 last). Each model finishes the phase before the next starts.
- **Budget gate.** Before each phase, the run stops if the budget left is below that phase's estimate for its remaining episodes. During a phase, run4.py stops before any episode that could push spend past the cap.
- **Provider failures.** `run_full.sh` makes up to 5 run4 attempts per (phase, model), and the run is resumable. An episode that still fails is recorded in `failures.jsonl`.
- **Untested cells.** Cells not reached are not run. If the cap truncates the run, every registered cell not run is reported as "not tested", never as a null result. A hypothesis that needs any unrun episode for a model is "not tested" for that model. It then:
  - counts as not supporting in "k of 6" criteria and in H1's "all six";
  - leaves the Holm family, which shrinks to the models tested;
  - is reported descriptively only, from its partial cells.

## Variables

**Manipulated.** Model, config, aware prompt, number of agents.

**Measured.** By score4.py at the frozen hash, with definitions as in src4/README.md.

- **Episode level.** `non_serializable` means no serial order of the committed agents' intents reproduces the final store. Each non-serializable episode gets exactly one primary label (`primary_label`). The precedence is `stale_overwrite` > `partial_action` > `write_skew` (first match wins):
  - `stale_overwrite`: some committed write's basis is older than the version it overwrote.
  - `partial_action`: no stale write, but some committed agent did not fulfil its intent.
  - `write_skew`: neither of the above.

  `stale_overwrite` is the primary label used by H4a. The raw number of stale writes per episode (`n_stale_writes`, which counts stale writes whatever the label) is exploratory only. Also measured: `graph_cycle`, `invariant_violation`, `stall`.
- **Agent level.**
  - Coordination choices: `reread`, `cas`, `lock`, `message`, `none`, counted from successful calls only.
  - Outcomes: `fulfilled`, `unnecessary_give_up`, `abandoned`, `lock_leak`.
  - Resources: turns, tokens and cost.
- **Scorer verification.** An independent verifier ran mutation testing on the frozen code: 97 of 99 mutants were killed. Neither survivor can change any reported number:
  - S18 lets `reread` count failed `get_record` calls. It is equivalent because a `get_record` that fails never logs a record id.
  - S39 removes a memo and affects performance only.

## Analysis plan

**Confirmatory statistical model** (`analyze4.confirmatory()`, written to `confirmatory.json` and `confirmatory.md`).

- **Clusters.** A cluster enters a test only if every episode the hypothesis needs for it is present. Within a cluster, seeds, agents and paired conditions are aggregated first (sum of numerators over sum of denominators per condition), giving one cluster value. The estimate is the mean of cluster values.
- **Bootstrap.** Cluster bootstrap over task instances, with 10,000 resamples of clusters with replacement. The RNG is `random.Random("20261031|<hypothesis>|<model>")`, with a suffix `|i` or `|ii` for the two parts of H4b. Each resample keeps all of an instance's seeds, agents and paired conditions.
- **p-values.** The one-sided p-value for H0: θ ≤ θ0 is (1 + #{θ* ≤ θ0}) / (B + 1), and symmetrically (1 + #{θ* ≥ θ0}) / (B + 1) for H0: θ ≥ θ0. We report 95% percentile intervals.
- **Degenerate case.** When all cluster values are equal, the bootstrap is degenerate. This includes every observed rate of 0 or 1. In that case the decision p-value is the exact one-sided sign test on cluster values against θ0 (ties dropped). The sign test is reported for every test.

**Inference criteria.** One-sided α = 0.05, with Holm across the tested models within each hypothesis. The decision rules are stated under each hypothesis.

**Descriptive tables (EXPLORATORY).** analyze4.py also writes `numbers.json` and `tables.md`, labelled EXPLORATORY:

- per-cell rates with 95% Wilson intervals;
- paired sign-flip permutation comparisons (aware on vs off; each config vs `none`) with Holm within (comparison, metric, n).

The "Wilson interval on a mean of instance rates" (sample size = number of instances) is an approximation used only for these descriptive tables. Neither the tables nor the permutation tests support any confirmatory claim.

**Data exclusion.**

- **Provider failures** (no completion) are retried as described under Stopping rule. An episode that never completes is recorded as missing, not replaced and not scored.
- **Truncation, invalid tool calls, refusals, turn-cap endings** are model behavior: kept, scored, and counted per cell. Sensitivity: all confirmatory tests and H5 are rerun with episodes that have a truncated agent treated as missing (`sensitivity_exclude_truncated`).
- **Served id differs from requested id:** kept, flagged, and reported (`served_ids`).
- **Dry-run rows and pilot rows** are dropped.

**Missing data.** Each test uses complete clusters only.

- A cluster whose missing episodes are all unrecovered provider failures (or, in the sensitivity analysis, truncated episodes) is dropped from that test, and the dropped clusters are listed.
- A registered episode that was never run (e.g. budget cap) makes the hypothesis "not tested" for that model (see Stopping rule).

**Temperature.** We request 0.

- Anthropic: if the API rejects the parameter, the harness retries without it and logs `temperature_effective` as null for that model.
- OpenRouter: it does not echo sampling parameters, so `temperature_effective` is logged as `unverified`.

Models without an effective temperature of 0 run at provider defaults, one sample per cell, and the paper says so. Seeds control scheduling only; outputs may vary even at temperature 0.

**Deviations.** A deviation is any departure from this document and any code change after the freeze, including bug fixes. Examples are a model id or setting, config, instance, prompt text, schedule parameter, exclusion rule or analysis. Each deviation is listed in an appendix table with:

- its reason;
- whether it was made before or after seeing confirmatory data;
- its effect;
- where feasible, the result under the registered plan.

If a harness or scorer bug is found, we fix it, rescore all episodes and report both versions.

**Exploratory analyses.** These are labeled as exploratory and support no confirmatory claims.

- All of `numbers.json` / `tables.md`: Wilson-interval cell rates and permutation comparisons.
- Per-template and per-paraphrase breakdowns, including whether agent-chosen `cas` drives H4a on inventory templates.
- `n_stale_writes`; `unnecessary_give_up`, `abandoned`; cost, tokens and turns.
- Qualitative coding of message content. Codes (a message may get more than one): announces intent or claims a record; reports a value read or written; asks another agent to wait or yield; agrees or acknowledges; other. The author codes every message from its text alone, with model and config hidden. If more than 300 messages are sent, a random 300 (seed 20261031) are coded. Reported as counts only.
- Configs `reread_only` and `cas_required`; aware-prompt effect on `cas` and `reread`.
- `graph_cycle` vs `non_serializable` agreement; `invariant_violation`, `lock_leak`, `stall`.
- n = 4/8 cells not used by H6 (`none`, `locks`, aware on).

Any analysis not listed here is labeled post hoc.

## Freeze

sha256 of every frozen file in src4, taken after all pre-registration edits and before any confirmatory episode (identical to src4/FREEZE.md):

| file | sha256 |
|---|---|
| `agents4.py` | `ec3e581601ce51376d5f8b9954377f1940d0e1b2298b1ee8d66a739a4b2f7b37` |
| `analyze4.py` | `ab27a14b21ca2181fe186fad36b0faef0ff1cdd85a6a8a852fc1b52f5c5eda2c` |
| `instances4.py` | `ae4447e43b08aba01a6061189e79ee8835acdb566e57859d6cbe410abd2226a9` |
| `model_agent4.py` | `314f4f7b5de2ba368b38e286b767a2508f935273565a64f2009ec4545b6a7202` |
| `plan_full.py` | `9087fc5a35fdde87ecc778259819a95df14c43cbc6fc515c6685b056008fd28b` |
| `preflight.py` | `e8dac1143e87b954ccddae5528729e41a427b21d447f2d33a1e0db55498f3cbe` |
| `providers.py` | `05289d094785882f0af334065eaa0d44b29bfafd307690abc5379c886a17a5b9` |
| `records.py` | `eb07d4469e7b14c6d6fd8f3adf4d212945f08727a379c110ce35db5f54c1ccaf` |
| `run4.py` | `e7f1a9e9fbb1b55ab3de85b0924ec4aac392734c1292ec87f7ac3a23e055100b` |
| `scheduler.py` | `6cd9bd4bb93d504b5d6f6eb7effbebba35ad515a8104f4493c2d231cd7d19a28` |
| `score4.py` | `a8949af9a4d4f98454d4967a381c832be9f62960a10664bf83be1c0402d066db` |
| `tasks4.py` | `a73d485a00b3a768b7a74ea77354fb64d57e0819c6fc16b52477be82232eb596` |
| `tests4.py` | `ece63beae3d1d283e88bad5ce7340e38f7e7f7b7bbd63fe0fc49d5e47c2285e7` |
| `tests_full4.py` | `1548dc16c3cc6dad9d6c343f5c7fd1dfc9f3ed2e4b2518333e6a412298b28ab0` |
| `tests_model4.py` | `402fbceab8c56fc360155b616c64eac3d458f51a6b8f07853af756b9ce8452ca` |
| `world4.py` | `975c1323de820fa83e3cd9b841ca9ca1a3a1f9437ad66cebb3b47e76e40c4557` |
| `instances_full.json` | `70943a64c88307f5575c990aa7549c10b92a342e324ac1c2abff76bff531d155` |
| `prices.json` | `9ab3087cd40283998b7bf82ae8409132a6d713d6a52e0789a2fb0f372e90b2f7` |
| `run_full.sh` | `dfa77edd276ca7e080479dacc6fb2477d73aec0908380ff79422d1abcedb1e45` |
| `run_pilot.sh` | `e937c941f3dfb70ae3edacb075e1ea344d46c9903a421926c35405d3f1186859` |

## Other

**Data and code availability.** For review, we provide an anonymized artifact containing the code, instance files, transcripts, ledgers, result CSVs, analyze4.py and FREEZE.md, together with an anonymized view-only link to this registration. Public release follows the decision, under the MIT licence (code) and CC BY 4.0 (instances, transcripts and results), subject to provider terms for model outputs.

**AI assistance.** AI coding assistants helped write and test the harness and analysis code, search the literature, and draft this pre-registration from the author's decisions. The author chose the research question and scope, set the budget, reviewed and approved the design, hypotheses and analysis plan, and runs the experiments.
