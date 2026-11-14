# Study 2 run log (registered plan: osf.io/zj3an, date_registered 2026-11-09T18:35:24Z)

Kept during the paid run. Only failures, cost and progress are read from the logs, as the registration declares.
Entries marked DEVIATION go into the paper's Study 2 deviations table; NOTE entries are reported where relevant.

## 2026-11-09

- 10:36 PST: `run_conc_s2go.sh` started by the `.autorun_conc` runner (job 004). Freeze check OK (38 files). Validity
  gate: 372 rows, 0 required failures. Preflight: Qwen served by Alibaba, GPT by OpenAI, Haiku/Sonnet/Fable OK,
  Gemini batch ping and two-turn parallel-call check OK (served model version gemini-4-argon). Lanes started 10:40 PST.
- Balance log (`analysis5/balance5.py --phase before`): OpenRouter key usage $158.85, remaining $41.15 (cap $28).
- Rehearsal history: a no-cost `--dry-run` on the Mac (job 002, 09:48 PST, before registration) failed with
  `pf[@]: unbound variable` under macOS bash 3.2; fixed in `run_conc_study2.sh` (empty-array idiom), refrozen,
  registration hashes updated BEFORE filing (CHANGES_V2.md Round 5). Second rehearsal with the paid interpreter
  (job 003, `.venv/bin/python`, anthropic SDK 2.3.0) exit 0, 5,160 transcripts, dry_check5 OK.
- DEVIATION (text, not procedure): the registration's "Declared confounds" says "Haiku applies [temperature 0]".
  The Anthropic API rejected `temperature` for claude-haiku-4-5-20251001 in the batch path
  (`invalid_request_error: temperature: Extra inputs are not permitted`), as it did for all three Claude models in
  Study 1 (results4/full/run_batch.log, 6 rejections; main.tex line 234). The driver's registered handling applied:
  after the first rejection the requests were resent without `temperature` and `temperature_effective` is logged
  null. In the first Haiku probe batches ~40 % of requests errored; the ~60 % that returned in the same batches were
  nevertheless stored with `temperature_effective` null (the independent verification, V3, found null in all 3,846
  Haiku completions), so the stored record does not distinguish them; treat every Haiku completion as run at the
  provider default, as for Sonnet and Fable. Analysis unchanged. Report: the confound entry should read "all three
  Claude models reject it and run at the provider default (Study 1 found the same)".
- NOTE: `submission 5c893852f1df has no batch on the server: dropped (its requests will be resubmitted)` in the
  Anthropic lane: a create call that did not register server-side; the driver's crash-safety path resubmitted
  the requests. No data effect.
- NOTE (cost gate behaviour): batches are submitted in waves of ~37 (Gemini) / ~50 (Haiku) requests because the
  per-block model sub-cap (1.3 x estimate) is compared against the worst-case cost of requests in flight
  (max_tokens 4096 each); actual cost per completion is ~$0.001, in line with the plan. Throughput, not budget,
  is the effect: Gemini batches end in ~4 min, Anthropic in ~2-3 min.
- NOTE (analyst exposure, declared): while diagnosing the errored Anthropic requests, Claude printed the first
  record of `probe-anthropic/batch_state/.../responses.jsonl`, which showed the opening sentence of one Haiku a1
  probe reply (episode claude-haiku-4-5-20251001__all_available__inventory_last_unit_ctrl@i0, a control probe).
  No outcome, label or score was read. Later inspections filtered to error objects and metadata only.
- Spend at 11:07 PST (all lanes): about $0.96 of $69 total; probe completions: Haiku 292, Gemini 229, Qwen 459;
  GPT probes finished (224 episodes).

- 13:13 PST check. Probe blocks done: Haiku 448, Sonnet 448, Qwen 672, GPT 224; Gemini 714/896 (gated waves of
  ~16-37 requests, ~4 min each). Core running: Haiku 232/448, Qwen 146/448. Spend by family (spend.jsonl):
  anthropic $3.82, openrouter $4.95, gemini $1.20 (caps 19/28/22).
- Cost vs plan (per episode): probes Haiku 1.45x, Qwen 1.5x, GPT 1.45x, Gemini 1.45x, Sonnet 1.05x; Haiku core
  $0.0098/episode vs plan mean ~$0.0067 (1.5x). The per-model sub-cap is cumulative 1.3 x (probe + core estimate):
  Haiku cap $4.78 against a projected $5.05, so the Haiku core block will probably stop a few percent short
  (about 14 pairs at the tail of the registered order) under the registered rule. Qwen projected ~$5.0 against a
  $5.27 cap (tight). No hand intervention; reported as the rule operating.

- 14:22 PST check. All probe blocks complete: probe-anthropic 896 (Haiku 448 + Sonnet 448), probe-openrouter 896
  (Qwen 672 + GPT 224), probe-gemini 896. Haiku core complete: 448/448 (the sub-cap did not bind; controls are
  cheaper than contended episodes). Sonnet core 112/448 running; Qwen core 302/448; Gemini core started (gated).
  Spend by family: anthropic $7.25, openrouter $6.38, gemini $1.49 (caps 19/28/22). Anthropic lane: one
  `!! batch create failed (APIConnectionError)` (transient; driver retried) and the expected temperature rejection
  for claude-sonnet-5.
- ELIGIBILITY STEP (registration: computed from probe transcripts only, before any episode result is opened):
  run 2026-11-09T22:22Z on the Mac (Linux VM python3, `python3 -I analysis5/analyze5.py eligibility --base
  results5/study2 --out analysis5/out_study2`; analyze5.py sha256 99dff56a… as registered). Inputs: 2,688 probe
  files (every cell at its registered probe count; Fable 0 by plan). Output `eligibility.json` sha256
  f4ad4f072fffc0e3a703ab708d61b5371e72f5481cb6f13a639f1598b228341d, posted to the OSF project 9qvpt as
  `eligibility_study2.json` (version 1, modified 2026-11-09T23:08:01Z, OSF-computed sha256 identical). Claude read
  only the file's structure and probe counts, not the rates. The core blocks were already running when it was
  posted (the runner executes blocks back to back); no episode result had been opened.

- 17:40 PST check. Anthropic lane finished 17:25 PST (exit 0): Haiku 448, Sonnet 448, Fable 96 core episodes;
  family spend $16.47 (cap 19). OpenRouter lane finished 16:52 PST (exit 0): Qwen 448, GPT 192 core episodes;
  family spend $19.49 (cap 28). Gemini core 324/672 (aware=both block running, gated waves), family spend $6.56
  (cap 22); at ~93 episodes/h it should finish around 21:30 PST, well before the Nov 30 price change.
  Total spend $42.52 (plan x1.15 = $58.82; caps $69). No lane stopped by a cap so far.

## 2026-11-09 evening: run complete

- 19:09 PST: all three lanes finished, exit 0; `run_conc_study2.sh exit 0`; job 004 exit 0. Balance log after:
  OpenRouter key usage $178.35 (change $19.49 = Study 2's own OpenRouter spend; others' spend $0.00; remaining $21.65).
- Final counts: probes 896 per lane (2,688); core n2-anthropic 992 (Haiku 448, Sonnet 448, Fable 96), n2-openrouter
  640 (Qwen 448, GPT 192), n2-gemini 672. Fable and GPT counts above the registration's core table are the plan's
  extension block (block 4), descriptive only, excluded from every registered statistic by analyze5.
- Spend by family: anthropic $16.47 (cap 19), openrouter $19.49 (cap 28), gemini $10.44 (cap 22); total $46.40
  (plan x1.15 $58.82). No cap stopped a lane; cap_truncated episodes: 0.
- 20:12 PST: registered analysis run on the Mac (Linux VM python3, `python3 -I analysis5/analyze5.py analyze ...
  --eligibility-sha256 f4ad4f07…`): 54 tests; results.json sha256 0c11cec935fee524c5587422…, numbers.tex
  a70c6f84b9c928604dcca18c…. Re-run in the cloud container on a copy of the data: 11,329 values compared, 0 material
  differences (float summation noise only at 1e-13). Study 2 results first opened by Claude at 20:14 PST, after
  the run ended and after eligibility was posted.
- Checks from results.json: isolation OK (0 control episodes with cross-agent edges); lock safety OK (0 violations);
  leakage not detected for any model; budget window clean. Flags: 3 GPT episodes served by a non-OpenAI host
  (sensitivity s5), 12 GPT provider failures (descriptive model).

- 21:00 PST: independent verification (review/V3_results_verification.md): RESULTS HOLD WITH CAVEATS, no blocker.
  Every registered number re-derived from the transcripts with separate code matches results.json exactly; stored
  scores equal the frozen scorer's output on every ledger; 52 labels read by hand all correct; pairing, isolation
  and lock safety confirmed. Caveats for the write-up: (1) under the CAS configs the confirmatory models have 0
  failures on the four single-record families, so their Δ comes from the write-skew and transfer families; (2) under
  locks Haiku/Qwen lock after reading (read-then-lock), and the blocking wait makes contention silent (no 409/423 to
  prompt a re-read; under CAS a 409 led to a re-read in 181/183 cases); (3) same-amount transfer instances: 32/35
  missing-leg failures follow a 409, a re-read that shows the expected post-debit balance, then a credit; (4) the
  primary measure should be named committed-intent (not final-state) serializability in the paper.
