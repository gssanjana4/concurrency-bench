# Raw-SQL slice (src_sql): EXPLORATORY, post hoc, not pre-registered

This is a small separate experiment. It is **not** part of the pre-registered study (`paper-concurrency/PREREGISTRATION.md`, `src4/`), it tests no hypothesis, and any table it produces must be labelled *exploratory, post hoc, not pre-registered*. It imports `src4/providers.py`, `src4/model_agent4.py` (price table, spend log, fake provider) and `src4/preflight.py` read-only. It never writes to `src4/` (no bytecode either) or `results4/`. The FREEZE.md hashes and the full `src4/` file listing were checked before and after the tests and the dry run, and nothing changed.

## Question

Give LLM agents **raw SQL on a real database** (one SQLite file in WAL mode, Python stdlib) and run them **truly concurrently**: real threads, real connections, no scheduler. Do they protect their own read-modify-write with the database's own tools, or do they read, think, and then blind-write? The tools in question are:

- explicit transactions (`BEGIN IMMEDIATE ... COMMIT`, or a deferred `BEGIN`);
- in-place or conditional updates (`SET x = x - 1 WHERE x > 0`, `WHERE version = n`);
- guarded inserts and constraints (`INSERT ... WHERE NOT EXISTS`, a `UNIQUE` index, `INSERT OR FAIL`).

And does integrity hold on the final file?

## Why this is not a repeat of the main study

| | Main study (src4, pre-registered) | This slice |
|---|---|---|
| Question | Do agents use coordination options a tool API *offers* (re-read, CAS, locks, messages), and is the outcome serializable? | Do agents *choose* to protect their read-modify-write with the database's own primitives? Nothing is offered or named; SQL is the whole interface. |
| Interface | `get_record` / `update_record` / `claim` / locks / messages on versioned records | one `run_sql(sql)` tool plus `finish` |
| Concurrency | deterministic seeded interleaving with a forced read-to-write gap | wall-clock threads; each agent has its own `sqlite3` connection; real `SQLITE_BUSY` / `BUSY_SNAPSHOT` errors returned verbatim |
| Ground truth | ledger + serializability search | final database file + committed statements recovered from the SQL log |
| Tasks | 8 templates on inventory, seat, ticket, account, budget records | 4 new templates (below). None of them reuses a main-study template, record kind, wording or number. |

The four templates and the closest main-study analogue:

| template | what each agent must do | protection idiom it invites | closest main-study analogue, and the difference |
|---|---|---|---|
| `counter` | add its own k to a shared counter | `SET value = value + k` | none. The main study has no unconditional increment. Its budget templates are guarded spends, and `budget_control` commutes inside the API. |
| `handle` | **insert** a user with a handle that must be unique, on a table with **no** UNIQUE constraint | `INSERT ... WHERE NOT EXISTS`, a UNIQUE index, a write transaction | seat/ticket `claim` updates an existing record. Here the hazard is a phantom duplicate insert, which only a constraint or a write lock can stop. |
| `withdraw` | withdraw from a shared account; total requests exceed the balance; decline if insufficient | `SET b = b - a WHERE b >= a`, version CAS, `BEGIN IMMEDIATE` | conceptually closest to `inventory_last_unit`. It is kept because the guarded `UPDATE ... WHERE` is the canonical SQL idiom. |
| `order` | insert a confirmed order **and** decrement stock, across two tables; demand exceeds stock | one transaction around both writes, or a guarded decrement before the insert | `transfer_shared_source` also touches two records, but there both writes are updates of one kind. Here an insert in one table must match a decrement in another. |

## Design

- **Tools.** `run_sql(sql)` runs one or more `;`-separated statements on the agent's own connection, in order, and stops at the first error. It returns the rows of queries (at most 50 shown), `rows_affected` for writes, or the SQLite error text verbatim (for example `OperationalError: database is locked`). `finish(status, note)` ends the agent; `status` is `done` or `declined` and is its claim. Replying without a tool call also ends the agent, with no claim.
- **Connections.** Each connection uses `isolation_level=None`, so there is no implicit BEGIN and the agent controls transactions. It uses `cached_statements=0`, a busy timeout of 200 ms, and WAL mode. The SQLite authorizer records the exact tables and columns each statement reads and writes. It denies `ATTACH`/`DETACH`, which also blocks `VACUUM INTO`, and `load_extension`, so nothing outside the episode's file can be touched. If an agent ends with a transaction still open, the harness rolls it back and logs it.
- **Concurrency.** All agents start together (barrier). Their model calls and SQL interleave in real time. Model latency is the think time. Temperature 0 is requested, but timing is not deterministic, so repeated episodes of a cell are repetitions, not replays.
- **Prompt** (short; fixed for every agent and model):
  > You are agent_k. You have SQL access to a shared SQLite database (a database file in WAL mode) through the run_sql tool; each call runs on your own database connection. Other clients may be reading and writing the same database at the same time as you.
  > Schema: *(the CREATE TABLE statements)*
  > Task: *(one sentence, e.g. "Withdraw 60 from account 1 in table accounts. The balance must never go below 0: if it is less than 60, do not withdraw and finish with status "declined".")*
  > When you are finished, call finish with status "done" if you completed the task or "declined" if you did not, and a one-line note.

  The sentence about other clients is always on. It mirrors the main study's aware sentence. The question here is whether agents protect themselves when they *know* the database is shared. Nothing in the prompt names a primitive.
- **Turn cap** 12 executed non-finish tool calls per agent (at most 13 completions), as in the main study. Other settings: max_tokens 4096, no prompt caching (the prompts are below Haiku's minimum cacheable length), episode timeout 900 s.
- **Grid** (`run_sql.sh`): `claude-haiku-4-5-20251001` and `openrouter:qwen/qwen3.6-27b-20260422` × 4 templates × 2 variants × n ∈ {2, 4} × 4 repetitions = **128 episodes, 384 agents**. Episodes are visited repetition-major, so a run stopped by the cap still has balanced coverage.

### Integrity (per episode; `tasks_sql.check_integrity`)

Data-invariant violations, listed in precedence order (the first present is `primary_kind`):

| template | violation kinds |
|---|---|
| counter | `lost_update` (a committed increment is missing from the final value), `over_applied` |
| handle | `duplicate_handle` (more than one row has the handle), `lost_registration` (an agent's committed insert is gone) |
| withdraw | `overdraft` (balance < 0), `oversubscribed` (withdrawals reported done exceed the start balance), `lost_update`, `over_applied` |
| order | `negative_stock`, `oversold` (confirmed qty > start stock), `lost_update`, `stock_order_mismatch` (stock ≠ start − confirmed; missing or orphan decrement), `duplicate_order` |

All templates also have `schema_damaged` and `collateral_write` (a seed row the task never needs was changed). A separate flag, `report_mismatch`, records `false_success`, `unreported_effect` and `double_success`: the agent's finish claim disagrees with what it committed. This flag is not an integrity violation.

### Protection behavior (per agent; full definitions in `classify_sql.py`)

From the SQL log, each agent gets these flags:

- `used_txn`, `txn_immediate`
- `rmw_in_txn`: a read and the following write happen in one transaction. A deferred BEGIN counts, because in WAL a stale snapshot makes the write fail with `SQLITE_BUSY_SNAPSHOT`. Wrapping only the write does not count.
- `used_atomic_update`, `used_conditional_update`, `used_cas`, `used_guarded_insert`
- `added_constraint`, `used_conflict_clause`
- `checked_rows_affected`, and its opposite `false_success_after_zero`
- busy errors, `retried_after_busy`, `set_busy_timeout`
- `blind_write`: an effective write to the contended table that none of these protects: a transaction read, an in-place update, an equality CAS, a guarded insert, or a UNIQUE index. A threshold `WHERE b >= 60` with a literal `SET b = 40` counts as *conditional but blind*.
- `all_protected`, `left_txn_open`, `atomic_pair` (order only), `no_write`

"Protected" describes the agent's own statement. Integrity is judged separately on the file. For example, a version CAS is safe only if every writer bumps the version.

## Run

On the Mac, from anywhere:

```
bash ~/Desktop/idempotencybench/src_sql/run_sql.sh            # real run: resumable, hard cap $5
bash ~/Desktop/idempotencybench/src_sql/run_sql.sh --dry-run  # scripted fake agents, no keys, no money
bash ~/Desktop/idempotencybench/src_sql/run_sql.sh --check-only
```

- **It will not compete with the main run.** It refuses to start while a `src4/run_full.sh` or `src4/run4.py` process is running. It also refuses while `results4/full/run.log` ends in an unfinished session, meaning no `=== FULL RUN DONE`, total-cost-cap stop or `=== STOPPED before phase` line after the last `=== start`. If the main run crashed and you have decided not to resume it, `ALLOW_SQL_BEFORE_FULL_DONE=1` skips the log check only. A running process always blocks.
- It uses the same `.env` (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`) and `.venv` conventions as `src4/run_pilot.sh`, runs `src4/preflight.py` once, keeps the Mac awake, and retries provider failures up to 5 times.
- It writes only to `results_sql/` (dry run: `results_sql/dry_run/`). The output layout follows run4: `results.csv` (one row per episode), `agents.csv` (one row per agent), `transcripts/<id>.json` (messages, every SQL statement with its authorizer access set, transaction state and timing, flags, integrity, final DB contents), `dbs/<id>.sqlite` (the final file), `spend.jsonl` and `failures.jsonl`.
- Rerunning resumes the run, and earlier spend counts toward the cap. When the grid finishes, the script runs the analysis: `results_sql/analysis/{tables.md, tables_appendix.tex, numbers.json}`. To run it by hand:

```
python3 src_sql/analyze_sql.py results_sql/results.csv --out results_sql/analysis
```

The analysis reports, per model × template × n (and pooled per model × n), the violation rate with a Wilson 95% CI (unit: episode), the counts of primary kinds, the report-mismatch rate and the violation rate split by whether the episode had a blind writer. It also reports the share of agents with each behavior, with Wilson CIs. These are descriptive, because agents within an episode are not independent. `tables_appendix.tex` uses booktabs and adjustbox, as in the paper, and every caption says EXPLORATORY.

Tests (no network): `cd src_sql && python3 -m unittest tests_sql -v`.

## Cost

These figures come from `python3 src_sql/run_sql.py --models ... --estimate`, using `src4/prices.json`.

| estimate | Haiku 4.5 | Qwen3.6-27B | total |
|---|---|---|---|
| pilot-calibrated: main-study pilot cost per agent ($0.0049 Haiku, $0.0024 Qwen) × 1.5 | $1.41 | $0.68 | **$2.09** |
| token model, typical: 6 completions/agent | 1.49M in + 0.17M out → $2.35 | 1.51M in + 0.35M out → $1.61 | **$3.97** |
| token model, worst case: every agent uses all 13 completions | $7.10 | $4.99 | $12.09 |

Token model assumptions:

- Each completion resends the system prompt and the tools (about 230 + 170 tokens, measured as characters / 4).
- Anthropic adds about 350 tokens of tool-use prompt to each request.
- The history grows by one output plus an 80-token tool result per step.
- Output per completion, including reasoning: 150 tokens for Haiku, 300 for Qwen.

Expected spend is $2–4. The hard $5 cap (preflight included) stops the run cleanly before an episode whose estimate would cross it. Because the grid is repetition-major, a capped run loses whole late repetitions, not cells.

## Dry run (fake scripted agents)

`run_sql.sh --dry-run` ran the full 128-episode grid in 1 min 54 s, with no failures and fake spend of $0.71 against the $5 cap, then ran the analysis. The scripted agents mix blind, atomic, transactional, CAS, guarded-insert and constraint styles, with 20–300 ms of fake think time. The run produced real busy errors (127 of 384 agents) and retries (103), real lost updates, duplicate handles and oversold stock on a real file. Protected-only mixes held integrity in the tests. These numbers test the harness only and say nothing about models.

## Limitations

- **Behavior flags come from the SQL text plus the authorizer.** The authorizer gives exact table and column identity. Clause structure (`SET` vs `WHERE`) comes from a small parser that strips literals and comments. The parser's rules are unit-tested, but an unusual SQL form could be misread. Integrity is judged independently, on the final file.
- **Effects are inferred from claims and the log.** `lost_update` and the report kinds rely on which agents committed an effective write (`rows_affected > 0`) to the contended table, and assume a committed write intended the agent's own amount.
- **Prompt and environment are fixed.** The shared-database sentence and WAL mode are always on, and the busy timeout is fixed at 200 ms. A longer timeout would turn some busy errors into waits.
- **Sample is small.** Two models; n ∈ {2, 4}; 8 episodes per model × template × n.
