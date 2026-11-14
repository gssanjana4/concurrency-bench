# Code and data: "Do LLM Agents Coordinate on Shared Records?" (Study 1 and Study 2)

Sanjana Gopnal Swamy (independent researcher). Artifact version v2. Code: MIT licence (`LICENSE`). Data: CC BY 4.0 (`data/LICENSE.txt`), model outputs subject to the providers' terms; intended for research use.

Pre-registrations: Study 1 https://osf.io/a5vec (registered 2026-10-31); Study 2 https://osf.io/zj3an (registered 2026-11-09, `date_registered` 2026-11-09T18:35:24Z). Both texts are in `preregistration/`. Archived copy of this repository, with the paper source and the two PDFs in the same record: https://doi.org/10.5281/zenodo.24226165. Repository: https://github.com/gssanjana4/concurrency-bench.

## What this is

Two pre-registered studies of whether LLM agents, each in its own conversation, coordinate when they act on the same versioned records through tool calls. A seeded scheduler interleaves their calls; the coordination primitives offered (none, conditional writes, fenced locks, both) and the prompt's mention of other agents are varied; scoring is deterministic from the ledger and the server call log (no LLM judge). Study 1 is the first run (frozen harness `src4/`). Four hard reviews of it found harness design flaws (`CHANGES_V2.md`), so Study 2 re-ran a corrected harness (`src5/`) with matched uncontended controls, fenced locks and first-reply probes, under a second registration. Study 1 is reported with its deviations; Study 2 carries the registered confirmatory tests of the corrected design.

## Layout

| path | what it is |
|---|---|
| `src4/` | Study 1 frozen harness and its confirmatory analysis (`analyze4.py`); `FREEZE.md` lists the 20 frozen sha256 |
| `src4_batch/` | Study 1 batch drivers (Sonnet 5, Fable 5, Gemini 4 Argon episodes) and their offline tests (not frozen) |
| `src_sql/` | the exploratory SQL slice of Study 1 (post hoc, not pre-registered) |
| `orchestrators_as_run/` | the orchestrator scripts exactly as run on the author's Mac for Study 1, with their own `SHA256SUMS` and README |
| `paper/latex/` | the Study 1 number pipeline: every script that produces a Study 1 number, its tests, `deviations.csv`, `build.sh`; the paper source and PDF are not in this artifact; they are in the same archived record (`paper-source-v1.zip` and the two PDFs) |
| `paper/` | (no compiled paper in this build) |
| `paper/audit/` | the pre-specified H5 transcript audit of Study 1 (performed by an AI agent) and the scoring spot-checks |
| `preregistration/` | the two registration texts: `PREREGISTRATION.md` (Study 1) and `PREREGISTRATION_STUDY2.md` (Study 2); `paper/PREREGISTRATION.md` is the copy the pipeline reads |
| `src5/`, `src5_batch/`, `src5_verify/`, `run_conc_study2.sh` | Study 2 frozen harness, batch layer, verification tools and runner: `src5/FREEZE.md` lists all 38 frozen sha256 (`src5/*.py`, `*.json`, `src5_batch/*.py`, `*.json`, `*.sh`, `src5_verify/dry_check5.py`, `run_conc_study2.sh`); `src5_verify/mutate5.py` and `mut5.json` (mutation testing) are not frozen |
| `run_conc_s2go.sh`, `run_conc_s2dry.sh`, `run_conc_elig.sh` | **non-frozen wrappers**, as run on the Mac: the paid run with the balance log around it, the no-cost rehearsal with the paid interpreter, and the eligibility step. Not in `FREEZE.md`; their hashes are in `SHA256SUMS` |
| `analysis5/` | Study 2 analysis: `analyze5.py` (frozen, registered: eligibility, the confirmatory tests, checks, H4b, budget report, sensitivities 1 to 9), `descriptives5.py` (pre-specified descriptive tables and figures; no test), `balance5.py`, `tests_analyze5.py`, `PREREG_GAPS.md`, `power_sims/` (registered power simulations), `testdata/`, `out/` (the registered dry-run outputs), `out_study2/` (`eligibility.json`, `results.json`, `numbers.tex` of the registered run) |
| `CHANGES_V2.md` | every pre-spend review blocker, its fix and the test that proves it (Rounds 1 to 5) |
| `STUDY2_RUN_LOG.md` | the paid-run log: gates, deviations, cost, the eligibility step, the final counts and the post-run checks |
| `osf_registration_records.md` | both OSF registrations as recorded at the time: identifier, `date_registered`, embargo end, sha256 and location of the registered text, the eligibility file's upload time (checkable without lifting the embargo) |
| `data/` | Study 2 data (`data/results5/study2/`) and the Study 1 data directories (`data/results4/full/`, `data/results_sql/`): see `data/README.md` |
| `reference_outputs/study1_analysis/` | the author's Study 1 analysis outputs, to compare against a rerun |
| `FREEZE_OVERRIDE.json` | the documented FREEZE override for redacted frozen files (empty in the public build; see below) |
| `SHA256SUMS`, `BUILD_INFO.json` | sha256 of every shipped file (`sha256sum -c SHA256SUMS`, on macOS `shasum -a 256 -c SHA256SUMS`); how and when this artifact was built and which checks passed |
| `tools/` | `make_artifact_v2.py` (built this artifact; its docstring lists every inclusion, exclusion and edit), `make_anon_artifact.py` (identity rules of the review build), `compare_json.py` |
| `.study2_registered` | the marker written on the Mac after the OSF registration was confirmed; `run_conc_s2go.sh` and `run_conc_elig.sh` refuse to run without it |

## Frozen and registered hashes

`src4/FREEZE.md`: 20/20 files verify in this copy. `src5/FREEZE.md`: 38/38 files verify. `python3 -I src5/freeze5.py --check` inside this copy printed: `FREEZE OK (38 files)`.

Registered sha256 (Study 2 registration, "Freeze"; `STUDY2_RUN_LOG.md`), each checked against the copy at build time:

| file | sha256 | in this copy |
|---|---|---|
| `src5/FREEZE.md` | `e5834fb5b81565158493acda36b3fb5d32e2455a3504a86ffac646ba09681c6f` | verifies |
| `run_conc_study2.sh` | `76bcfa3f6e2c518ba0dafa50f702f68512490a9eee37f5c24bd0fe6443f9ead9` | verifies |
| `analysis5/analyze5.py` | `99dff56a75c925e48bff0f676bfc60f0ed52c4d3aaa1df88cb6f2c9b609a1357` | verifies |
| `analysis5/balance5.py` | `b387791ec7f530b12f18191b7bf333f78236c512e24591ee27b1cd4dfa4e8e87` | verifies |
| `analysis5/tests_analyze5.py` | `f2c5ffaf4716f81a7589b9c995c466d1af76b3527c1208d4bfcd46aac08ca4f1` | verifies |
| `preregistration/PREREGISTRATION_STUDY2.md` | `8193e9602f0c1257e1ec69d890f15ab4e63c084fa0da77d1eae416c16fd23ee5` | verifies |
| `analysis5/out_study2/eligibility.json` | `f4ad4f072fffc0e3a703ab708d61b5371e72f5481cb6f13a639f1598b228341d` | verifies |
| `analysis5/out_study2/results.json` | `0c11cec935fee524c55874229c43955f1b9b5f88eacf1106ced4d7fc2c09c6e7` | verifies |
| `analysis5/out_study2/numbers.tex` | `a70c6f84b9c928604dcca18c1584a44cce22eb38bb08e49e89d7e01509d07daa` | verifies |

The eligibility file's sha256 (`f4ad4f072fffc0e3a703ab708d61b5371e72f5481cb6f13a639f1598b228341d`) was posted to the OSF project before any episode result was opened (`STUDY2_RUN_LOG.md`, "ELIGIBILITY STEP"); `analyze5.py analyze` refuses to run unless the eligibility file it is given has that hash.

## Reproduce Study 2 from the shipped transcripts

Requirements: Python 3.10 or later (the runs used 3.13); the harness and the registered analysis are standard library only. `matplotlib` for `descriptives5.py` and the Study 1 figures; the `anthropic` SDK (2.3.0 was used) for the batch path and its tests; `numpy` and `scipy` only for `analysis5/power_sims/`. Run from the artifact root.

```
# 1. eligibility from the probe transcripts only (must print sha256 f4ad4f072fffc0e3a703ab708d61b5371e72f5481cb6f13a639f1598b228341d)
python3 -I analysis5/analyze5.py eligibility --base data/results5/study2 --out analysis5/out_rerun

# 2. the registered analysis (54 tests, about 30 s); refuses unless --eligibility has the posted sha256
python3 -I analysis5/analyze5.py analyze --base data/results5/study2 \
    --eligibility analysis5/out_study2/eligibility.json \
    --eligibility-sha256 f4ad4f072fffc0e3a703ab708d61b5371e72f5481cb6f13a639f1598b228341d \
    --out analysis5/out_rerun

# 3. compare with the shipped outputs: numbers.tex is byte-identical; results.json is equal up to float
#    summation noise (about 1e-13, platform dependent: the registered run was on macOS)
cmp analysis5/out_rerun/numbers.tex analysis5/out_study2/numbers.tex
python3 -I tools/compare_json.py analysis5/out_rerun/results.json analysis5/out_study2/results.json

# 4. pre-specified descriptive tables and figures (matplotlib), no test; deterministic
python3 -I analysis5/descriptives5.py --base data/results5/study2 --results analysis5/out_study2/results.json \
    --numbers analysis5/out_study2/numbers.tex --plan src5/plan_study2.json --out study2_out --facts study2_out/facts.md

# 5. the 24-call sensitivity re-score from the logged ledgers (also inside analyze5, sensitivity 1; no -I:
#    rescore5 imports its siblings from the script directory)
python3 src5/rescore5.py --cap 24 --out cap24.csv data/results5/study2/n2-*/transcripts
```

`analysis5/out_study2/` is the author's run of exactly these commands on the Mac (see the hash table). Scores and ledgers are reproducible from the transcripts with the frozen scorer; the model outputs are not: re-running the harness is a new data collection.

### Tests

```
cd src5 && python3 -m unittest tests5 && cd ..                       # 91 harness tests, about 6 s (one of them needs the anthropic SDK importable)
cd src5_batch && python3 -m unittest tests_batch tests_gemini && cd ..   # 59 batch-path tests incl. the equivalence gate; needs the anthropic SDK; ~17 min
python3 src5/validity5.py --out validity_rerun                           # reference-policy validity table (372 rows, 0 required failures; ~3 min)
bash run_conc_study2.sh --dry-run --base results5/study2_dry             # whole grid with fake models, no keys, no money (needs the anthropic SDK importable); then dry_check5
A5_DRY_BASE=results5/study2_dry PYTHONDONTWRITEBYTECODE=1 python3 analysis5/tests_analyze5.py   # 46 analysis tests (end to end on that dry run; writes analysis5/out/)
python3 src5_verify/mutate5.py                                           # mutation testing (124 mutants; SRC5_DIR=$PWD/src5)
```

`tests_analyze5.py` needs a dry run of the final harness (`A5_DRY_BASE`); it rewrites `analysis5/out/`, whose shipped content is the registered dry-run output (hashes in `SHA256SUMS`). `tests_batch`/`tests_gemini` and the mutation run take long; the Study 2 registration lists the counts they produced.

## Re-run the harness

**Dry run (no keys, no money; about 10 minutes).** `bash run_conc_study2.sh --dry-run --base results5/study2_dry` runs the freeze check, the validity gate, fake preflights, the whole registered grid with fake models that lock and message, the channel rehearsal and `src5_verify/dry_check5.py` (5,160 transcripts, 1,180 matched pairs; it needs the `anthropic` SDK importable even though nothing is sent). `run_conc_s2dry.sh` is the wrapper that did this on the Mac with the paid interpreter (`.venv/bin/python`).

**Paid run.** Create `.env` with `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, then `bash run_conc_study2.sh` (or `bash run_conc_s2go.sh`, which also logs the OpenRouter key balance before and after and refuses to start without `.study2_registered`). The script refuses to start if any frozen file differs from `src5/FREEZE.md` or the validity gate fails; it spends at most the per-provider caps in its header (Anthropic $19, OpenRouter $28, Gemini $22, total $69; the registered run spent $46.40). Haiku, Sonnet and Fable run through the Anthropic Message Batches API, Gemini through the Google Batch API, Qwen and GPT-5.5 sync through OpenRouter (Qwen pinned to the Alibaba host). Model versions and prices move: a new run is a new study, not a reproduction of this one. The eligibility step between the probe block and the analysis is `run_conc_elig.sh`.

## Study 1

The Study 1 data are in `data/results4/full/` and `data/results_sql/`. The Study 1 pipeline runs as on the build machine, with the data location given explicitly:

```
export RESULTS4=$PWD/data/results4/full RESULTS_SQL=$PWD/data/results_sql
cd paper/latex
python3 run_analysis.py --out ../analysis            # verifies src4/FREEZE.md, runs the frozen src4/analyze4.py (confirmatory)
python3 explore4.py --analysis ../analysis           # EXPLORATORY analyses from saved CSVs and transcripts
python3 rollback_sensitivity.py --analysis ../analysis   # POST HOC rollback rescoring + H5 audit counts
python3 posthoc_review.py --analysis ../analysis     # POST HOC review analyses (saved data only)
python3 reference_policies.py --analysis ../analysis # POST HOC scripted reference agents (no model calls)
cd ../../src4 && python3 -m unittest tests4 tests_full4 tests_model4   # harness tests
```

`confirmatory.json` should equal `reference_outputs/study1_analysis/confirmatory.json` except for the input paths. `make_numbers4.py --check` and `paper/latex/tests/` also need the paper source (`main.tex`, `facts/`), which is in `paper-source-v1.zip` of the archived record. Study 1 harness tests in `src4_batch/` import the frozen harness through `src4_batch/frozen.py`, whose own FREEZE gate does not read `FREEZE_OVERRIDE.json`; they pass on this unredacted copy.

## FREEZE override

`FREEZE_OVERRIDE.json` is the documented mechanism of the review build: a frozen file that had to be redacted for anonymity is listed with its FREEZE.md hash (equal to the sha256 of the original, checked when the artifact was built) and the sha256 of the redacted copy; `paper/latex/pipeline_common.py` accepts exactly those bytes and nothing else. In this public build nothing is redacted and the list is empty: every frozen file matches its FREEZE.md hash.

## Edits made by the builder

- data/results5/study2/openrouter_balance.jsonl: the `raw` provider response (account metadata of the shared OpenRouter key) was replaced by a note; the fields analyze5 reads are unchanged.
- Local filesystem paths of the author's machine (log and traceback lines) were replaced by the make_anon_artifact.py path tokens in: `data/results4/full/run.log`, `data/results4/full/run_batch.log`, `data/results4/full/run_everything_after.log`, `data/results5/study2/lane_anthropic.log`; 26 line(s) in all, listed in BUILD_INFO.json.

Excluded: `batch_state/` and `held_for_pair/` directories, `__pycache__`, `.env`, the dry-run rehearsal transcripts, the build logs, the paper source and PDF, and the AI pre-submission and pre-spend review documents (R1 to R3, T1 to T8, T3b, T3c, T7b, T8b, T8c, V1, V1b, V2 and V2b: AI-generated, in-pipeline checks, not peer review).

## AI use

This work was AI-assisted: Claude models (Anthropic, which also provides three of the six evaluated models) assisted under the author's direction and review. The author chose the research question, scope and budget, reviewed and approved the designs, hypotheses and analysis plans, filed both registrations under her own account and ran the experiments on her machine with her API credit (the Study 2 run was started by a queued job on her Mac after the registration was filed; `STUDY2_RUN_LOG.md`). The paper's Acknowledgments carry its AI-use statement.

## Cite

```
Gopnal Swamy, Sanjana. Do LLM Agents Coordinate on Shared Records? Two Pre-registered Studies of Optional Protection on a Record API. 2026. Preprint. Code and data: https://doi.org/10.5281/zenodo.24226165 and https://github.com/gssanjana4/concurrency-bench
```

```bibtex
@misc{gopnalswamy2026coordinate,
  author       = {Gopnal Swamy, Sanjana},
  title        = {Do LLM Agents Coordinate on Shared Records? Two Pre-registered Studies of Optional Protection on a Record API},
  year         = {2026},
  howpublished = {Preprint},
  note         = {Code and data: https://doi.org/10.5281/zenodo.24226165 and https://github.com/gssanjana4/concurrency-bench; pre-registrations https://osf.io/a5vec and https://osf.io/zj3an}
}
```

Built 2026-11-14 (UTC) by `tools/make_artifact_v2.py` (public mode); 11,272 files. Study 2 transcripts: probe-anthropic 896, probe-gemini 896, probe-openrouter 896, n2-anthropic 992, n2-gemini 672, n2-openrouter 640. Wrappers included: run_conc_s2go.sh, run_conc_s2dry.sh, run_conc_elig.sh. Eight files were edited after the build, on 2026-11-14, and their lines in `SHA256SUMS` were refreshed: `README.md` (archive DOI, citation, a test note, the AI-use section), `paper/latex/deviations.csv` (the last sentence of the H5 audit row removed) and, to remove notes on the paper's writing workflow, which is not part of this artifact, `CHANGES_V2.md`, `paper/latex/README.md`, `paper/latex/build.sh`, `paper/latex/tests/test_make_numbers4.py`, `tools/make_artifact_v2.py` and `tools/make_anon_artifact.py`.
