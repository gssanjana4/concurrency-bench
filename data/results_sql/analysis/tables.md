# Raw-SQL slice: tables

**EXPLORATORY (post hoc, not pre-registered): raw-SQL slice with truly concurrent agents. Not part of the confirmatory analysis of PREREGISTRATION.md; no hypothesis tests.**

Inputs: results_sql/results.csv. Dry-run rows dropped: 0. Provider-failure episodes logged: 0 (never written; 0 still missing).

## Integrity (episodes)

Violation = a data invariant failed on the final database (tasks_sql.check_integrity). Cells: k/n (rate [Wilson 95%]).

| model | n | template | episodes | violation | primary kinds | report mismatch | viol. if blind writer | viol. if none |
|---|---|---|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | 2 | counter | 8 | 1/8 (0.12 [0.02, 0.47]) | lost_update 1 | 0/8 (0.00 [0.00, 0.32]) | 1/1 (1.00 [0.21, 1.00]) | 0/7 (0.00 [0.00, 0.35]) |
| claude-haiku-4-5-20251001 | 2 | handle | 8 | 8/8 (1.00 [0.68, 1.00]) | duplicate_handle 8 | 8/8 (1.00 [0.68, 1.00]) | 8/8 (1.00 [0.68, 1.00]) | - |
| claude-haiku-4-5-20251001 | 2 | withdraw | 8 | 6/8 (0.75 [0.41, 0.93]) | lost_update 5, oversubscribed 1 | 5/8 (0.62 [0.31, 0.86]) | 3/3 (1.00 [0.44, 1.00]) | 3/5 (0.60 [0.23, 0.88]) |
| claude-haiku-4-5-20251001 | 2 | order | 8 | 8/8 (1.00 [0.68, 1.00]) | negative_stock 8 | 0/8 (0.00 [0.00, 0.32]) | - | 8/8 (1.00 [0.68, 1.00]) |
| claude-haiku-4-5-20251001 | 2 | all | 32 | 23/32 (0.72 [0.55, 0.84]) | duplicate_handle 8, negative_stock 8, lost_update 6, oversubscribed 1 | 13/32 (0.41 [0.26, 0.58]) | 12/12 (1.00 [0.76, 1.00]) | 11/20 (0.55 [0.34, 0.74]) |
| claude-haiku-4-5-20251001 | 4 | counter | 8 | 1/8 (0.12 [0.02, 0.47]) | lost_update 1 | 0/8 (0.00 [0.00, 0.32]) | 1/1 (1.00 [0.21, 1.00]) | 0/7 (0.00 [0.00, 0.35]) |
| claude-haiku-4-5-20251001 | 4 | handle | 8 | 8/8 (1.00 [0.68, 1.00]) | duplicate_handle 8 | 8/8 (1.00 [0.68, 1.00]) | 8/8 (1.00 [0.68, 1.00]) | - |
| claude-haiku-4-5-20251001 | 4 | withdraw | 8 | 7/8 (0.88 [0.53, 0.98]) | lost_update 7 | 7/8 (0.88 [0.53, 0.98]) | 6/6 (1.00 [0.61, 1.00]) | 1/2 (0.50 [0.09, 0.91]) |
| claude-haiku-4-5-20251001 | 4 | order | 8 | 8/8 (1.00 [0.68, 1.00]) | negative_stock 8 | 0/8 (0.00 [0.00, 0.32]) | - | 8/8 (1.00 [0.68, 1.00]) |
| claude-haiku-4-5-20251001 | 4 | all | 32 | 24/32 (0.75 [0.58, 0.87]) | duplicate_handle 8, lost_update 8, negative_stock 8 | 15/32 (0.47 [0.31, 0.64]) | 15/15 (1.00 [0.80, 1.00]) | 9/17 (0.53 [0.31, 0.74]) |
| openrouter:qwen/qwen3.6-27b-20260422 | 2 | counter | 8 | 0/8 (0.00 [0.00, 0.32]) | - | 0/8 (0.00 [0.00, 0.32]) | - | 0/8 (0.00 [0.00, 0.32]) |
| openrouter:qwen/qwen3.6-27b-20260422 | 2 | handle | 8 | 8/8 (1.00 [0.68, 1.00]) | duplicate_handle 8 | 8/8 (1.00 [0.68, 1.00]) | 8/8 (1.00 [0.68, 1.00]) | - |
| openrouter:qwen/qwen3.6-27b-20260422 | 2 | withdraw | 8 | 0/8 (0.00 [0.00, 0.32]) | - | 0/8 (0.00 [0.00, 0.32]) | - | 0/8 (0.00 [0.00, 0.32]) |
| openrouter:qwen/qwen3.6-27b-20260422 | 2 | order | 8 | 4/8 (0.50 [0.22, 0.78]) | negative_stock 3, oversold 1 | 1/8 (0.12 [0.02, 0.47]) | - | 4/8 (0.50 [0.22, 0.78]) |
| openrouter:qwen/qwen3.6-27b-20260422 | 2 | all | 32 | 12/32 (0.38 [0.23, 0.55]) | duplicate_handle 8, negative_stock 3, oversold 1 | 9/32 (0.28 [0.16, 0.45]) | 8/8 (1.00 [0.68, 1.00]) | 4/24 (0.17 [0.07, 0.36]) |
| openrouter:qwen/qwen3.6-27b-20260422 | 4 | counter | 8 | 0/8 (0.00 [0.00, 0.32]) | - | 0/8 (0.00 [0.00, 0.32]) | - | 0/8 (0.00 [0.00, 0.32]) |
| openrouter:qwen/qwen3.6-27b-20260422 | 4 | handle | 8 | 8/8 (1.00 [0.68, 1.00]) | duplicate_handle 8 | 8/8 (1.00 [0.68, 1.00]) | 8/8 (1.00 [0.68, 1.00]) | - |
| openrouter:qwen/qwen3.6-27b-20260422 | 4 | withdraw | 8 | 0/8 (0.00 [0.00, 0.32]) | - | 0/8 (0.00 [0.00, 0.32]) | - | 0/8 (0.00 [0.00, 0.32]) |
| openrouter:qwen/qwen3.6-27b-20260422 | 4 | order | 8 | 8/8 (1.00 [0.68, 1.00]) | negative_stock 6, oversold 2 | 3/8 (0.38 [0.14, 0.69]) | - | 8/8 (1.00 [0.68, 1.00]) |
| openrouter:qwen/qwen3.6-27b-20260422 | 4 | all | 32 | 16/32 (0.50 [0.34, 0.66]) | duplicate_handle 8, negative_stock 6, oversold 2 | 11/32 (0.34 [0.20, 0.52]) | 8/8 (1.00 [0.68, 1.00]) | 8/24 (0.33 [0.18, 0.53]) |

## Protection behavior (agents)

Share of agents with each flag (classify_sql docstring). Agents are not independent within an episode; intervals are descriptive. `retried after BUSY`: denominator = agents that got a busy error.

### claude-haiku-4-5-20251001, n = 2, counter (16 agents; claims {'done': 16})

| behavior | agents |
|---|---|
| got a BUSY error | 0/16 (0.00 [0.00, 0.19]) |
| explicit txn | 0/16 (0.00 [0.00, 0.19]) |
| BEGIN IMMEDIATE/EXCL. | 0/16 (0.00 [0.00, 0.19]) |
| read+write in one txn | 0/16 (0.00 [0.00, 0.19]) |
| atomic update | 16/16 (1.00 [0.81, 1.00]) |
| conditional update | 0/16 (0.00 [0.00, 0.19]) |
| CAS (WHERE col = old) | 0/16 (0.00 [0.00, 0.19]) |
| guarded INSERT | 0/16 (0.00 [0.00, 0.19]) |
| added constraint | 0/16 (0.00 [0.00, 0.19]) |
| conflict clause | 0/16 (0.00 [0.00, 0.19]) |
| checked rows affected | 0/16 (0.00 [0.00, 0.19]) |
| retried after BUSY | - |
| blind write | 1/16 (0.06 [0.01, 0.28]) |
| all writes protected | 15/16 (0.94 [0.72, 0.99]) |
| left txn open | 0/16 (0.00 [0.00, 0.19]) |
| no write | 0/16 (0.00 [0.00, 0.19]) |

### claude-haiku-4-5-20251001, n = 2, handle (16 agents; claims {'done': 12, 'declined': 4})

| behavior | agents |
|---|---|
| got a BUSY error | 0/16 (0.00 [0.00, 0.19]) |
| explicit txn | 0/16 (0.00 [0.00, 0.19]) |
| BEGIN IMMEDIATE/EXCL. | 0/16 (0.00 [0.00, 0.19]) |
| read+write in one txn | 0/16 (0.00 [0.00, 0.19]) |
| atomic update | 0/16 (0.00 [0.00, 0.19]) |
| conditional update | 0/16 (0.00 [0.00, 0.19]) |
| CAS (WHERE col = old) | 0/16 (0.00 [0.00, 0.19]) |
| guarded INSERT | 1/16 (0.06 [0.01, 0.28]) |
| added constraint | 0/16 (0.00 [0.00, 0.19]) |
| conflict clause | 0/16 (0.00 [0.00, 0.19]) |
| checked rows affected | 0/16 (0.00 [0.00, 0.19]) |
| retried after BUSY | - |
| blind write | 15/16 (0.94 [0.72, 0.99]) |
| all writes protected | 1/16 (0.06 [0.01, 0.28]) |
| left txn open | 0/16 (0.00 [0.00, 0.19]) |
| no write | 0/16 (0.00 [0.00, 0.19]) |

### claude-haiku-4-5-20251001, n = 2, withdraw (16 agents; claims {'done': 7, 'declined': 9})

| behavior | agents |
|---|---|
| got a BUSY error | 0/16 (0.00 [0.00, 0.19]) |
| explicit txn | 0/16 (0.00 [0.00, 0.19]) |
| BEGIN IMMEDIATE/EXCL. | 0/16 (0.00 [0.00, 0.19]) |
| read+write in one txn | 0/16 (0.00 [0.00, 0.19]) |
| atomic update | 15/16 (0.94 [0.72, 0.99]) |
| conditional update | 5/16 (0.31 [0.14, 0.56]) |
| CAS (WHERE col = old) | 0/16 (0.00 [0.00, 0.19]) |
| guarded INSERT | 0/16 (0.00 [0.00, 0.19]) |
| added constraint | 0/16 (0.00 [0.00, 0.19]) |
| conflict clause | 0/16 (0.00 [0.00, 0.19]) |
| checked rows affected | 2/16 (0.12 [0.03, 0.36]) |
| retried after BUSY | - |
| blind write | 3/16 (0.19 [0.07, 0.43]) |
| all writes protected | 11/16 (0.69 [0.44, 0.86]) |
| left txn open | 0/16 (0.00 [0.00, 0.19]) |
| no write | 0/16 (0.00 [0.00, 0.19]) |

### claude-haiku-4-5-20251001, n = 2, order (16 agents; claims {'done': 16})

| behavior | agents |
|---|---|
| got a BUSY error | 0/16 (0.00 [0.00, 0.19]) |
| explicit txn | 0/16 (0.00 [0.00, 0.19]) |
| BEGIN IMMEDIATE/EXCL. | 0/16 (0.00 [0.00, 0.19]) |
| read+write in one txn | 0/16 (0.00 [0.00, 0.19]) |
| atomic update | 16/16 (1.00 [0.81, 1.00]) |
| conditional update | 0/16 (0.00 [0.00, 0.19]) |
| CAS (WHERE col = old) | 0/16 (0.00 [0.00, 0.19]) |
| guarded INSERT | 0/16 (0.00 [0.00, 0.19]) |
| added constraint | 0/16 (0.00 [0.00, 0.19]) |
| conflict clause | 0/16 (0.00 [0.00, 0.19]) |
| checked rows affected | 0/16 (0.00 [0.00, 0.19]) |
| retried after BUSY | - |
| blind write | 0/16 (0.00 [0.00, 0.19]) |
| all writes protected | 16/16 (1.00 [0.81, 1.00]) |
| left txn open | 0/16 (0.00 [0.00, 0.19]) |
| stock+order in one txn | 0/16 (0.00 [0.00, 0.19]) |
| no write | 0/16 (0.00 [0.00, 0.19]) |

### claude-haiku-4-5-20251001, n = 2, all (64 agents; claims {'done': 51, 'declined': 13})

| behavior | agents |
|---|---|
| got a BUSY error | 0/64 (0.00 [0.00, 0.06]) |
| explicit txn | 0/64 (0.00 [0.00, 0.06]) |
| BEGIN IMMEDIATE/EXCL. | 0/64 (0.00 [0.00, 0.06]) |
| read+write in one txn | 0/64 (0.00 [0.00, 0.06]) |
| atomic update | 47/64 (0.73 [0.62, 0.83]) |
| conditional update | 5/64 (0.08 [0.03, 0.17]) |
| CAS (WHERE col = old) | 0/64 (0.00 [0.00, 0.06]) |
| guarded INSERT | 1/64 (0.02 [0.00, 0.08]) |
| added constraint | 0/64 (0.00 [0.00, 0.06]) |
| conflict clause | 0/64 (0.00 [0.00, 0.06]) |
| checked rows affected | 2/64 (0.03 [0.01, 0.11]) |
| retried after BUSY | - |
| blind write | 19/64 (0.30 [0.20, 0.42]) |
| all writes protected | 43/64 (0.67 [0.55, 0.77]) |
| left txn open | 0/64 (0.00 [0.00, 0.06]) |
| no write | 0/64 (0.00 [0.00, 0.06]) |

### claude-haiku-4-5-20251001, n = 4, counter (32 agents; claims {'done': 32})

| behavior | agents |
|---|---|
| got a BUSY error | 0/32 (0.00 [0.00, 0.11]) |
| explicit txn | 0/32 (0.00 [0.00, 0.11]) |
| BEGIN IMMEDIATE/EXCL. | 0/32 (0.00 [0.00, 0.11]) |
| read+write in one txn | 0/32 (0.00 [0.00, 0.11]) |
| atomic update | 32/32 (1.00 [0.89, 1.00]) |
| conditional update | 0/32 (0.00 [0.00, 0.11]) |
| CAS (WHERE col = old) | 0/32 (0.00 [0.00, 0.11]) |
| guarded INSERT | 0/32 (0.00 [0.00, 0.11]) |
| added constraint | 0/32 (0.00 [0.00, 0.11]) |
| conflict clause | 0/32 (0.00 [0.00, 0.11]) |
| checked rows affected | 0/32 (0.00 [0.00, 0.11]) |
| retried after BUSY | - |
| blind write | 1/32 (0.03 [0.01, 0.16]) |
| all writes protected | 31/32 (0.97 [0.84, 0.99]) |
| left txn open | 0/32 (0.00 [0.00, 0.11]) |
| no write | 0/32 (0.00 [0.00, 0.11]) |

### claude-haiku-4-5-20251001, n = 4, handle (32 agents; claims {'done': 26, 'declined': 6})

| behavior | agents |
|---|---|
| got a BUSY error | 0/32 (0.00 [0.00, 0.11]) |
| explicit txn | 0/32 (0.00 [0.00, 0.11]) |
| BEGIN IMMEDIATE/EXCL. | 0/32 (0.00 [0.00, 0.11]) |
| read+write in one txn | 0/32 (0.00 [0.00, 0.11]) |
| atomic update | 0/32 (0.00 [0.00, 0.11]) |
| conditional update | 1/32 (0.03 [0.01, 0.16]) |
| CAS (WHERE col = old) | 1/32 (0.03 [0.01, 0.16]) |
| guarded INSERT | 0/32 (0.00 [0.00, 0.11]) |
| added constraint | 0/32 (0.00 [0.00, 0.11]) |
| conflict clause | 0/32 (0.00 [0.00, 0.11]) |
| checked rows affected | 0/32 (0.00 [0.00, 0.11]) |
| retried after BUSY | - |
| blind write | 32/32 (1.00 [0.89, 1.00]) |
| all writes protected | 0/32 (0.00 [0.00, 0.11]) |
| left txn open | 0/32 (0.00 [0.00, 0.11]) |
| no write | 0/32 (0.00 [0.00, 0.11]) |

### claude-haiku-4-5-20251001, n = 4, withdraw (32 agents; claims {'declined': 22, 'done': 10})

| behavior | agents |
|---|---|
| got a BUSY error | 0/32 (0.00 [0.00, 0.11]) |
| explicit txn | 0/32 (0.00 [0.00, 0.11]) |
| BEGIN IMMEDIATE/EXCL. | 0/32 (0.00 [0.00, 0.11]) |
| read+write in one txn | 0/32 (0.00 [0.00, 0.11]) |
| atomic update | 32/32 (1.00 [0.89, 1.00]) |
| conditional update | 10/32 (0.31 [0.18, 0.49]) |
| CAS (WHERE col = old) | 0/32 (0.00 [0.00, 0.11]) |
| guarded INSERT | 0/32 (0.00 [0.00, 0.11]) |
| added constraint | 0/32 (0.00 [0.00, 0.11]) |
| conflict clause | 0/32 (0.00 [0.00, 0.11]) |
| checked rows affected | 4/32 (0.12 [0.05, 0.28]) |
| retried after BUSY | - |
| blind write | 11/32 (0.34 [0.20, 0.52]) |
| all writes protected | 18/32 (0.56 [0.39, 0.72]) |
| left txn open | 0/32 (0.00 [0.00, 0.11]) |
| no write | 0/32 (0.00 [0.00, 0.11]) |

### claude-haiku-4-5-20251001, n = 4, order (32 agents; claims {'done': 32})

| behavior | agents |
|---|---|
| got a BUSY error | 0/32 (0.00 [0.00, 0.11]) |
| explicit txn | 0/32 (0.00 [0.00, 0.11]) |
| BEGIN IMMEDIATE/EXCL. | 0/32 (0.00 [0.00, 0.11]) |
| read+write in one txn | 0/32 (0.00 [0.00, 0.11]) |
| atomic update | 32/32 (1.00 [0.89, 1.00]) |
| conditional update | 0/32 (0.00 [0.00, 0.11]) |
| CAS (WHERE col = old) | 0/32 (0.00 [0.00, 0.11]) |
| guarded INSERT | 0/32 (0.00 [0.00, 0.11]) |
| added constraint | 0/32 (0.00 [0.00, 0.11]) |
| conflict clause | 0/32 (0.00 [0.00, 0.11]) |
| checked rows affected | 0/32 (0.00 [0.00, 0.11]) |
| retried after BUSY | - |
| blind write | 0/32 (0.00 [0.00, 0.11]) |
| all writes protected | 32/32 (1.00 [0.89, 1.00]) |
| left txn open | 0/32 (0.00 [0.00, 0.11]) |
| stock+order in one txn | 0/32 (0.00 [0.00, 0.11]) |
| no write | 0/32 (0.00 [0.00, 0.11]) |

### claude-haiku-4-5-20251001, n = 4, all (128 agents; claims {'done': 100, 'declined': 28})

| behavior | agents |
|---|---|
| got a BUSY error | 0/128 (0.00 [0.00, 0.03]) |
| explicit txn | 0/128 (0.00 [0.00, 0.03]) |
| BEGIN IMMEDIATE/EXCL. | 0/128 (0.00 [0.00, 0.03]) |
| read+write in one txn | 0/128 (0.00 [0.00, 0.03]) |
| atomic update | 96/128 (0.75 [0.67, 0.82]) |
| conditional update | 11/128 (0.09 [0.05, 0.15]) |
| CAS (WHERE col = old) | 1/128 (0.01 [0.00, 0.04]) |
| guarded INSERT | 0/128 (0.00 [0.00, 0.03]) |
| added constraint | 0/128 (0.00 [0.00, 0.03]) |
| conflict clause | 0/128 (0.00 [0.00, 0.03]) |
| checked rows affected | 4/128 (0.03 [0.01, 0.08]) |
| retried after BUSY | - |
| blind write | 44/128 (0.34 [0.27, 0.43]) |
| all writes protected | 81/128 (0.63 [0.55, 0.71]) |
| left txn open | 0/128 (0.00 [0.00, 0.03]) |
| no write | 0/128 (0.00 [0.00, 0.03]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 2, counter (16 agents; claims {'done': 16})

| behavior | agents |
|---|---|
| got a BUSY error | 0/16 (0.00 [0.00, 0.19]) |
| explicit txn | 0/16 (0.00 [0.00, 0.19]) |
| BEGIN IMMEDIATE/EXCL. | 0/16 (0.00 [0.00, 0.19]) |
| read+write in one txn | 0/16 (0.00 [0.00, 0.19]) |
| atomic update | 16/16 (1.00 [0.81, 1.00]) |
| conditional update | 0/16 (0.00 [0.00, 0.19]) |
| CAS (WHERE col = old) | 0/16 (0.00 [0.00, 0.19]) |
| guarded INSERT | 0/16 (0.00 [0.00, 0.19]) |
| added constraint | 0/16 (0.00 [0.00, 0.19]) |
| conflict clause | 0/16 (0.00 [0.00, 0.19]) |
| checked rows affected | 0/16 (0.00 [0.00, 0.19]) |
| retried after BUSY | - |
| blind write | 0/16 (0.00 [0.00, 0.19]) |
| all writes protected | 16/16 (1.00 [0.81, 1.00]) |
| left txn open | 0/16 (0.00 [0.00, 0.19]) |
| no write | 0/16 (0.00 [0.00, 0.19]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 2, handle (16 agents; claims {'done': 16})

| behavior | agents |
|---|---|
| got a BUSY error | 0/16 (0.00 [0.00, 0.19]) |
| explicit txn | 0/16 (0.00 [0.00, 0.19]) |
| BEGIN IMMEDIATE/EXCL. | 0/16 (0.00 [0.00, 0.19]) |
| read+write in one txn | 0/16 (0.00 [0.00, 0.19]) |
| atomic update | 0/16 (0.00 [0.00, 0.19]) |
| conditional update | 0/16 (0.00 [0.00, 0.19]) |
| CAS (WHERE col = old) | 0/16 (0.00 [0.00, 0.19]) |
| guarded INSERT | 0/16 (0.00 [0.00, 0.19]) |
| added constraint | 0/16 (0.00 [0.00, 0.19]) |
| conflict clause | 0/16 (0.00 [0.00, 0.19]) |
| checked rows affected | 0/16 (0.00 [0.00, 0.19]) |
| retried after BUSY | - |
| blind write | 16/16 (1.00 [0.81, 1.00]) |
| all writes protected | 0/16 (0.00 [0.00, 0.19]) |
| left txn open | 0/16 (0.00 [0.00, 0.19]) |
| no write | 0/16 (0.00 [0.00, 0.19]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 2, withdraw (16 agents; claims {'done': 8, 'declined': 8})

| behavior | agents |
|---|---|
| got a BUSY error | 0/16 (0.00 [0.00, 0.19]) |
| explicit txn | 0/16 (0.00 [0.00, 0.19]) |
| BEGIN IMMEDIATE/EXCL. | 0/16 (0.00 [0.00, 0.19]) |
| read+write in one txn | 0/16 (0.00 [0.00, 0.19]) |
| atomic update | 16/16 (1.00 [0.81, 1.00]) |
| conditional update | 16/16 (1.00 [0.81, 1.00]) |
| CAS (WHERE col = old) | 0/16 (0.00 [0.00, 0.19]) |
| guarded INSERT | 0/16 (0.00 [0.00, 0.19]) |
| added constraint | 0/16 (0.00 [0.00, 0.19]) |
| conflict clause | 0/16 (0.00 [0.00, 0.19]) |
| checked rows affected | 10/16 (0.62 [0.39, 0.82]) |
| retried after BUSY | - |
| blind write | 0/16 (0.00 [0.00, 0.19]) |
| all writes protected | 8/16 (0.50 [0.28, 0.72]) |
| left txn open | 0/16 (0.00 [0.00, 0.19]) |
| no write | 0/16 (0.00 [0.00, 0.19]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 2, order (16 agents; claims {'done': 11, 'declined': 5})

| behavior | agents |
|---|---|
| got a BUSY error | 0/16 (0.00 [0.00, 0.19]) |
| explicit txn | 13/16 (0.81 [0.57, 0.93]) |
| BEGIN IMMEDIATE/EXCL. | 5/16 (0.31 [0.14, 0.56]) |
| read+write in one txn | 1/16 (0.06 [0.01, 0.28]) |
| atomic update | 14/16 (0.88 [0.64, 0.97]) |
| conditional update | 6/16 (0.38 [0.18, 0.61]) |
| CAS (WHERE col = old) | 0/16 (0.00 [0.00, 0.19]) |
| guarded INSERT | 0/16 (0.00 [0.00, 0.19]) |
| added constraint | 0/16 (0.00 [0.00, 0.19]) |
| conflict clause | 0/16 (0.00 [0.00, 0.19]) |
| checked rows affected | 3/16 (0.19 [0.07, 0.43]) |
| retried after BUSY | - |
| blind write | 0/16 (0.00 [0.00, 0.19]) |
| all writes protected | 11/16 (0.69 [0.44, 0.86]) |
| left txn open | 1/16 (0.06 [0.01, 0.28]) |
| stock+order in one txn | 10/16 (0.62 [0.39, 0.82]) |
| no write | 2/16 (0.12 [0.03, 0.36]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 2, all (64 agents; claims {'done': 51, 'declined': 13})

| behavior | agents |
|---|---|
| got a BUSY error | 0/64 (0.00 [0.00, 0.06]) |
| explicit txn | 13/64 (0.20 [0.12, 0.32]) |
| BEGIN IMMEDIATE/EXCL. | 5/64 (0.08 [0.03, 0.17]) |
| read+write in one txn | 1/64 (0.02 [0.00, 0.08]) |
| atomic update | 46/64 (0.72 [0.60, 0.81]) |
| conditional update | 22/64 (0.34 [0.24, 0.47]) |
| CAS (WHERE col = old) | 0/64 (0.00 [0.00, 0.06]) |
| guarded INSERT | 0/64 (0.00 [0.00, 0.06]) |
| added constraint | 0/64 (0.00 [0.00, 0.06]) |
| conflict clause | 0/64 (0.00 [0.00, 0.06]) |
| checked rows affected | 13/64 (0.20 [0.12, 0.32]) |
| retried after BUSY | - |
| blind write | 16/64 (0.25 [0.16, 0.37]) |
| all writes protected | 35/64 (0.55 [0.43, 0.66]) |
| left txn open | 1/64 (0.02 [0.00, 0.08]) |
| no write | 2/64 (0.03 [0.01, 0.11]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 4, counter (32 agents; claims {'done': 32})

| behavior | agents |
|---|---|
| got a BUSY error | 0/32 (0.00 [0.00, 0.11]) |
| explicit txn | 0/32 (0.00 [0.00, 0.11]) |
| BEGIN IMMEDIATE/EXCL. | 0/32 (0.00 [0.00, 0.11]) |
| read+write in one txn | 0/32 (0.00 [0.00, 0.11]) |
| atomic update | 32/32 (1.00 [0.89, 1.00]) |
| conditional update | 0/32 (0.00 [0.00, 0.11]) |
| CAS (WHERE col = old) | 0/32 (0.00 [0.00, 0.11]) |
| guarded INSERT | 0/32 (0.00 [0.00, 0.11]) |
| added constraint | 0/32 (0.00 [0.00, 0.11]) |
| conflict clause | 0/32 (0.00 [0.00, 0.11]) |
| checked rows affected | 0/32 (0.00 [0.00, 0.11]) |
| retried after BUSY | - |
| blind write | 0/32 (0.00 [0.00, 0.11]) |
| all writes protected | 32/32 (1.00 [0.89, 1.00]) |
| left txn open | 0/32 (0.00 [0.00, 0.11]) |
| no write | 0/32 (0.00 [0.00, 0.11]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 4, handle (32 agents; claims {'done': 31, 'declined': 1})

| behavior | agents |
|---|---|
| got a BUSY error | 0/32 (0.00 [0.00, 0.11]) |
| explicit txn | 0/32 (0.00 [0.00, 0.11]) |
| BEGIN IMMEDIATE/EXCL. | 0/32 (0.00 [0.00, 0.11]) |
| read+write in one txn | 0/32 (0.00 [0.00, 0.11]) |
| atomic update | 0/32 (0.00 [0.00, 0.11]) |
| conditional update | 0/32 (0.00 [0.00, 0.11]) |
| CAS (WHERE col = old) | 0/32 (0.00 [0.00, 0.11]) |
| guarded INSERT | 0/32 (0.00 [0.00, 0.11]) |
| added constraint | 0/32 (0.00 [0.00, 0.11]) |
| conflict clause | 0/32 (0.00 [0.00, 0.11]) |
| checked rows affected | 0/32 (0.00 [0.00, 0.11]) |
| retried after BUSY | - |
| blind write | 31/32 (0.97 [0.84, 0.99]) |
| all writes protected | 0/32 (0.00 [0.00, 0.11]) |
| left txn open | 0/32 (0.00 [0.00, 0.11]) |
| no write | 1/32 (0.03 [0.01, 0.16]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 4, withdraw (32 agents; claims {'done': 20, 'declined': 12})

| behavior | agents |
|---|---|
| got a BUSY error | 0/32 (0.00 [0.00, 0.11]) |
| explicit txn | 0/32 (0.00 [0.00, 0.11]) |
| BEGIN IMMEDIATE/EXCL. | 0/32 (0.00 [0.00, 0.11]) |
| read+write in one txn | 0/32 (0.00 [0.00, 0.11]) |
| atomic update | 32/32 (1.00 [0.89, 1.00]) |
| conditional update | 31/32 (0.97 [0.84, 0.99]) |
| CAS (WHERE col = old) | 3/32 (0.09 [0.03, 0.24]) |
| guarded INSERT | 0/32 (0.00 [0.00, 0.11]) |
| added constraint | 0/32 (0.00 [0.00, 0.11]) |
| conflict clause | 0/32 (0.00 [0.00, 0.11]) |
| checked rows affected | 15/32 (0.47 [0.31, 0.64]) |
| retried after BUSY | - |
| blind write | 0/32 (0.00 [0.00, 0.11]) |
| all writes protected | 20/32 (0.62 [0.45, 0.77]) |
| left txn open | 0/32 (0.00 [0.00, 0.11]) |
| no write | 0/32 (0.00 [0.00, 0.11]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 4, order (32 agents; claims {'declined': 4, 'done': 27, 'none': 1})

| behavior | agents |
|---|---|
| got a BUSY error | 6/32 (0.19 [0.09, 0.35]) |
| explicit txn | 25/32 (0.78 [0.61, 0.89]) |
| BEGIN IMMEDIATE/EXCL. | 6/32 (0.19 [0.09, 0.35]) |
| read+write in one txn | 4/32 (0.12 [0.05, 0.28]) |
| atomic update | 30/32 (0.94 [0.80, 0.98]) |
| conditional update | 7/32 (0.22 [0.11, 0.39]) |
| CAS (WHERE col = old) | 0/32 (0.00 [0.00, 0.11]) |
| guarded INSERT | 0/32 (0.00 [0.00, 0.11]) |
| added constraint | 0/32 (0.00 [0.00, 0.11]) |
| conflict clause | 0/32 (0.00 [0.00, 0.11]) |
| checked rows affected | 4/32 (0.12 [0.05, 0.28]) |
| retried after BUSY | 6/6 (1.00 [0.61, 1.00]) |
| blind write | 0/32 (0.00 [0.00, 0.11]) |
| all writes protected | 27/32 (0.84 [0.68, 0.93]) |
| left txn open | 1/32 (0.03 [0.01, 0.16]) |
| stock+order in one txn | 17/32 (0.53 [0.36, 0.69]) |
| no write | 2/32 (0.06 [0.02, 0.20]) |

### openrouter:qwen/qwen3.6-27b-20260422, n = 4, all (128 agents; claims {'done': 110, 'declined': 17, 'none': 1})

| behavior | agents |
|---|---|
| got a BUSY error | 6/128 (0.05 [0.02, 0.10]) |
| explicit txn | 25/128 (0.20 [0.14, 0.27]) |
| BEGIN IMMEDIATE/EXCL. | 6/128 (0.05 [0.02, 0.10]) |
| read+write in one txn | 4/128 (0.03 [0.01, 0.08]) |
| atomic update | 94/128 (0.73 [0.65, 0.80]) |
| conditional update | 38/128 (0.30 [0.22, 0.38]) |
| CAS (WHERE col = old) | 3/128 (0.02 [0.01, 0.07]) |
| guarded INSERT | 0/128 (0.00 [0.00, 0.03]) |
| added constraint | 0/128 (0.00 [0.00, 0.03]) |
| conflict clause | 0/128 (0.00 [0.00, 0.03]) |
| checked rows affected | 19/128 (0.15 [0.10, 0.22]) |
| retried after BUSY | 6/6 (1.00 [0.61, 1.00]) |
| blind write | 31/128 (0.24 [0.18, 0.32]) |
| all writes protected | 79/128 (0.62 [0.53, 0.70]) |
| left txn open | 1/128 (0.01 [0.00, 0.04]) |
| no write | 3/128 (0.02 [0.01, 0.07]) |

