# Data of "Do LLM Agents Coordinate on Shared Records?"

Licence: **CC BY 4.0** for the instances, transcripts (ledgers included), result CSVs and logs, as stated in the registrations (`LICENSE.txt`). Model outputs inside the transcripts remain subject to the providers' terms (Anthropic, OpenAI and Alibaba Qwen through OpenRouter, Google Gemini); the Qwen model licence applies to Qwen outputs. The CC BY 4.0 terms govern; the data are intended for research use. The records are synthetic (generated names and numbers): no personal data.

## Study 4 (`results7/study4/`)

The paid run of 2026-11-16 (registered plan: https://osf.io/6asc8, `../study4/PREREGISTRATION_STUDY4.md`). One
directory per provider lane, as written by `../study4/run_conc_study4.sh`: `n2-anthropic/` (1,152 episodes: Haiku 4.5
and Sonnet 5, 512 each; Fable 5, 128 under `locks_s2text` only, after which the registered stage rule stopped it;
Message Batches) and `n2-openrouter/` (82 episodes, Qwen3.6-27B pinned to Alibaba, stopped when the OpenRouter account
ran out of credit), each with `transcripts/`, `results.csv` and `spend.jsonl` (`failures.jsonl`: provider failures
that produced no episode). Also `summary.md`, `run_study4.log`, `lane_<provider>.log` (local paths shortened),
`floor_gate.json` (the stage rule's decision), `openrouter_restarts.log`, `validity/`, `preflight/` and
`openrouter_balance.jsonl` (its `raw` provider response was removed; its `limit_remaining_usd` is the key's limit,
not the account balance). Not shipped: `batch_state/` and `held_for_pair/`, the dry-run transcripts.

## Study 3 (`results6/study3/`)

The paid run of 2026-11-15 (plan: `../study3/PREREGISTRATION_STUDY3.md`, uploaded to the OSF before the run; the
registration https://osf.io/3pa4k is retrospective, see `../osf_registration_records.md`). One directory per provider
lane, as written by `../study3/run_conc_study3.sh`: `n2-anthropic/` (1,792 episodes, Haiku 4.5 and Sonnet 5, Message
Batches) and `n2-openrouter/` (896 episodes, Qwen3.6-27B pinned to Alibaba), each with `transcripts/`, `results.csv`
and `spend.jsonl`. Also `summary.md`, `run_study3.log`, `lane_<provider>.log`, `validity/` and `validity_run.log` (the
scripted validity gate before spending), `preflight/` and `openrouter_balance.jsonl` (its `raw` provider response was
removed). Not shipped: `batch_state/` and `held_for_pair/` (empty at the end of the run), the dry-run transcripts.

## Study 2 (`results5/study2/`)

The paid run of 2026-11-09 (registered plan: the Study 2 registration (https://osf.io/zj3an), `date_registered` 2026-11-09T18:35:24Z; run log: `../STUDY2_RUN_LOG.md`). One directory per provider lane, exactly as written by `run_conc_study2.sh`:

| directory | transcripts | content |
|---|---|---|
| `probe-anthropic/` | 896 | first-reply probes, Haiku and Sonnet (one completion per agent, nothing executed); `results.csv`, `spend.jsonl` |
| `probe-gemini/` | 896 | first-reply probes, Gemini 4 Argon; `results.csv`, `spend.jsonl` |
| `probe-openrouter/` | 896 | first-reply probes, Qwen and GPT-5.5; `results.csv`, `spend.jsonl` |
| `n2-anthropic/` | 992 | core episodes (n = 2) Haiku, Sonnet; Fable extension block; `results.csv`, `spend.jsonl` |
| `n2-gemini/` | 672 | core episodes (n = 2) Gemini, aware off and on under locks/all_available; `results.csv`, `spend.jsonl` |
| `n2-openrouter/` | 640 | core episodes (n = 2) Qwen; GPT-5.5 core and extension blocks; `results.csv`, `spend.jsonl`, `failures.jsonl` |

Each transcript is one episode or probe: the prompts, every completion with its per-completion settings (`temperature_effective`, `model_served`, `served_host`, reasoning/thinking fields), the tool calls, the ledger and the stored score of the frozen scorer (`src5/score5.py`). `results.csv` is one row per episode; `spend.jsonl` one line per completion with cost; `failures.jsonl` provider failures that produced no episode. Extension-block rows (block priority 4) are descriptive only and enter no registered statistic.

Transcript list digest (the `inputs.sha256_of_list` that `analysis5/analyze5.py` records): all lanes `d444660fc174602ba8d23cb42a94d0a9205b6c24dd819dfcd448555f914430ac` over 4,992 files; probe lanes `e9451cf9c3e093e1227b7e4f55201a51964c5bb36c74048d17a9c9aa04a51aa6` over 2,688 files. Both equal the values in `../analysis5/out_study2/results.json` and `eligibility.json`, so these are exactly the files the registered analysis read (checked at build).

Also here: `summary.md` (descriptive summary written by the runner), `preflight/` (preflight spend and the Gemini batch preflight record), `validity/` (the reference-policy validity gate that ran before spending), `run_study2.log`, `lane_<provider>.log`, `validity_run.log` (the run), `summary_dry.md`, `run_study2_dry.log`, `rehearsal.log` (the no-cost rehearsal on the author's Mac before registration), `autorun_job004_s2go.log` (the queued job that started the paid run: freeze check, balance log, lanes, spend by provider) and `openrouter_balance.jsonl` (the shared key's usage before and after the OpenRouter lane, `analysis5/balance5.py`; its `raw` provider response was removed, see the top-level README).

Not shipped: `batch_state/` (provider batch request/response state; every stored completion is in the transcripts), `held_for_pair/` (empty at the end of the run), the dry-run rehearsal transcripts (regenerate with `bash run_conc_study2.sh --dry-run`).

## Study 1 (`results4/full/`, `results_sql/`)

`results4/full/`: the registered Study 1 run (three phases; transcripts with ledgers, result CSVs, failures and spend logs, preflight record, run logs), copied from the author's Mac.
`results_sql/`: the exploratory SQL slice (post hoc, not pre-registered): CSVs, transcripts, SQLite databases and its own analysis outputs.

The Study 1 pipeline reads them through `RESULTS4=<artifact>/data/results4/full` and `RESULTS_SQL=<artifact>/data/results_sql` (top-level README, "Study 1").
