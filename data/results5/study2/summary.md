| model | n | config | aware | arm | eps | clean | comp. | failed | top failed labels | fs | dsg | basis dsg | ever viol. | lock att/gr/eff | cas | promote | msg | fulfilled | cap ends | deadlocks | agent errors | ctrl w/ msg | exposure | cap-trunc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-fable-5 | 2 | all_available | 0 | contended | 12 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.42 | 0.00 | 0.00 | 0.79/0.79/0.75 | 0.62 | 0.00 | 0.00 | 0.50 | 0/24 | 0 | 0 | 0 | 0.50 | 0 |
| claude-fable-5 | 2 | all_available | 0 | control | 12 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.62/0.62/0.93 | 1.00 | 0.00 | 0.00 | 1.00 | 0/24 | 0 | 0 | 0 | 0.00 | 0 |
| claude-fable-5 | 2 | cas_available | 0 | contended | 12 | 0.67 | 0.33 | 0.00 |  | 0.00 | 0.75 | 0.00 | 0.33 | 0.00/0.00/0.00 | 0.88 | 0.00 | 0.00 | 0.46 | 0/24 | 0 | 0 | 0 | 0.54 | 0 |
| claude-fable-5 | 2 | cas_available | 0 | control | 12 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0/24 | 0 | 0 | 0 | 0.00 | 0 |
| claude-fable-5 | 2 | locks | 0 | contended | 12 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 1.00/1.00/1.00 | 0.00 | 0.00 | 0.00 | 0.50 | 0/24 | 0 | 0 | 0 | 0.50 | 0 |
| claude-fable-5 | 2 | locks | 0 | control | 12 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 1.00/1.00/1.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0/24 | 0 | 0 | 0 | 0.00 | 0 |
| claude-fable-5 | 2 | none | 0 | contended | 12 | 0.25 | 0.17 | 0.58 | lost_update 5, write_skew 2 | 0.58 | 0.75 | 0.67 | 0.33 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 0.79 | 0/24 | 0 | 0 | 0 | 0.25 | 0 |
| claude-fable-5 | 2 | none | 0 | control | 12 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0/24 | 0 | 0 | 0 | 0.00 | 0 |
| claude-haiku-4-5-20251001 | 2 | all_available | 0 | contended | 56 | 0.68 | 0.00 | 0.32 | write_skew 13, missing_leg 5 | 0.32 | 0.79 | 0.23 | 0.23 | 0.21/0.21/0.00 | 0.88 | 0.00 | 0.00 | 0.64 | 0/112 | 0 | 0 | 0 | 0.38 | 0 |
| claude-haiku-4-5-20251001 | 2 | all_available | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.17/0.17/0.11 | 1.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| claude-haiku-4-5-20251001 | 2 | cas_available | 0 | contended | 56 | 0.64 | 0.00 | 0.36 | write_skew 14, missing_leg 6 | 0.36 | 0.77 | 0.25 | 0.25 | 0.00/0.00/0.00 | 0.91 | 0.00 | 0.00 | 0.65 | 0/112 | 0 | 0 | 0 | 0.38 | 0 |
| claude-haiku-4-5-20251001 | 2 | cas_available | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| claude-haiku-4-5-20251001 | 2 | locks | 0 | contended | 56 | 0.18 | 0.00 | 0.82 | lost_update 31, write_skew 14 | 0.82 | 0.93 | 0.80 | 0.25 | 0.89/0.89/0.00 | 0.00 | 0.00 | 0.00 | 0.91 | 0/112 | 0 | 0 | 0 | 0.35 | 0 |
| claude-haiku-4-5-20251001 | 2 | locks | 0 | control | 56 | 0.98 | 0.00 | 0.02 | wrong_value 1 | 0.02 | 0.00 | 0.00 | 0.00 | 0.94/0.94/0.02 | 0.00 | 0.00 | 0.00 | 0.99 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| claude-haiku-4-5-20251001 | 2 | none | 0 | contended | 56 | 0.23 | 0.00 | 0.77 | lost_update 29, write_skew 14 | 0.77 | 0.77 | 0.77 | 0.25 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 0.89 | 0/112 | 0 | 0 | 0 | 0.12 | 0 |
| claude-haiku-4-5-20251001 | 2 | none | 0 | control | 56 | 0.93 | 0.00 | 0.07 | out_of_intent_write 2, wrong_value 2 | 0.07 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 0.96 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| claude-sonnet-5 | 2 | all_available | 0 | contended | 56 | 0.61 | 0.02 | 0.38 | write_skew 15, missing_leg 6 | 0.38 | 0.84 | 0.27 | 0.27 | 0.39/0.39/0.00 | 0.94 | 0.00 | 0.00 | 0.71 | 0/112 | 0 | 0 | 0 | 0.37 | 0 |
| claude-sonnet-5 | 2 | all_available | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.39/0.39/0.02 | 1.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| claude-sonnet-5 | 2 | cas_available | 0 | contended | 56 | 0.64 | 0.02 | 0.34 | write_skew 14, missing_leg 5 | 0.34 | 0.77 | 0.25 | 0.25 | 0.00/0.00/0.00 | 0.92 | 0.00 | 0.00 | 0.70 | 0/112 | 0 | 0 | 0 | 0.38 | 0 |
| claude-sonnet-5 | 2 | cas_available | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| claude-sonnet-5 | 2 | locks | 0 | contended | 56 | 0.61 | 0.00 | 0.39 | write_skew 12, lost_update 7 | 0.34 | 0.91 | 0.34 | 0.21 | 0.96/0.96/0.51 | 0.00 | 0.00 | 0.00 | 0.74 | 0/112 | 0 | 0 | 0 | 0.39 | 0 |
| claude-sonnet-5 | 2 | locks | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.90/0.90/0.61 | 0.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| claude-sonnet-5 | 2 | none | 0 | contended | 56 | 0.23 | 0.00 | 0.77 | lost_update 29, write_skew 14 | 0.77 | 0.77 | 0.77 | 0.25 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 0.91 | 0/112 | 0 | 0 | 0 | 0.12 | 0 |
| claude-sonnet-5 | 2 | none | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| gemini-4-argon-20261013 | 2 | all_available | 0 | contended | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.41 | 0.00 | 0.00 | 0.43/0.43/1.00 | 0.73 | 0.00 | 0.00 | 0.57 | 0/112 | 0 | 0 | 0 | 0.50 | 0 |
| gemini-4-argon-20261013 | 2 | all_available | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.44/0.44/1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| gemini-4-argon-20261013 | 2 | all_available | 1 | contended | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.39 | 0.00 | 0.00 | 0.43/0.43/1.00 | 0.73 | 0.00 | 0.00 | 0.57 | 0/112 | 0 | 0 | 0 | 0.50 | 0 |
| gemini-4-argon-20261013 | 2 | all_available | 1 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.44/0.44/0.98 | 1.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| gemini-4-argon-20261013 | 2 | cas_available | 0 | contended | 56 | 0.88 | 0.12 | 0.00 |  | 0.00 | 0.79 | 0.09 | 0.12 | 0.00/0.00/0.00 | 0.88 | 0.04 | 0.00 | 0.57 | 0/112 | 0 | 0 | 0 | 0.54 | 0 |
| gemini-4-argon-20261013 | 2 | cas_available | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 1.00 | 0.05 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| gemini-4-argon-20261013 | 2 | locks | 0 | contended | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 1.00/1.00/1.00 | 0.00 | 0.00 | 0.00 | 0.57 | 0/112 | 0 | 0 | 0 | 0.50 | 0 |
| gemini-4-argon-20261013 | 2 | locks | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 1.00/1.00/1.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| gemini-4-argon-20261013 | 2 | locks | 1 | contended | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 1.00/1.00/1.00 | 0.00 | 0.00 | 0.00 | 0.57 | 0/112 | 0 | 0 | 0 | 0.50 | 0 |
| gemini-4-argon-20261013 | 2 | locks | 1 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 1.00/1.00/1.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| gemini-4-argon-20261013 | 2 | none | 0 | contended | 56 | 0.27 | 0.20 | 0.54 | lost_update 29, write_skew 1 | 0.54 | 0.75 | 0.57 | 0.21 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 0.79 | 0/112 | 0 | 0 | 0 | 0.29 | 0 |
| gemini-4-argon-20261013 | 2 | none | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| gpt-5.5-20260423 | 2 | all_available | 0 | contended | 24 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.29 | 0.00 | 0.00 | 0.79/0.79/1.00 | 0.60 | 0.00 | 0.00 | 0.50 | 0/48 | 0 | 0 | 0 | 0.50 | 0 |
| gpt-5.5-20260423 | 2 | all_available | 0 | control | 24 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.71/0.71/1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0/48 | 0 | 0 | 0 | 0.00 | 0 |
| gpt-5.5-20260423 | 2 | cas_available | 0 | contended | 24 | 0.75 | 0.17 | 0.08 | write_skew 2 | 0.08 | 0.79 | 0.12 | 0.25 | 0.00/0.00/0.00 | 0.90 | 0.00 | 0.00 | 0.54 | 0/48 | 0 | 0 | 0 | 0.50 | 0 |
| gpt-5.5-20260423 | 2 | cas_available | 0 | control | 24 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0/48 | 0 | 0 | 0 | 0.00 | 0 |
| gpt-5.5-20260423 | 2 | locks | 0 | contended | 24 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 1.00/1.00/1.00 | 0.00 | 0.00 | 0.00 | 0.50 | 0/48 | 0 | 0 | 0 | 0.50 | 0 |
| gpt-5.5-20260423 | 2 | locks | 0 | control | 24 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 1.00/1.00/1.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0/48 | 0 | 0 | 0 | 0.00 | 0 |
| gpt-5.5-20260423 | 2 | none | 0 | contended | 24 | 0.21 | 0.08 | 0.71 | lost_update 13, write_skew 4 | 0.71 | 0.79 | 0.71 | 0.25 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 0.85 | 0/48 | 0 | 0 | 0 | 0.15 | 0 |
| gpt-5.5-20260423 | 2 | none | 0 | control | 24 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0/48 | 0 | 0 | 0 | 0.00 | 0 |
| qwen3.6-27b-20260422 | 2 | all_available | 0 | contended | 56 | 0.77 | 0.02 | 0.21 | missing_leg 5, write_skew 5 | 0.21 | 0.82 | 0.09 | 0.12 | 0.29/0.29/0.33 | 0.84 | 0.00 | 0.00 | 0.62 | 0/112 | 1 | 0 | 0 | 0.46 | 0 |
| qwen3.6-27b-20260422 | 2 | all_available | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.21/0.21/0.62 | 0.98 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| qwen3.6-27b-20260422 | 2 | cas_available | 0 | contended | 56 | 0.57 | 0.00 | 0.43 | write_skew 14, missing_leg 8 | 0.43 | 0.77 | 0.27 | 0.29 | 0.00/0.00/0.00 | 0.95 | 0.00 | 0.00 | 0.70 | 0/112 | 0 | 0 | 0 | 0.38 | 0 |
| qwen3.6-27b-20260422 | 2 | cas_available | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| qwen3.6-27b-20260422 | 2 | locks | 0 | contended | 56 | 0.30 | 0.00 | 0.70 | lost_update 25, write_skew 14 | 0.70 | 0.86 | 0.70 | 0.25 | 0.70/0.70/0.28 | 0.00 | 0.00 | 0.00 | 0.87 | 0/112 | 0 | 0 | 0 | 0.30 | 0 |
| qwen3.6-27b-20260422 | 2 | locks | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.69/0.69/0.29 | 0.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |
| qwen3.6-27b-20260422 | 2 | none | 0 | contended | 56 | 0.20 | 0.00 | 0.80 | lost_update 31, write_skew 14 | 0.80 | 0.80 | 0.80 | 0.25 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 0.93 | 0/112 | 0 | 0 | 0 | 0.10 | 0 |
| qwen3.6-27b-20260422 | 2 | none | 0 | control | 56 | 1.00 | 0.00 | 0.00 |  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00/0.00/0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0/112 | 0 | 0 | 0 | 0.00 | 0 |

## First-reply probes (one completion per agent; codes from model_agent5.first_reply_code)

| model | config | aware | arm | probes | first-reply codes |
|---|---|---|---|---|---|
| claude-haiku-4-5-20251001 | all_available | 0 | contended | 56 | read 56 |
| claude-haiku-4-5-20251001 | all_available | 0 | control | 28 | read 28 |
| claude-haiku-4-5-20251001 | all_available | 1 | contended | 56 | read 56 |
| claude-haiku-4-5-20251001 | all_available | 1 | control | 28 | read 28 |
| claude-haiku-4-5-20251001 | cas_available | 0 | contended | 56 | read 56 |
| claude-haiku-4-5-20251001 | cas_available | 0 | control | 28 | read 28 |
| claude-haiku-4-5-20251001 | cas_available | 1 | contended | 56 | read 56 |
| claude-haiku-4-5-20251001 | cas_available | 1 | control | 28 | read 28 |
| claude-haiku-4-5-20251001 | locks | 0 | contended | 56 | read 56 |
| claude-haiku-4-5-20251001 | locks | 0 | control | 28 | read 28 |
| claude-haiku-4-5-20251001 | locks | 1 | contended | 56 | read 48, lock 8 |
| claude-haiku-4-5-20251001 | locks | 1 | control | 28 | read 26, lock 2 |
| claude-haiku-4-5-20251001 | none | 0 | contended | 56 | read 56 |
| claude-haiku-4-5-20251001 | none | 0 | control | 28 | read 28 |
| claude-haiku-4-5-20251001 | none | 1 | contended | 56 | read 56 |
| claude-haiku-4-5-20251001 | none | 1 | control | 28 | read 28 |
| claude-sonnet-5 | all_available | 0 | contended | 56 | read 56 |
| claude-sonnet-5 | all_available | 0 | control | 28 | read 28 |
| claude-sonnet-5 | all_available | 1 | contended | 56 | read 32, lock 24 |
| claude-sonnet-5 | all_available | 1 | control | 28 | read 16, lock 12 |
| claude-sonnet-5 | cas_available | 0 | contended | 56 | read 56 |
| claude-sonnet-5 | cas_available | 0 | control | 28 | read 28 |
| claude-sonnet-5 | cas_available | 1 | contended | 56 | read 56 |
| claude-sonnet-5 | cas_available | 1 | control | 28 | read 28 |
| claude-sonnet-5 | locks | 0 | contended | 56 | read 51, lock 5 |
| claude-sonnet-5 | locks | 0 | control | 28 | read 26, lock 2 |
| claude-sonnet-5 | locks | 1 | contended | 56 | lock 47, read 9 |
| claude-sonnet-5 | locks | 1 | control | 28 | lock 24, read 4 |
| claude-sonnet-5 | none | 0 | contended | 56 | read 56 |
| claude-sonnet-5 | none | 0 | control | 28 | read 28 |
| claude-sonnet-5 | none | 1 | contended | 56 | read 56 |
| claude-sonnet-5 | none | 1 | control | 28 | read 28 |
| gemini-4-argon-20261013 | all_available | 0 | contended | 112 | read 64, lock 48 |
| gemini-4-argon-20261013 | all_available | 0 | control | 56 | read 32, lock 24 |
| gemini-4-argon-20261013 | all_available | 1 | contended | 112 | read 64, lock 48 |
| gemini-4-argon-20261013 | all_available | 1 | control | 56 | read 32, lock 24 |
| gemini-4-argon-20261013 | cas_available | 0 | contended | 112 | read 112 |
| gemini-4-argon-20261013 | cas_available | 0 | control | 56 | read 56 |
| gemini-4-argon-20261013 | cas_available | 1 | contended | 112 | read 112 |
| gemini-4-argon-20261013 | cas_available | 1 | control | 56 | read 56 |
| gemini-4-argon-20261013 | locks | 0 | contended | 112 | lock 112 |
| gemini-4-argon-20261013 | locks | 0 | control | 56 | lock 56 |
| gemini-4-argon-20261013 | locks | 1 | contended | 112 | lock 112 |
| gemini-4-argon-20261013 | locks | 1 | control | 56 | lock 56 |
| gemini-4-argon-20261013 | none | 0 | contended | 112 | read 112 |
| gemini-4-argon-20261013 | none | 0 | control | 56 | read 56 |
| gemini-4-argon-20261013 | none | 1 | contended | 112 | read 103, blind_write 9 |
| gemini-4-argon-20261013 | none | 1 | control | 56 | read 48, blind_write 8 |
| gpt-5.5-20260423 | all_available | 0 | contended | 28 | lock 17, read 11 |
| gpt-5.5-20260423 | all_available | 0 | control | 14 | lock 8, read 6 |
| gpt-5.5-20260423 | all_available | 1 | contended | 28 | lock 22, read 6 |
| gpt-5.5-20260423 | all_available | 1 | control | 14 | lock 9, read 5 |
| gpt-5.5-20260423 | cas_available | 0 | contended | 28 | read 28 |
| gpt-5.5-20260423 | cas_available | 0 | control | 14 | read 14 |
| gpt-5.5-20260423 | cas_available | 1 | contended | 28 | read 28 |
| gpt-5.5-20260423 | cas_available | 1 | control | 14 | read 14 |
| gpt-5.5-20260423 | locks | 0 | contended | 28 | lock 28 |
| gpt-5.5-20260423 | locks | 0 | control | 14 | lock 14 |
| gpt-5.5-20260423 | locks | 1 | contended | 28 | lock 28 |
| gpt-5.5-20260423 | locks | 1 | control | 14 | lock 14 |
| gpt-5.5-20260423 | none | 0 | contended | 28 | read 28 |
| gpt-5.5-20260423 | none | 0 | control | 14 | read 14 |
| gpt-5.5-20260423 | none | 1 | contended | 28 | read 28 |
| gpt-5.5-20260423 | none | 1 | control | 14 | read 14 |
| qwen3.6-27b-20260422 | all_available | 0 | contended | 84 | read 84 |
| qwen3.6-27b-20260422 | all_available | 0 | control | 42 | read 42 |
| qwen3.6-27b-20260422 | all_available | 1 | contended | 84 | read 82, lock 2 |
| qwen3.6-27b-20260422 | all_available | 1 | control | 42 | read 42 |
| qwen3.6-27b-20260422 | cas_available | 0 | contended | 84 | read 84 |
| qwen3.6-27b-20260422 | cas_available | 0 | control | 42 | read 42 |
| qwen3.6-27b-20260422 | cas_available | 1 | contended | 84 | read 84 |
| qwen3.6-27b-20260422 | cas_available | 1 | control | 42 | read 42 |
| qwen3.6-27b-20260422 | locks | 0 | contended | 84 | read 79, lock 5 |
| qwen3.6-27b-20260422 | locks | 0 | control | 42 | read 38, lock 4 |
| qwen3.6-27b-20260422 | locks | 1 | contended | 84 | read 50, lock 34 |
| qwen3.6-27b-20260422 | locks | 1 | control | 42 | read 25, lock 17 |
| qwen3.6-27b-20260422 | none | 0 | contended | 84 | read 84 |
| qwen3.6-27b-20260422 | none | 0 | control | 42 | read 42 |
| qwen3.6-27b-20260422 | none | 1 | contended | 84 | read 84 |
| qwen3.6-27b-20260422 | none | 1 | control | 42 | read 42 |

## Interleavings (contended episodes)

- claude-fable-5: 48 episodes; first mover {'a1': 28, 'a0': 20}; reads overlap 0.48; top patterns [('R1W1R0', 13), ('R0W0R1', 12), ('R1R0W1', 7), ('R0R1W0W1', 5), ('R0R1W1W0', 3)]
- claude-haiku-4-5-20251001: 224 episodes; first mover {'a1': 121, 'a0': 103}; reads overlap 0.83; top patterns [('R1R0W1W0', 47), ('R0R1W0W1', 42), ('R0R1W1W0', 32), ('R1R0W1', 27), ('R0W0R1', 20)]
- claude-sonnet-5: 224 episodes; first mover {'a1': 122, 'a0': 102}; reads overlap 0.83; top patterns [('R1R0W1W0', 41), ('R0R1W0W1', 39), ('R0R1W1W0', 34), ('R1R0W1', 31), ('R0R1W0', 20)]
- openrouter:google/gemini-4-argon-20261013: 336 episodes; first mover {'a1': 156, 'a0': 180}; reads overlap 0.40; top patterns [('R0W0R1', 106), ('R1W1R0', 68), ('R1R0W1', 32), ('R1R0W1W0', 28), ('R0W0R1W1', 22)]
- openrouter:openai/gpt-5.5-20260423: 96 episodes; first mover {'a1': 53, 'a0': 43}; reads overlap 0.47; top patterns [('R1W1R0', 29), ('R0W0R1', 22), ('R1R0W1', 8), ('R1R0W1W0', 8), ('R0R1W0W1', 7)]
- openrouter:qwen/qwen3.6-27b-20260422: 224 episodes; first mover {'a1': 118, 'a0': 106}; reads overlap 0.83; top patterns [('R1R0W1W0', 50), ('R0R1W0W1', 43), ('R0R1W1W0', 29), ('R1R0W1', 27), ('R0W0R1', 21)]

Episodes dropped because their matched partner is missing: 0

Recorded episode cost by provider family: {'anthropic': 16.46, 'gemini': 10.44, 'openrouter': 19.28}
