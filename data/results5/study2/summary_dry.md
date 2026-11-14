| model | n | config | aware | arm | eps | clean | comp. | failed | top failed labels | fs | dsg | basis dsg | ever viol. | lock att/gr/eff | cas | promote | msg | fulfilled | cap ends | deadlocks | agent errors | ctrl w/ msg | exposure | cap-trunc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## First-reply probes (one completion per agent; codes from model_agent5.first_reply_code)

| model | config | aware | arm | probes | first-reply codes |
|---|---|---|---|---|---|
| gemini-4-argon-20261013 | all_available | 0 | contended | 112 | lock 112 |
| gemini-4-argon-20261013 | all_available | 0 | control | 56 | lock 56 |
| gemini-4-argon-20261013 | all_available | 1 | contended | 112 | lock 112 |
| gemini-4-argon-20261013 | all_available | 1 | control | 56 | lock 56 |
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
| gemini-4-argon-20261013 | none | 1 | contended | 112 | read 112 |
| gemini-4-argon-20261013 | none | 1 | control | 56 | read 56 |
| gpt-5.5-20260423 | all_available | 0 | contended | 28 | lock 28 |
| gpt-5.5-20260423 | all_available | 0 | control | 14 | lock 14 |
| gpt-5.5-20260423 | all_available | 1 | contended | 28 | lock 28 |
| gpt-5.5-20260423 | all_available | 1 | control | 14 | lock 14 |
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
| qwen3.6-27b-20260422 | all_available | 0 | contended | 84 | lock 84 |
| qwen3.6-27b-20260422 | all_available | 0 | control | 42 | lock 42 |
| qwen3.6-27b-20260422 | all_available | 1 | contended | 84 | lock 84 |
| qwen3.6-27b-20260422 | all_available | 1 | control | 42 | lock 42 |
| qwen3.6-27b-20260422 | cas_available | 0 | contended | 84 | read 84 |
| qwen3.6-27b-20260422 | cas_available | 0 | control | 42 | read 42 |
| qwen3.6-27b-20260422 | cas_available | 1 | contended | 84 | read 84 |
| qwen3.6-27b-20260422 | cas_available | 1 | control | 42 | read 42 |
| qwen3.6-27b-20260422 | locks | 0 | contended | 84 | lock 84 |
| qwen3.6-27b-20260422 | locks | 0 | control | 42 | lock 42 |
| qwen3.6-27b-20260422 | locks | 1 | contended | 84 | lock 84 |
| qwen3.6-27b-20260422 | locks | 1 | control | 42 | lock 42 |
| qwen3.6-27b-20260422 | none | 0 | contended | 84 | read 84 |
| qwen3.6-27b-20260422 | none | 0 | control | 42 | read 42 |
| qwen3.6-27b-20260422 | none | 1 | contended | 84 | read 84 |
| qwen3.6-27b-20260422 | none | 1 | control | 42 | read 42 |

## Interleavings (contended episodes)


Episodes dropped because their matched partner is missing: 0

Recorded episode cost by provider family: {'gemini': 1.33, 'openrouter': 1.32}
