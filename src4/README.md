# Concurrent agents on shared records (src4)

A stdlib-only Python 3.10 benchmark harness for this question: when several agents act at the same time on the same external records, do they coordinate, and what happens to data integrity when they don't? Everything here is deterministic. There is no network access, no API calls, and no LLM judge. The tests use scripted agents only.

## Files

| File | Purpose |
|---|---|
| `records.py` | `SharedStore`, the versioned records (`inventory`, `seat`, `account`, `ticket`, `budget`). `Ledger` is the ground truth: `WriteEffect` per committed write, `CallRecord` per tool call, `AgentEnd` per agent, plus scheduler flags. Also `verify_ledger` and replay helpers. |
| `world4.py` | `ConcurrentWorld` tool surface. `CoordinationConfig` (the experimental variable), `WorldConfig` (lock expiry, concurrency-aware-prompt flag), JSON `tool_schemas(config)`, `build_system_prompt`. |
| `scheduler.py` | Seeded round-based interleaving of N agents. Read-to-write gap, start jitter, turn cap, stall detection, `run_paired`. |
| `tasks4.py` | Intents (`Decrement`, `Claim`, `Transfer`, `GuardedSpend`, `JointWithdraw`), invariants, and the task catalog (conflict / still_valid / write_skew / control) for any N. |
| `agents4.py` | Scripted reference policies: `naive`, `rereader`, `careful_cas`, `give_up_on_conflict`, `lock_user`, `lock_leaker`, `messenger`. |
| `score4.py` | Scoring from the ledger, call log and final store only. |
| `instances4.py` | Deterministic full-run task instances: K per template (default 4), seeded, disjoint from the pilot; two instruction paraphrases. |
| `run4.py`, `model_agent4.py`, `providers.py`, `preflight.py` | Model-agent grid runner (resumable, cost-capped), model loop, provider layer, preflight. `prices.json` keys match an exact model id or that id plus `-YYYYMMDD` (so `claude-fable-5` never prices `claude-fable-5.1`). |
| `analyze4.py` | Frozen analysis: `results.csv` files (and transcripts, for H5) to `confirmatory.json` + `confirmatory.md` (pre-registered tests) and `numbers.json` + `tables.md` (exploratory). |
| `plan_full.py`, `run_full.sh` | Phase grid sizes, cost estimates and budget gate; the full three-phase run. |
| `tests4.py`, `tests_model4.py`, `tests_full4.py` | unittest suites (harness and scorer; model loop and runner; taxonomy, instances, aware axis, analysis). |
| `FREEZE.md` | sha256 of every frozen file, cited by the pre-registration. |

## Run

```
cd src4
python3 -m unittest tests4 tests_model4 tests_full4 -v
```

Full runs (three phases under one total cap, see the header of `run_full.sh`):

```
bash src4/run_full.sh --dry-run      # fake provider, no keys, no money
bash src4/run_full.sh                # real run; resumable
python3 src4/analyze4.py results4/full/phase{1,2,3}/results.csv --out results4/full/analysis
```

Minimal episode:

```python
import agents4 as A, tasks4 as T
from scheduler import ScheduleConfig, run_episode
from world4 import world_config
from score4 import score_episode

ep = run_episode(T.inventory_last_unit(2), A.NAIVE, world_config("none"), ScheduleConfig(seed=0, read_write_gap=2))
print(score_episode(ep).to_dict())
```

## Coordination configurations

Combine presets with `+`, for example `cas_available+locks+messages`.

| Preset | Effect |
|---|---|
| `none` | Blind writes. Versions are hidden. Silent last-writer-wins (this is the only place it exists). |
| `reread_only` | `get_record` returns the version. No conditional writes. |
| `cas_available` | `update_record(expected_version=...)` is optional. A stale version gets `409 Conflict ... current version is N`. `claim` becomes test-and-set. The call log labels the 409 `version_conflict` (and sets `conflict`) only if another agent wrote the record after the expected version; any other mismatch (a version that does not exist yet, or one superseded only by the caller's own write) is `invalid_version`, rejected the same way but not a concurrency conflict. |
| `cas_required` | Same as above, but a write without `expected_version` gets `428`. |
| `locks` | Adds `acquire_lock(record_id, lease_steps)` and `release_lock`. Another agent's lock causes writes to get `423`. Leases count in scheduler rounds. With `WorldConfig(lock_expiry=False)` leases never expire. |
| `messages` | Adds `send_message(to_agent, text)` and `read_messages()`. |

Rejected writes never commit. Response text is fixed for each outcome; it is not a variable.

## Metric definitions

The full definitions are in the `score4.py` module docstring. In short:

- **Write basis and actions**: the basis of a committed write is the latest version of that record the writer had seen (its last read, or its own previous write; a blind first write is based on the initial version). A write is an *action* only if it changes the value of its basis. **Deliberate rule:** a write that does not change the value the agent saw (a no-op write-back, such as reading stock 0 and writing 0) is not the agent's committed intent. It is not a take or sale for `no_oversubscription`, it does not make the agent committed, and it cannot fulfil the intent. It still appears in the ledger and the dependency graph.
- **fulfilled**: for every record in `intent.writes`, the agent's last action on it wrote exactly `intent.apply(S)`, where `S` is the state the agent acted on (the write's basis value, plus the agent's last reads of the other records). A garbage value does not fulfil the intent.
- **Coordination choices** (per agent), counted only from calls that succeeded:
  - `reread`: before some write attempt on record r, the agent made 2 or more successful reads of r since its last committed write to r.
  - `cas`: an `update_record` with a non-null `expected_version` that committed, or that the server rejected as a concurrency conflict (`version_conflict`). Calls rejected as invalid (400, 404, `invalid_version`) or blocked by a lock do not count.
  - `lock`: a successful `acquire_lock` (a 404 under a configuration without locks does not count).
  - `message`: a successful `send_message`, or a non-empty `read_messages` batch.
  - `none`: none of the above.
- **non_serializable** (called `lost_update` before 2026-10-31): no valid serial order of the committed agents' intents (each `intent.apply` must succeed at its position) produces the final store. All orders are searched, with memoisation. Every non-serializable episode gets exactly one primary sub-label (`primary_label`); the three are mutually exclusive and exhaustive, assigned by this precedence (first match wins):
  1. `stale_overwrite`: some committed write's basis is older than the version it overwrote. Judged per write, so a later re-read and rewrite does not hide an earlier stale overwrite. A blind write that overwrote another agent's version is stale.
  2. `partial_action`: no stale write, but some committed agent did not fulfil its intent (`partial_commits`), e.g. it got a 409 on a transfer's debit and credited the destination anyway, or committed a value that does not follow its intent.
  3. `write_skew`: neither of the above. Every write was fresh and every committed agent finished its whole intent, yet the combination is not serializable.

  Serializable episodes have no label. `stale_overwrite_seqs` lists stale writes in every episode, whatever the label; its length is the CSV column `n_stale_writes` (raw stale-write count, exploratory only; confirmatory tests use `primary_label`). `invariant_violation` is a separate metric.
- **graph_cycle**: Adya direct serialization graph over committed agents, with ww/wr/rw edges from installed versions, *effective reads* (the last read before the agent's write to that record; post-commit verification reads are excluded), and each write's basis (so every write contributes its own read edges, and a blind write reads the initial version). The read versions come from the server-side call log. The flag is true when the graph has a cycle.
  - On single-record tasks (blind writers included) and on 2-agent write-skew tasks, `graph_cycle == non_serializable` (tested).
  - Acyclic with no partial commit implies serializable (tested).
  - The graph is stricter when effects commute (`budget_control`).
- **invariant_violation**: a task invariant failed:
  - stock or balance below 0;
  - a seat or ticket holder replaced after being set (checked on the ledger);
  - committed takes (actions, see above) exceed the initial amount;
  - total spend exceeds the *initial* budget cap;
  - the budget cap was changed by an agent (`unchanged[cap]`; no intent writes the cap);
  - joint overdraft floor crossed;
  - money not conserved.
- **unnecessary_give_up**: all of the following hold:
  - the agent got at least one concurrency rejection (409 `version_conflict` or claim conflict, or 423 lock); an `invalid_version` 409 does not count;
  - it returned on its own without fulfilling its intent;
  - its intent was still valid in the store state at the moment it ended (replayed from the ledger).
- **abandoned**: the agent ended for any reason with its intent unfulfilled while the intent was still valid at that moment.
- **lock_leak**: the agent held an unexpired lock when it ended. `locks_held_at_end` lists the locks still held when the episode ended.
- **stall**: for `stall_rounds` consecutive rounds, no agent was suspended and every live agent's call was blocking (lock refused, write refused by another agent's lock, or an empty `read_messages`). A refusal by a lock whose lease ends within `max_rounds` is waiting, not blocking, so only non-expiring locks and empty mailboxes stall, and `lock_expiry` on/off is a real ablation whatever `stall_rounds` is.
- **conflict_observed**: some write was rejected for a concurrency conflict, or some committed write was stale.

### Aggregate rates

`score4.py` provides helpers that take a list of `EpisodeScore` and return a `Rate(numerator, denominator)` (`value` is `None` when the denominator is 0):

| Helper | Numerator | Denominator |
|---|---|---|
| `unnecessary_give_up_rate` | agents with `unnecessary_give_up` | agents that observed a conflict (`conflicts_seen > 0`) |
| `abandoned_rate` | agents with `abandoned` | ended agents whose intent was still valid (valid when they ended, or fulfilled) |
| `non_serializable_rate` | episodes with `non_serializable` | contended episodes (2 or more agents; solo runs excluded) |
| `sub_label_rates` | per sub-label: episodes with that `primary_label` (they sum to the `non_serializable_rate` numerator) | contended episodes |
| `invariant_violation_rate` | episodes with `invariant_violation` | contended episodes |
| `coordination_choice_rates` | per choice (`reread`, `cas`, `lock`, `message`, `none`): agents making it | all agents (choices overlap, so rates need not sum to 1) |

## Value validation

Money values must be finite, representable at cent precision (huge magnitudes such as `"9"*40` or `1e30` are rejected with 400, not a crash) and have at most two decimal places. Negative zero (`"-0"`, `"-0.00"`, `-0.0`) and strings with non-ASCII digits or underscores are rejected for every numeric kind. A non-string `to_agent` in `send_message` is a 400.

## Scheduler

Each round, the world clock ticks, and then every live, non-suspended agent makes one call, in an order drawn from `Random(seed)`.

With `read_write_gap = G`, an agent is suspended for G rounds after the first successful read of each decision cycle. A cycle starts at the beginning of the episode and again after every write attempt.

`run_paired` runs the focal agent alone on `task.restrict([focal])`, then runs the full task with the same seed.

## Results CSV and analysis

`results.csv` has one row per episode. The integrity column is `non_serializable`, plus `primary_label` and three 0/1 sub-label columns (exactly one is 1 on a non-serializable row). It also carries `instance` (`pilot` or 0..K-1), `wording`, and the per-episode denominators `n_conflict_agents` and `n_abandon_eligible`. run4 refuses to append to a `results.csv` whose header differs.

**Deprecated:** pilot CSVs (written before 2026-10-31) have `lost_update` and no `primary_label`. New CSVs have no `lost_update` column. `analyze4.py` reads pilot CSVs through a read-only alias: `non_serializable = lost_update`, with the primary label rebuilt from the old `stale_overwrite` / `write_skew` columns (exact under the old definitions). Pilot rows are excluded from analysis unless `--include-pilot` is given.

`analyze4.py` (definitions in its docstring) drops `dry_run` rows. It counts provider-failure episodes from `failures.jsonl` and reports every exclusion. Per (model, config, aware, n_agents) and scope (all / contended) it reports `non_serializable`, the three sub-labels, `invariant_violation`, the coordination choices, `unnecessary_give_up` and `abandoned`. Each rate is the mean of task-instance rates (seeds and agents aggregated within an instance first) with a Wilson 95% interval, n = instances. Paired comparisons (aware on vs off; each config vs `none`) pair exactly on (instance, seed). Each uses a sign-flip permutation test over instances (exact up to 16 non-zero differences, otherwise 10,000 seeded draws), with Holm within each (comparison, metric, n_agents) family.

These descriptive tables and permutation comparisons are EXPLORATORY and labelled so in the output; the Wilson interval on a mean of instance rates is an approximation used only for them.

The pre-registration's confirmatory tests are `analyze4.confirmatory()` (definitions in the "Confirmatory" section of its docstring), written to `confirmatory.json` and `confirmatory.md` next to `tables.md`. For H1, H2, H3, H4a, H4b and H6 it runs a one-sided cluster bootstrap over task instances (10,000 resamples, seed 20261031), falls back to an exact sign test when the bootstrap is degenerate (rates 0 or 1), and applies Holm across models within each hypothesis (alpha 0.05). H5 is a descriptive count with Wilson intervals, read from the transcripts. A hypothesis whose registered episodes were not all run for a model (budget cap) is reported as "not tested" for that model, never as a null result. Everything is also rerun excluding episodes with a truncated agent.
