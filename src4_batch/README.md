# src4_batch: batch execution for claude-sonnet-5, claude-fable-5 and Gemini 4 Argon

This directory runs the remaining Anthropic models of the pre-registered src4 grid through the Anthropic
Message Batches API (50% price), and `openrouter:google/gemini-4-argon-20261013` through Google's Gemini Batch
API (50% price; see [Gemini](#gemini-gemini-batch-api-instead-of-openrouter)). The Anthropic models see exactly
what they would see on the sync path. Nothing in `src4/` is modified: the driver imports the frozen modules and
refuses to run if any FREEZE.md hash differs.

## Files

| File | Purpose |
|---|---|
| `batch_driver.py` | The driver. It takes run4's grid arguments and writes the same outputs. It keeps state on disk, resumes after a crash, applies the cap, retries failed requests, and polls with backoff. |
| `replay.py` | The seam: deterministic replay of one frozen episode with recorded responses. |
| `fake_api.py` | Offline fake of the Anthropic Messages and Batches HTTP API. Its model is the run4 `--dry-run` model (`model_agent4.scripted_policy`). Used for dry runs and tests. |
| `frozen.py` | Puts `../src4` on `sys.path` (no bytecode written there), checks FREEZE.md, hashes this directory. |
| `switch_facts.py` | Facts for the deviation notes. `batch_switch_facts.json` is written once, just before the first Sonnet 5 / Fable 5 batch run. `batch_switch_facts_latest.json` is rewritten at every start and also holds provider failures and rate limits per phase and model. |
| `cells_done.py` | Counts a model's finished cells in a phase (transcript present, run4's resume test); used by run_rest.sh's retry loop. |
| `run_rest.sh` | Runner for the author's Mac: the rest of the full run (see below). |
| `tests_batch.py` | Tests: the equivalence gate, money, retries, crash/restart, plumbing. |
| `gemini_translate.py` | Gemini: OpenAI-format payload of the frozen OpenRouterProvider → Gemini GenerateContentRequest, and Gemini reply → the OpenRouter JSON the frozen provider parses. Pure functions. |
| `gemini_replay.py` | Gemini: the replay seam (`urllib.request.urlopen` under the frozen OpenRouterProvider). |
| `gemini_batch.py` | Gemini: Batch API backend (plain REST), dated price table, driver adapter. |
| `fake_gemini.py` | Gemini: offline fake of generateContent + Batch Mode with strict request checks (thought signatures included). |
| `gemini_preflight.py` | Gemini: one small real batch request before the first Gemini run; stops unless the served model is gemini-4-argon. |
| `prices_batch.json` | Gemini list prices per date period (Google pricing page), used × 0.5. Not `src4/prices.json`. |
| `tests_gemini.py` | Gemini tests: translation round trip, response parsing, gate, money, retries, restart, preflight. |

## Design: where the seam is

The seam is the HTTP transport under the real `anthropic` SDK client. A replayed episode runs through the frozen
call chain unmodified: `run4.run_one` → `scheduler.run_episode` → `model_agent4.ModelAgent` →
`providers.AnthropicProvider` → `model_agent4.UsageProbeClient` → `anthropic.Anthropic().messages.create`.
This is the chain `run4.make_provider` builds for a real Anthropic run. The frozen code therefore produces
everything the model sees: the prompt, the tool specs, the `cache_control` markers, `max_tokens` = 4096,
temperature 0 (sent via `extra_body` on SDKs without the kwarg), and the turn cap.

The SDK serializes the `POST /v1/messages` body and hands it to an `httpx.MockTransport`. That body is the
batch request's `params`, byte for byte. The transport answers with the recorded `message` object of the
batch result, and the SDK parses it the way it parses a sync response.

**Why lockstep replay is exact.** The scheduler is simulated: a seeded round order, no wall clock. A request
that an agent makes in scheduler round r depends only on the results of its own tool calls, all of which ran
in rounds before r. So one replay collects the request of every agent that needs a completion in the current
round:

- A missing response is recorded and answered with a placeholder (an empty end_turn message, which ends that agent).
- The replay is abandoned at the next world tick, before anything that depends on a placeholder can produce a request.
- An episode is written only from a replay with no missing response.

The tick is observed through `_TickWorld`, a subclass of the frozen `world4.ConcurrentWorld`. It calls
`super().tick()` and then the hook. It is bound as `scheduler.ConcurrentWorld` for the duration of a replay
and restored afterwards (tested).

The driver loop:

1. Collect every ended batch.
2. Replay each episode that got new responses.
3. Write each finished episode (transcript and results.csv row, through run4's own `csv_row`, `append_csv` and `write_json_atomic`).
4. Submit all new requests as one batch.
5. Poll with backoff (30 s, growing ×1.5 to 300 s) and repeat.

## Equivalence (the gate)

`tests_batch.EquivalenceGate` checks the batch driver against the sync path. Both use the same fake model and
the same real SDK; only the transport differs.

- **Sync path:** frozen `run4.run_grid` in real-run mode, with `make_provider` returning
  `AnthropicProvider(UsageProbeClient(sdk))`.
- **Grid:** n = 2 (6 configs × aware off/on × 8 templates × seeds 0, 1 = 192 episodes), n = 4 (96) and
  n = 8 (96). That is every config and both prompts.

The test asserts:

- **Request payloads.** The multiset of request bodies the batch driver submits equals the multiset the sync
  path POSTs, both as parsed JSON and as bytes (SDK encoder: compact separators, `ensure_ascii=False`). Every
  body has model, `max_tokens` 4096, temperature 0.0, `cache_control` on the system block and on the last
  tool only, and the frozen start message.
- **results.csv:** every column of every row is identical.
- **Scores:** identical.
- **Transcripts:** identical except these fields, and the test fails if any other field differs:
  - `run_info.started_utc`, `run_info.finished_utc`, `run_info.wall_seconds`. Batch values: first submission of the episode, last batch end, and their difference.
  - `run_info.execution` (new key): mode, batch ids, lockstep rounds, retried requests, retry generation, price factor.
  - `agents.<id>.turns[].at_utc`. Batch value: the `ended_at` of the batch that answered that completion. Sync value: the response time.
- **spend.jsonl:** the same entries in the frozen schema. Batch entries add `batch: true`, `batch_id`,
  `custom_id`, `batch_gen` and `price_factor`, and their `at_utc` is the batch end.

Further checks:

- **Against literal `run4 --dry-run` (FakeProvider):** identical messages, executions, ledgers, final stores,
  scores and CSV columns, apart from the provider-dependent token, cost and served-id columns.
- **Self-check during real runs:** after each replay of a finished episode, the driver compares the spend entry
  the frozen code would log with the one it logged when the batch result arrived. It aborts on any difference.

Differences in a real run that the gate cannot remove:

- `cost_usd` in turns, totals, rows and spend is 50% of the sync price, because `--price-factor` is 0.5. The
  gate runs at factor 1.0. `test_costs_are_exactly_half...` checks that every value is exactly half.
- results.csv row order follows completion order, not grid order. Analysis keys rows by `episode_id`.
- Batch prompt caching is best effort (docs: 30–98% hit rates). `cache_read_tokens` and `cache_write_tokens`, and
  so cost, can differ from what a sync run would have had. Model input does not change. These prompts are
  probably below the minimum cacheable length anyway, as with Haiku (see model_agent4's docstring).
- `model_served` comes from the batch result's `model` field, the same field the sync path reads.
- The text of a model's reply is a new sample, as with any rerun; temperature 0 does not make outputs
  deterministic (PREREGISTRATION.md, Temperature).
- Residual risk, not testable offline: the next request re-sends each earlier assistant turn as the SDK dumps
  the parsed content blocks (`exclude_unset`). If the API serialized a content block differently in batch
  results than in sync responses (for example an explicit `"citations": null`), that JSON would differ.
  It would not change what the model reads.

## Money

Prices are from prices.json × 0.5, for input, output, cache-write and cache-read tokens alike. Sources,
checked 2026-11-01:

- [Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing): "All usage is
  charged at 50 percent of the standard API prices". "The pricing discounts from prompt caching and Message
  Batches can stack". "All active models support the Message Batches API". Batch prices are listed for
  Sonnet 5 ($1 / $5 per MTok) and Fable 5 ($5 / $25). Errored, canceled and expired requests: "You will not
  be billed for these requests". Limits: 100,000 requests or 256 MB per batch, 24 h expiry, results kept
  29 days, `custom_id` must match `^[a-zA-Z0-9_-]{1,64}$`, "most batches completing within 1 hour".
- [Pricing](https://platform.claude.com/docs/en/about-claude/pricing): Sonnet 5 costs $2 input, $10 output,
  $2.50 5-minute cache write and $0.20 cache hit; Fable 5 costs $10, $50, $12.50 and $1 (the prices.json
  entries). The page says the cache multipliers "stack with other pricing modifiers, including the Batch API
  discount", and its batch table lists Sonnet 5 at $1 / $5 and Fable 5 at $5 / $25.
- [Model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations): `claude-sonnet-5`
  and `claude-fable-5` are Active, not retired before June 30, 2027 and June 9, 2027.

The cap is the one $330 cap of run_full.sh. It covers every spend.jsonl (preflight, phases 1–3, including
OpenRouter and earlier sync spend) plus the driver's own log. Two gates apply:

1. **Admission.** Episodes start in run4's grid order under run4's own rule: 1.5 × the most expensive finished
   episode of that model in that phase, else the token prior. The rule is applied at batch prices, with the
   unspent estimate of running episodes reserved.
2. **Per batch.** A batch is not submitted unless spend + the worst case of all batches in flight + this
   batch's worst case ≤ cap. Worst case per request = 0.5 × ((body bytes + 1000) × the dearest input rate +
   `max_tokens` × output rate). Requests that do not fit wait. If nothing fits and nothing is in flight, the
   driver exits 2.

## Failures, retries, restart

- **Retries.** Errored, expired, canceled or missing results are resubmitted in the next batch, up to 5 tries.
  After that, the replay serves the last error as the HTTP status the sync API would have returned (e.g. 400
  for `invalid_request_error`). The frozen provider then raises the same SDK exception, and the failures.jsonl
  line has run4's schema and message (tested against a sync run with the same error). The episode is dropped
  for this run. On the next run it starts afresh (new retry generation), as with run4.
- **Temperature rejected.** If the API rejects `temperature`, the replay serves that 400 locally, so the frozen
  provider drops temperature exactly as on the sync path. `temperature_effective` is then null (tested).
- **State on disk** (`<out>/batch_state/<model>/`):
  - `batches.json` holds every batch id, its requests and their outcomes. A submission intent is written
    before each create call. A crash between create and bookkeeping is settled on restart by finding the
    server batch whose `custom_id`s carry the intent's nonce.
  - `responses.jsonl` holds every succeeded message.
  - `episodes.json` holds the retry generation and lockstep rounds per episode.
  - A restart collects batches still in flight and never resubmits a request that is in flight or answered.
    This is tested for a crash after create, a crash while in flight, and re-collection.
- **Exit codes:** as run4. 0 finished, 2 cost cap, 3 provider failures, 1 refused.

## Running (author's Mac)

1. Stop `run_full.sh` (Ctrl-C). `run_rest.sh` refuses to start while it, `run4.py` or another driver runs.
2. Run `bash ~/Desktop/idempotencybench/src4_batch/run_rest.sh` (same `.env` and `.venv` as run_full.sh). To
   rehearse first, run `bash .../src4_batch/run_rest.sh --dry-run --base /tmp/rehearsal`.
3. For Gemini, add `GEMINI_API_KEY=...` to the same `.env`. While the key is missing, keep passing
   `--skip-model openrouter:google/gemini-4-argon-20261013`. To run Gemini later, stop the running invocation
   (finished episodes and paid batch results are kept) and start `run_rest.sh` again without the skip.

`run_rest.sh` does the following:

- Checks FREEZE and records the switch facts. It refuses if any Sonnet 5 / Fable 5 episode was already run
  synchronously, or if any Gemini episode was run through OpenRouter.
- Runs the preflight unless it already passed, as run_full.sh does.
- For each phase 1, 2, 3, runs the frozen `plan_full.py` budget gate (unchanged and conservative: list prices).
  Then it runs the models in the registered order, minus any `--skip-model`:
  - **qwen, haiku, gpt-5.5:** the frozen `src4/run4.py` with run_full.sh's exact arguments. Finished episodes
    are skipped, so a finished model is only verified.
  - **gemini, sonnet-5, fable-5:** `batch_driver.py` with the same grid arguments, and run_full.sh's 5-attempt
    retry handling. Before the first Gemini batch run, `gemini_preflight.py` (once) and
    `switch_facts.py --record-gemini`.
- **Sync models retry until done.** Each sync model is an outer loop around the frozen run4.py, re-invoked
  until every cell of that model in the phase has a transcript.
  - Why: GPT-5.5 hit OpenRouter HTTP 429 ("new accounts are limited to 20 requests per minute"). run4 stops
    after 3 consecutive provider failures, and run_full.sh gives up after 5 attempts.
  - What it does: it sleeps 120–180 s between attempts and logs every attempt (episodes done before and
    after, failures.jsonl lines). Episodes that hit a rate limit are in failures.jsonl and are simply run
    again on the next attempt, never dropped. analyze4 counts them as `provider_failure_recovered`.
  - When it stops: there is no low attempt cap. It stops on the cost cap (exit 2), a credit/key limit or
    HTTP 402 (run4 exit 4), a refusal (exit 1), or 10 attempts in a row that finish no episode (exit 3;
    rerun to continue). This applies to all three sync models, Haiku included.
- Logs to `results4/full/run_batch.log`.

## Deviation notes (deviations.csv; columns deviation, reason, before_after, effect, registered_result)

Take N and the date from `results4/full/batch_switch_facts.json`, written just before the first Sonnet 5 /
Fable 5 batch run. Take the failure counts from `batch_switch_facts_latest.json` (`provider_failures`).

**Row 1: batch execution.**

- **deviation:** Execution mode for claude-sonnet-5 and claude-fable-5 changed from synchronous Messages API
  calls (src4/run_full.sh → run4.py) to the Anthropic Message Batches API (src4_batch/run_rest.sh →
  batch_driver.py). Episodes are advanced in lockstep by deterministic replay of the frozen episode code. Grid,
  phases, model order, prompts, tool specs, cache markers, max_tokens, temperature, turn cap, scheduler, scorer
  and the $330 total cap are unchanged. No file in src4/ was modified (FREEZE.md hashes verified at start).
- **reason:** Cost. Batch requests are billed at 50% of list price for input, output and cache tokens.
- **before_after:** Made after N confirmatory episodes of the other models had run, and before any
  claude-sonnet-5 or claude-fable-5 confirmatory episode. No Sonnet 5 / Fable 5 result had been seen.
- **effect:** None on model inputs. An offline equivalence test (src4_batch/tests_batch.py) showed that the
  request bodies are byte-identical to the sync path, with identical results rows, scores and transcripts
  apart from timing fields (n = 2, 4, 8; all configs; aware on and off). Differences:
  - timing fields: per-turn `at_utc` is the batch end time; `run_info` times span submission to the last batch end; `run_info.execution` is added;
  - recorded cost is at batch price;
  - results.csv row order follows completion order;
  - prompt-cache hits are best effort in batches;
  - the served model id is read from the batch result's `model` field.
- **registered_result:** Not applicable. Model inputs and analysis are unchanged.

**Row 2: provider-failure retries.**

- **deviation:** Retries for provider failures of the synchronous models now continue until every registered
  episode is done, instead of run_full.sh's 5 run4 attempts per (phase, model) with 60 s sleeps.
  src4_batch/run_rest.sh re-invokes the frozen run4.py with unchanged arguments, sleeping 120–180 s
  between attempts. It stops on the cost cap, an OpenRouter credit/key limit (402), or 10 consecutive
  attempts that finish no episode.
- **reason:** openrouter:openai/gpt-5.5-20260423 hit OpenRouter HTTP 429 rate limits ("new accounts are
  limited to 20 requests per minute"). The live run stopped at 235/768 phase-1 GPT-5.5 episodes (phase 1:
  Qwen 768, Haiku 768; spend $24.32).
- **before_after:** Before any analysis of confirmatory data. The decision depends only on provider errors,
  not on results.
- **effect:** None on episodes. Rate-limited episodes are logged in failures.jsonl and rerun from scratch,
  never dropped or replaced. analyze4 reports them as `provider_failure_recovered`. The registered stopping
  rule already makes the run resumable; only the number of automatic attempts changes.
- **registered_result:** Under the registered 5-attempt rule, the unfinished GPT-5.5 episodes would have
  needed manual reruns. If they were never rerun, the affected hypotheses would be "not tested" for GPT-5.5.

## Wall-clock and cost estimate

**Lockstep rounds.** One round per scheduler round in which some agent needs a completion. That is at least the
largest number of completions of any agent (≤ 13 under the turn cap) and at most the episode's total.

- Dry-run model: 3 rounds per episode at n = 2, 4 and 8.
- Pilot: about 3 completions per agent (Haiku, `locks`).
- A phase lasts as long as its slowest episode: about 3–5 rounds typical, up to about 13–20 when some agent runs to the turn cap.
- Admission adds about one more set of rounds per (phase, model). The first episodes are admitted under run4's
  token prior and the rest once one has finished (Sonnet admits about half of phase 1 at first, Fable about
  10%; in phases 2 and 3 Fable admits about 10–25%).

**Latency.** The docs say most batches finish within 1 hour; small batches often take minutes. Per (phase,
model): about 2 × (5–15 rounds) × (5–60 min), roughly 1–30 h, likely a few hours. Six (phase, model) runs for
Sonnet and Fable come to about 0.5–3 days of wall-clock, unattended and resumable.

**Cost** (plan_full estimates × the observed/estimate ratio so far: Haiku $0.0120/$0.0098 = 1.22, GPT $0.038/$0.0294 = 1.29):

| | Sonnet 5 | Fable 5 | total |
|---|---|---|---|
| plan_full estimate (list price) | $28.30 | $141.50 | $169.80 |
| sync, scaled by observed 1.22–1.29 | $34.7–36.6 | $173.3–182.9 | $207.9–219.5 |
| batch (× 0.5) | $17.3–18.3 | $86.6–91.4 | $104.0–109.7 |
| saving | | | about $104–110 |

## Gemini: Gemini Batch API instead of OpenRouter

`openrouter:google/gemini-4-argon-20261013` had run **zero** confirmatory episodes when this path was built
(run_rest.sh was running with `--skip-model` for it). All 960 Gemini episodes switch together; the driver and
switch_facts.py refuse to start if any non-batch Gemini transcript exists, so the two paths never mix.

### Availability and API facts (checked 2026-11-01)

| Fact | Source |
|---|---|
| Model code `gemini-4-argon`, one version listed ("stable"), latest update October 2026 (page updated 2026-10-30). Capabilities: **Batch API supported**, function calling supported, thinking supported (levels low, medium, high), implicit caching only. Output limit 65,536 tokens. | [Gemini 4 Argon model page](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon) |
| OpenRouter's `google/gemini-4-argon` was released Oct 13, 2026 (the `-20261013` date), served by Google AI Studio and Google Vertex. Its batch price is listed as $1 / $5. | [OpenRouter model page](https://openrouter.ai/google/gemini-4-argon-20261013) |
| Batch Mode: inline requests (total under 20 MB) or a JSONL file (up to 2 GB). Billed at 50% of the interactive price. System instructions, generation config and tools are supported per request. Target turnaround is 24 h; jobs expire after 48 h. Results are kept 6 weeks. Creation is not idempotent. | [Batch Mode guide](https://ai.google.dev/gemini-api/docs/batch-mode) |
| REST: `POST v1beta/models/{m}:batchGenerateContent` returns an Operation. `GET v1beta/batches/{id}`: states `BATCH_STATE_{PENDING,RUNNING,SUCCEEDED,FAILED,CANCELLED,EXPIRED}`. Output is `inlinedResponses[]` {metadata, response \| error} "in the same order as the input requests", or a `responsesFile`. | [Batch API reference](https://ai.google.dev/api/batch-mode) |
| Prices for Gemini 4 Argon (paid tier, USD per MTok). Standard: $2 input / $10 output through Nov 30, 2026, then $4 / $20 from Dec 1, 2026. Batch: $1 / $5, then $2 / $10. "Output pricing includes thinking tokens". No prompt-length tiers. | [Pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Default thinking for `gemini-4-argon`: **"On (medium)"**. `max_output_tokens` limits output "including thought tokens". Response pricing is "the sum of output tokens and thinking tokens". | [Thinking](https://ai.google.dev/gemini-api/docs/thinking) |
| Gemini 4 and 3 require **thought signatures** for function calling. The first `functionCall` of each step in the current turn must carry its signature, or the API returns 400. On parallel calls the signature is on the first call only. Signatures on text parts are optional. | [Thought signatures](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures) |
| Gemini 3+ generates an `id` for every function call; return the matching id with the result. | [Function calling (Interactions API version of the page)](https://ai.google.dev/gemini-api/docs/interactions/function-calling) |
| `FunctionDeclaration.parametersJsonSchema`: "Describes the parameters to the function in JSON Schema format. This field is mutually exclusive with `parameters`" (the OpenAPI-subset field). | [Google GenAI SDK reference](https://googleapis.github.io/dotnet-genai/api/Google.GenAI.Types.FunctionDeclaration.html) |
| `FunctionResponse.response`: use the "output" key for the function output and the "error" key for error details. | [FunctionResponse reference](https://docs.cloud.google.com/java/docs/reference/google-cloud-vertexai/latest/com.google.cloud.vertexai.api.FunctionResponse) |
| Batch limits are separate from interactive limits: 100 concurrent batches. Gemini 4 Argon batch **enqueued tokens**: Tier 1 5,000,000, Tier 2 500,000,000, Tier 3 1,000,000,000. | [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) |
| OpenRouter normalizes `finish_reason` to `tool_calls`, `stop`, `length`, `content_filter` or `error`, and gives the raw value as `native_finish_reason`. Unsupported parameters are ignored. Reasoning tokens count against `max_tokens`. The `reasoning.encrypted` format is `google-gemini-v1`. | [OpenRouter API](https://openrouter.ai/docs/api-reference/overview), [reasoning tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) |

### Design

Same driver, same lockstep replay, same state, cap, retries and exit codes as above. The provider-specific
parts sit behind an adapter (`AnthropicAdapter` in batch_driver.py, `GeminiAdapter` in gemini_batch.py).

**Seam.** The frozen chain is unchanged: `run4.run_one` → `scheduler` → `ModelAgent` →
`providers.OpenRouterProvider.complete`, exactly what `run4.make_provider` builds for this model id. The frozen
provider still builds the OpenAI-format payload it would POST to OpenRouter. During a replay,
`urllib.request.urlopen` is bound to a local function (restored afterwards; tested). That function:

1. translates the payload into a Gemini `GenerateContentRequest`. This object, byte for byte, is the batch
   request.
2. answers with the recorded Gemini reply, rendered as OpenRouter chat-completion JSON, which the frozen
   provider parses as usual.

`providers.time` is bound to a no-sleep shim during a replay, so the frozen provider's own 429/5xx retry loop
runs instantly on served errors.

**Request translation** (`gemini_translate.to_gemini_request`; anything else is refused, never guessed):

| frozen OpenRouter payload | Gemini request |
|---|---|
| system message (str) | `systemInstruction.parts[0].text`, exact |
| `tools[].function{name, description, parameters}` | `tools[0].functionDeclarations[]{name, description, parametersJsonSchema}`: the frozen JSON Schema, unchanged (including the typeless `value` property and `additionalProperties: false`) |
| `tool_choice: "auto"` | `toolConfig.functionCallingConfig.mode: AUTO` (the API default) |
| user message | `{role: user, parts: [{text}]}` |
| assistant `{content, tool_calls, reasoning_details}` | `{role: model, parts: [{text}?, {functionCall{id, name, args}}…]}`. `args = json.loads(arguments)`. Gemini's call id is sent back. Each `thoughtSignature` goes back on the part it came from. |
| `tool` messages | `{functionResponse{id, name, response: {"output": <content string, exact>}}}`. Consecutive results go in one user turn, in call order. |
| `max_tokens: 4096` | `generationConfig.maxOutputTokens: 4096` |
| `temperature: 0.0` | `generationConfig.temperature: 0.0` |
| (no reasoning parameter) | no `thinkingConfig`, so Google's default applies (medium for this model) |

**Response rendering** (`to_openrouter_response`):

- **Text and calls.** Text parts are joined into `content`. `functionCall` parts become `tool_calls` with
  `arguments = json.dumps(args)` and id = Gemini's id. If Gemini sends no id, the id is `gsyn_<turn>_<i>`, and
  such ids are never sent to Gemini.
- **Signatures.** Each thought signature becomes a `reasoning_details` entry
  (`reasoning.encrypted`, `google-gemini-v1`). The frozen provider passes these back unchanged on the next
  request (it already does this for OpenRouter reasoning models), and the translation re-attaches them.
- **Finish reason.** `STOP` maps to `tool_calls` (if there are calls) or `stop`. `MAX_TOKENS` maps to
  `length`. SAFETY, RECITATION, BLOCKLIST, PROHIBITED_CONTENT, SPII and the IMAGE_* reasons map to
  `content_filter`. Everything else (MALFORMED_FUNCTION_CALL, OTHER, …) maps to `error`. The raw value is kept
  in `native_finish_reason`.
- **Blocked prompt.** `promptFeedback.blockReason` gives an empty reply with `content_filter`.
- **Usage.** `prompt_tokens = promptTokenCount`, `completion_tokens = candidatesTokenCount +
  thoughtsTokenCount` (both billed as output), `reasoning_tokens = thoughtsTokenCount`.
- **Served model.** `model = modelVersion`, so `model_served` is `"<modelVersion> @Google Gemini Batch API"`.
- **Errors.** A reply with no candidate and no block reason is treated as an errored request and retried. A
  per-request error (google.rpc.Status) is served after the last try as the HTTP status Google maps it to
  (400, 429, 503, …), in OpenRouter's provider-error envelope. The frozen provider then raises exactly as on the
  sync path, and failures.jsonl gets run4's line:
  `openrouter:google/gemini-4-argon-20261013: RuntimeError: OpenRouter HTTP 400: …`.

**Backend.** Plain REST over the httpx module the installed anthropic SDK already ships. The google-genai SDK is
not used, for three reasons:

- what is submitted is exactly the JSON the translation produced, so there is no SDK object round trip that
  could rename or drop `thoughtSignature`, `parametersJsonSchema` or function-call ids;
- there is no new dependency on the author's Mac;
- the same MockTransport fake serves tests and dry runs.

How the backend behaves:

- Requests go inline, chunked under 16 MB (the limit is 20 MB).
- Create is never retried, because it is not idempotent. A crash between create and bookkeeping is settled by
  matching result keys, as for Anthropic. GETs are retried.
- Job-level `FAILED`, `EXPIRED` and `CANCELLED` outcomes apply to every request without its own result, and
  those requests are resubmitted (up to 5 tries).
- **Enqueued-token gate:** the estimated input tokens in flight (body bytes / 3, conservative) stay ≤
  `--max-enqueued-tokens`, default 4,000,000 (Tier 1 is 5M). Override it with `GEMINI_MAX_ENQUEUED_TOKENS`
  if the key is Tier 2+.

**Recorded per completion.** These come from the frozen code, unchanged:

- `model_served` (from `modelVersion`);
- `stop_reason` and `provider_meta.native_finish_reason`;
- `provider_meta.reasoning_tokens` and `reasoning_details_n`;
- `usage.reasoning` (thinking tokens), with `usage.output` including thinking tokens;
- `temperature_effective: "unverified"` (Google does not echo it, as with OpenRouter);
- cost at batch price.

Per episode, `run_info.execution` adds:

- `mode: gemini_batch_api`;
- `gemini_model`;
- `served_model_versions`;
- `native_usage` (promptTokenCount, cachedContentTokenCount, candidatesTokenCount, thoughtsTokenCount);
- the batch ids.

Every raw Gemini reply is kept in `batch_state/<model>/responses.jsonl`.

**Preflight.** `gemini_preflight.py` runs before the first Gemini batch, once. It sends the frozen preflight
request (built by the frozen provider and translated) as a one-request batch and waits for it. It prints the
model metadata, `modelVersion`, finish reason, usage and cost (the cost is added to the preflight spend log). It
exits 1 unless the served version is `gemini-4-argon` or `gemini-4-argon-*`, so nothing more is spent before
the served name is known. The batch id is saved before polling, so a rerun resumes the same batch.

### What differs from the OpenRouter path

The registered path sent the frozen payload to OpenRouter, and **OpenRouter** translated it for Google. Here
our translation replaces OpenRouter's. OpenRouter's internal translation is not published, so the points below
are where it may differ. The system prompt text, tool names, descriptions and schemas, history content, max
tokens, temperature and the absence of a reasoning parameter are the same by construction and by test.

1. **Tool schemas.** These go as `parametersJsonSchema` (full JSON Schema, unchanged). OpenRouter may have used
   the OpenAPI-subset `parameters` field after sanitizing (for example dropping `additionalProperties` or the
   typeless `value` schema).
2. **Tool results.** These go as `{"output": "<the JSON string>"}`. OpenRouter may have wrapped or parsed the
   string differently.
3. **Thought signatures and call ids.** These are returned exactly as Gemini sent them, as Google requires.
   Text-part signatures are kept, and several text parts are joined into one, as the frozen history stores one
   text block.
4. **Reasoning default.** No `thinkingConfig` is sent, so Google's default applies ("medium" for this model).
   OpenRouter publishes a per-model `default_enabled` / `default_effort`. If OpenRouter sends an explicit
   `thinkingLevel` for this model when the request has no `reasoning`, the effective level could have differed.
   That could not be checked from here (openrouter.ai/api/v1/models was unreachable). Thought summaries are not
   requested (`includeThoughts` unset); summaries do not enter the model's context.
5. **Upstream.** Always the Gemini API (AI Studio), batch tier. OpenRouter could route to AI Studio or Vertex.
6. **Finish-reason mapping** for SAFETY / blocked / MALFORMED_FUNCTION_CALL follows OpenRouter's documented
   normalized set. The exact mapping OpenRouter applies is not published; `native_finish_reason` keeps the raw
   value, so analysis can re-classify. `error` counts as truncated in the frozen agent (`TRUNCATED_STOPS`), as it
   would on OpenRouter.
7. **Recorded fields.** The transcript `provider` is `gemini_batch` (was `openrouter`). `model_served` is
   `<modelVersion> @Google Gemini Batch API`. `cost_source` is `price_table` at batch price (OpenRouter's path
   logs `reported` usage.cost). Implicitly cached prompt tokens are charged at the full input rate (the frozen
   usage path has no cached-token bucket for OpenRouter), so logged cost slightly overstates.
   `cachedContentTokenCount` is kept in `native_usage`. The timing fields and `run_info.execution` differ as for
   Anthropic.
8. **Prompt and generation settings unchanged.** Temperature 0 is sent as registered. Google gives no
   temperature advice for this model on the pages above. Responses at temperature 0 are not deterministic.

### Money

`prices_batch.json` (new; `src4/prices.json` unchanged) holds Google's **list** prices for two periods.
Cost = list × `--price-factor` 0.5 for every token class, and a test checks that this equals Google's published
batch price for both periods.

- The period is picked by the end time of the batch that answered the completion.
- The switch to the December prices is put at 2026-11-30T00:00Z, one day early, so it is conservative in any
  time zone.
- Estimates and the per-batch worst case use the dearer December period.
- The cap is the same single $330 cap over every spend.jsonl (preflight and phases 1–3, including the Anthropic
  and OpenRouter spend).

**Cost estimate, Gemini's 960 episodes.** plan_full's estimate at the plan's price level is:

| | n = 2 (768 eps) | n = 4 (96 eps) | n = 8 (96 eps) | total |
|---|---|---|---|---|
| plan_full per episode | $0.0294 | $0.0647 | $0.1423 | |
| plan_full total | $22.58 | $6.21 | $13.66 | **$42.45** |

Observed GPT-5.5 cost is about 2.2× its plan estimate, which gives $93.4 at the plan's price level (3× Haiku,
about $3 / $15 per MTok).

| Gemini batch price | factor vs the plan's price level | estimate |
|---|---|---|
| $1 / $5 (through Nov 30) | 1/3 | **≈ $31** |
| $2 / $10 (Dec 1 on) | 2/3 | **≈ $62** |

If the plan's per-episode figure is taken as Gemini's own sync list cost, plan × 2.2 × 0.5 = $46.7. Thinking
at the default medium level is the main uncertainty in token use.

### Deviation notes (rows for deviations.csv)

Take the counts and the date from `results4/full/batch_switch_facts_gemini.json`, written just before the
first Gemini batch run (`run_rest.sh` calls `switch_facts.py --record-gemini`).

**Row 3: Gemini provider and execution path.**

- **deviation:** The provider and execution path for `openrouter:google/gemini-4-argon-20261013` changed. It was
  synchronous OpenRouter chat completions (src4/run_full.sh → run4.py → providers.OpenRouterProvider →
  OpenRouter → Google). It is now the Google Gemini Batch API, model `gemini-4-argon` (src4_batch/run_rest.sh →
  batch_driver.py), for all 960 Gemini episodes.
  - The frozen OpenRouterProvider still builds every request. src4_batch/gemini_translate.py replaces
    OpenRouter's OpenAI-to-Gemini translation and renders replies in OpenRouter's response format, so the frozen
    agent loop and scorer run unchanged.
  - Unchanged: the registered model id, grid, phases, system prompt text, tool names, descriptions and JSON
    schemas, message history, max_tokens 4096 (maxOutputTokens, thinking included), temperature 0, no
    reasoning or thinking parameter (provider default), turn cap, scheduler, scorer and the $330 total cap.
  - No file in src4/ was modified (FREEZE.md verified at every start).
- **reason:** Cost, since Gemini Batch is billed at 50% of the standard price. Also OpenRouter rate limits
  (GPT-5.5 HTTP 429).
- **before_after:** Before any Gemini confirmatory episode (0 Gemini episodes; N episodes of the other models
  had run, from batch_switch_facts_gemini.json). No Gemini result had been seen.
- **effect:** Same model-visible content by construction and by offline test (tests_gemini.py; n = 2, 4, 8, all
  configs, aware on and off):
  - system prompt, tools and multi-turn history are carried exactly;
  - the batch path equals a sequential path with the same translation (request bytes, results rows, scores,
    transcripts except timing);
  - decisions equal run4 --dry-run.

  Differences:
  - the translation layer is ours, not OpenRouter's: tool schemas as parametersJsonSchema, tool results as
    {"output": string}, thought signatures and call ids returned as Google requires, Google's default thinking
    level (OpenRouter's default for this model unverified);
  - upstream is always the Gemini API;
  - recorded provider is gemini_batch;
  - model_served comes from modelVersion;
  - cost is computed at batch price from token counts (cached tokens at full input price) instead of
    OpenRouter's usage.cost;
  - timing fields; results.csv row order.
- **registered_result:** Not available. The registered OpenRouter path was never run for Gemini confirmatory
  episodes.

**Row 4: run order.**

- **deviation:** Gemini's episodes run after the other models' episodes of the same phase, not between GPT-5.5
  and Sonnet 5 as registered. run_rest.sh was run with `--skip-model openrouter:google/gemini-4-argon-20261013`
  while the Gemini batch path was built. While the skip was in place, the other models, Sonnet 5 and Fable 5
  included, ran their phase-1 episodes (and possibly later phases) before any Gemini episode. The per-phase
  counts at the switch are in batch_switch_facts_gemini.json.
- **reason:** Time to build and test the Gemini batch path. The other models were not held up.
- **before_after:** Before any Gemini confirmatory episode; independent of results.
- **effect:** None on episode content. Episodes are independent (own seed and instance, no state shared across
  episodes). Two consequences:
  - Calendar time differs, so a server-side update of `gemini-4-argon` would show in `model_served`, which is
    recorded per completion.
  - The single $330 cap is now drawn last by Gemini rather than by Fable 5, so if the cap binds, Gemini
    episodes (not Fable 5's) are the ones left unrun.
- **registered_result:** The same episodes. Only which model's episodes the cap would cut differs.

## Tests

```
cd src4_batch && ../.venv/bin/python -m unittest tests_batch tests_gemini -v   # needs the anthropic SDK
cd src4 && python3 -m unittest tests4 tests_model4 tests_full4       # frozen suites, unchanged
python3 src4_batch/frozen.py                                         # FREEZE.md hashes
```

Results on 2026-11-01 (anthropic SDK 2.3.0, Python 3.13):

- tests_batch: 20 tests OK. This includes the gate at n = 2, 4 and 8 with the dry-run model, and the same gate
  with a harder "chaos" fake model that uses multi-call turns, locks, messages and the turn cap (n = 8: up to
  57 completions per episode in at most 19 lockstep rounds).
- Frozen suites: 146 tests OK. FREEZE: 20 files match.
- Full dry run `run_rest.sh --dry-run`: all three phases, 5,760 episodes, exit 0. The frozen analyze4.py read
  every row (no schema or duplicate problems).
- The sync retry loop was exercised with stub runners: a rate-limited stub finishes, a stub that never makes
  progress stops after 10 idle attempts with exit 3, and a credit-limit stub stops with exit 4.

After the Gemini change (same day):

- **tests_batch and tests_gemini: 54 tests OK** (20 + 34). The Anthropic tests are unchanged and still pass on
  the generalized driver. tests_gemini covers the following:
  - **translation round trip:** system prompt, the tool specs of all six presets as parametersJsonSchema, and a
    multi-turn history with parallel calls, tool results, Unicode, nested args, synthetic ids and signatures;
  - **response parsing:** multiple calls, text + call, empty, SAFETY, blocked prompt, MAX_TOKENS, malformed
    call and thought parts, each equal to the Completion the frozen provider builds from the equivalent
    OpenRouter response;
  - **the sync-vs-batch gate:** n = 2 (192 episodes), n = 4 and n = 8 (96 each), plus the chaos model at
    n = 2, 4, 8;
  - **literal run4 --dry-run equivalence;**
  - **money:** price periods, the 0.5 × list = published batch price check, the single cap, the enqueued-token
    gate;
  - **retries:** per-request errors, empty replies, job EXPIRED / FAILED / CANCELLED;
  - **failures after 5 tries:** 400 and 503, with failures.jsonl lines identical to the sync run4 line;
  - **other paths:** temperature rejection, safety blocks inside batches;
  - **restart:** crash after create, crash in flight, re-collection, resume;
  - **plumbing:** preflight, refusal to mix paths, backend parsing, create never retried.
- **The fake checks thought signatures.** The fake Gemini API recomputes each signature from the request prefix,
  so every gate request also proves that the earlier history was re-sent byte-identically.
- **Mutation check:** dropping the thought signatures or the temperature from the translation makes the tests
  fail.
- **Frozen suites:** 146 tests OK. FREEZE: 20 files match.
- **Full dry run** `run_rest.sh --dry-run`, all three phases with Gemini on the fake Batch API: 5,760 episodes
  (960 per model), exit 0. The frozen analyze4.py read every row (no schema or duplicate problems).
- **Skip-then-resume rehearsal:** phase 1 with `--skip-model` Gemini, then without it. Gemini ran last, and
  `batch_switch_facts_gemini_dry.json` recorded the other five models at 768 each and 0 Gemini sync
  transcripts.
