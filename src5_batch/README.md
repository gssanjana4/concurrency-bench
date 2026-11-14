# src5_batch: batch execution for Study 2 (src5)

This is a copy of `src4_batch` (Study 1, unchanged) retargeted at the Study 2 harness `src5`. The design is the
one documented in `src4_batch/README.md`:
- the HTTP seam under the real `anthropic` SDK, or `urllib.urlopen` for Gemini;
- lockstep replay of the harness episode code;
- state on disk, crash and restart recovery;
- retries, then a provider failure recorded exactly as on the sync path.

That README stays the reference for the mechanism. Only the differences are listed here.

| file | change for Study 2 |
|---|---|
| `harness.py` (was `frozen.py`) | puts `../src5` (or `$SRC5_DIR`) on `sys.path` and checks `src5/FREEZE.md`. **Round 3:** the freeze covers this directory (`*.py`, `*.json`, `*.sh`), `src5_verify/dry_check5.py` and `run_conc_study2.sh` too, and a frozen file without a row is a mismatch |
| every module | imports `run5`, `model_agent5`, `world5`, `scheduler5`, `providers5` instead of the src4 modules |
| `batch_driver.py` | grid arguments are `run5.add_grid_args` (Study 2 templates, schedule indices, per-cell call cap, scheduler overrides). The **cost gates are per provider family plus total** (`budget5`, `--family-cap`, `--max-usd`), with an optional **per-model sub-cap** (`--model-cap`). Admission uses `run5.prior_estimate` (Study 1's observed costs) instead of a token bound. Spend entries carry `provider_family`. **Every Claude model**, Haiku included, can run here. **Round 3:** a contended episode and its matched control (adjacent in `run5.build_grid`) are admitted together (estimate of both, per config), advance together through the worst-case gate (when the gate holds a request of one arm, the partner's requests of that wave wait too), and are written only together (`run5.commit_episode`; a finished arm waits in `held_for_pair/`). |
| `gemini_preflight.py` | uses `src5/preflight5.py`. **V2:** adds a two-turn parallel-call check (two parallel `get_record` calls, then both function responses in one turn); it fails unless turn 1 made 2 calls and turn 2 was answered. Resumable without paying twice. |
| `tests_batch.py`, `tests_gemini.py` | same gates on the Study 2 grid; the chaos model uses `lease_calls`, `renew_lock` and fencing tokens; new family-cap test |
| `cells_done.py`, `fake_api.py`, `fake_gemini.py`, `gemini_*.py`, `replay.py` | module retargeting only; **V2:** `batch_driver.py` and `cells_done.py` pass `--probe` (first-reply probes) to `run5.build_grid` |

`run_rest.sh` is the Study 1 runner, kept for reference only. Study 2 runs through `../run_conc_study2.sh`.

## Equivalence (byte-identical model inputs), re-verified on src5

`tests_batch.EquivalenceGate` and `tests_gemini.GeminiGate` run the same grid twice: once through the sync
path (`run5.run_grid` with the real SDK or the harness OpenRouter provider) and once through the batch driver.
Both use the same fake model; only the transport differs. They assert:
- the multiset of request bodies is equal as JSON and as bytes;
- every `results.csv` column is equal;
- the scores are equal;
- the transcripts are equal except for the timing fields;
- the spend entries are equal.

Grids covered:
- **n = 2:** 4 configs × aware off/on × 14 templates × 2 schedules = 224 episodes.
- **n = 4:** 112 episodes.
- **n = 8:** 24 episodes.
- **A chaos model:** multi-call turns, locks with fencing tokens, messages, cap endings. **V2:** run over the 4 grid
  configs plus the labelled `all_peer_informed`, since no grid config offers messages any more.
- **V2: probe mode** (`--probe`, n = 2, 112 probe episodes): same request bodies, rows and transcripts.

A further test checks decisions against literal `run5 --dry-run`.

Results (2026-11-03, anthropic SDK 2.3.0, Python 3.13):

| suite | tests | result |
|---|---|---|
| `tests_batch` | 22 | OK |
| `tests_gemini` | 34 | OK |

V2 and Round 3 re-runs after the pre-spend fixes: see `../CHANGES_V2.md`.

```
cd src5_batch && python3 -m unittest tests_batch tests_gemini
```
