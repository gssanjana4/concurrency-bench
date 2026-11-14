# CONFIRMATORY tests (pre-registered)

Cluster bootstrap over task instances, B = 10000, seed 20261031; one-sided; exact sign test when the bootstrap is degenerate; Holm within each hypothesis over tested models; alpha = 0.05. Truncated episodes excluded: False (0).

## H1: proportion of episodes non_serializable (config none, n = 2, aware off)

Decision rule: supported iff all registered models reject after Holm. **Verdict: supported.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| claude-haiku-4-5-20251001 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| openrouter:google/gemini-4-argon-20261013 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| claude-sonnet-5 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| claude-fable-5 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |

## H2: proportion of agents with a successful acquire_lock (config locks, n = 2, aware off)

Decision rule: supported iff at least 4 of 6 models reject after Holm. **Verdict: not supported.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 28/28 | 0 | 0.125 | [0.054, 0.205] | 0.0029 | bootstrap | 0.0145 | yes |
| claude-haiku-4-5-20251001 | tested | 28/28 | 0 | 0.009 | [0.000, 0.027] | 0.0001 | bootstrap | 0.0006 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 28/28 | 0 | 0.938 | [0.884, 0.982] | 1.0000 | bootstrap | 1.0000 | no |
| openrouter:google/gemini-4-argon-20261013 | tested | 28/28 | 0 | 0.884 | [0.804, 0.955] | 1.0000 | bootstrap | 1.0000 | no |
| claude-sonnet-5 | tested | 28/28 | 0 | 0.634 | [0.473, 0.786] | 1.0000 | bootstrap | 1.0000 | no |
| claude-fable-5 | tested | 28/28 | 0 | 0.920 | [0.821, 0.991] | 1.0000 | bootstrap | 1.0000 | no |

## H3: agent rate of the offered option (lock | locks, message | messages), aware on - off

Decision rule: report which models reject after Holm; no claim about the others. **Verdict: reported per model (no overall claim).** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 28/28 | 0 | 0.263 | [0.192, 0.335] | 0.0001 | bootstrap | 0.0006 | yes |
| claude-haiku-4-5-20251001 | tested | 28/28 | 0 | 0.174 | [0.103, 0.250] | 0.0001 | bootstrap | 0.0006 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 28/28 | 0 | 0.031 | [-0.009, 0.071] | 0.0656 | bootstrap | 0.0656 | no |
| openrouter:google/gemini-4-argon-20261013 | tested | 28/28 | 0 | 0.049 | [0.009, 0.094] | 0.0107 | bootstrap | 0.0214 | yes |
| claude-sonnet-5 | tested | 28/28 | 0 | 0.161 | [0.107, 0.219] | 0.0001 | bootstrap | 0.0006 | yes |
| claude-fable-5 | tested | 28/28 | 0 | 0.071 | [0.022, 0.129] | 0.0005 | bootstrap | 0.0015 | yes |

## H4a: primary-label stale_overwrite rate, none - cas_available (n = 2, aware off)

Decision rule: supported for each model that rejects after Holm. **Verdict: supported for 6 of 6 models.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| claude-haiku-4-5-20251001 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| openrouter:google/gemini-4-argon-20261013 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| claude-sonnet-5 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| claude-fable-5 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |

## H4b: (i) write_skew rate under cas_available > 0.50; (ii) drop none - cas_available < 0.25

Decision rule: supported for each model that rejects after Holm. **Verdict: supported for 3 of 6 models.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 8/8 | 0 | (i) 1.000; (ii) 0.000 | (i) [1.000, 1.000]; (ii) [0.000, 0.000] | 0.0039 | (i) sign_test; (ii) sign_test | 0.0234 | yes |
| claude-haiku-4-5-20251001 | tested | 8/8 | 0 | (i) 1.000; (ii) 0.000 | (i) [1.000, 1.000]; (ii) [0.000, 0.000] | 0.0039 | (i) sign_test; (ii) sign_test | 0.0234 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 8/8 | 0 | (i) 0.438; (ii) 0.062 | (i) [0.188, 0.688]; (ii) [-0.312, 0.375] | 0.7540 | (i) bootstrap; (ii) bootstrap | 1.0000 | no |
| openrouter:google/gemini-4-argon-20261013 | tested | 8/8 | 0 | (i) 0.062; (ii) -0.062 | (i) [0.000, 0.188]; (ii) [-0.188, 0.000] | 1.0000 | (i) bootstrap; (ii) bootstrap | 1.0000 | no |
| claude-sonnet-5 | tested | 8/8 | 0 | (i) 1.000; (ii) 0.000 | (i) [1.000, 1.000]; (ii) [0.000, 0.000] | 0.0039 | (i) sign_test; (ii) sign_test | 0.0234 | yes |
| claude-fable-5 | tested | 8/8 | 0 | (i) 0.000; (ii) 0.562 | (i) [0.000, 0.000]; (ii) [0.250, 0.875] | 1.0000 | (i) sign_test; (ii) bootstrap | 1.0000 | no |

## H6: OLS slope of non_serializable (0/1) on log2(n), n = 2, 4, 8 (cas_available, aware off, seed 0)

Decision rule: supported for each model that rejects after Holm. **Verdict: supported for 0 of 6 models.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 14/14 | 0 | 0.036 | [0.000, 0.107] | 0.3513 | bootstrap | 1.0000 | no |
| claude-haiku-4-5-20251001 | tested | 14/14 | 0 | 0.000 | [0.000, 0.000] | 1.0000 | sign_test | 1.0000 | no |
| openrouter:openai/gpt-5.5-20260423 | tested | 14/14 | 0 | 0.036 | [0.000, 0.107] | 0.3537 | bootstrap | 1.0000 | no |
| openrouter:google/gemini-4-argon-20261013 | tested | 14/14 | 0 | -0.036 | [-0.107, 0.000] | 1.0000 | bootstrap | 1.0000 | no |
| claude-sonnet-5 | tested | 14/14 | 0 | 0.000 | [0.000, 0.000] | 1.0000 | sign_test | 1.0000 | no |
| claude-fable-5 | tested | 14/14 | 0 | 0.000 | [0.000, 0.000] | 1.0000 | sign_test | 1.0000 | no |

## H5 (pre-specified descriptive): partial actions after a concurrency rejection

| model | partial / eligible agents | rate | 95% Wilson CI |
|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | 29 / 37 | 0.78 | [0.63, 0.89] |
| claude-haiku-4-5-20251001 | 32 / 32 | 1.00 | [0.89, 1.00] |
| openrouter:openai/gpt-5.5-20260423 | 1 / 33 | 0.03 | [0.01, 0.15] |
| openrouter:google/gemini-4-argon-20261013 | 1 / 32 | 0.03 | [0.01, 0.16] |
| claude-sonnet-5 | 31 / 37 | 0.84 | [0.69, 0.92] |
| claude-fable-5 | 5 / 37 | 0.14 | [0.06, 0.28] |

Models with at least one: 6 (outcome met before audit: True). pre-specified outcome: >= 1 such agent, confirmed by transcript audit, in >= 3 of 6 models; counts here are before the manual audit.

# Sensitivity: confirmatory tests excluding episodes with a truncated agent

Cluster bootstrap over task instances, B = 10000, seed 20261031; one-sided; exact sign test when the bootstrap is degenerate; Holm within each hypothesis over tested models; alpha = 0.05. Truncated episodes excluded: True (5).

## H1: proportion of episodes non_serializable (config none, n = 2, aware off)

Decision rule: supported iff all registered models reject after Holm. **Verdict: supported.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| claude-haiku-4-5-20251001 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| openrouter:google/gemini-4-argon-20261013 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| claude-sonnet-5 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |
| claude-fable-5 | tested | 28/28 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0000 | yes |

## H2: proportion of agents with a successful acquire_lock (config locks, n = 2, aware off)

Decision rule: supported iff at least 4 of 6 models reject after Holm. **Verdict: not supported.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 28/28 | 0 | 0.125 | [0.054, 0.205] | 0.0029 | bootstrap | 0.0145 | yes |
| claude-haiku-4-5-20251001 | tested | 28/28 | 0 | 0.009 | [0.000, 0.027] | 0.0001 | bootstrap | 0.0006 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 28/28 | 0 | 0.938 | [0.884, 0.982] | 1.0000 | bootstrap | 1.0000 | no |
| openrouter:google/gemini-4-argon-20261013 | tested | 28/28 | 0 | 0.884 | [0.804, 0.955] | 1.0000 | bootstrap | 1.0000 | no |
| claude-sonnet-5 | tested | 28/28 | 0 | 0.634 | [0.473, 0.786] | 1.0000 | bootstrap | 1.0000 | no |
| claude-fable-5 | tested | 28/28 | 0 | 0.920 | [0.821, 0.991] | 1.0000 | bootstrap | 1.0000 | no |

## H3: agent rate of the offered option (lock | locks, message | messages), aware on - off

Decision rule: report which models reject after Holm; no claim about the others. **Verdict: reported per model (no overall claim).** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 26/28 | 2 | 0.250 | [0.178, 0.327] | 0.0001 | bootstrap | 0.0006 | yes |
| claude-haiku-4-5-20251001 | tested | 28/28 | 0 | 0.174 | [0.103, 0.250] | 0.0001 | bootstrap | 0.0006 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 28/28 | 0 | 0.031 | [-0.009, 0.071] | 0.0656 | bootstrap | 0.0656 | no |
| openrouter:google/gemini-4-argon-20261013 | tested | 28/28 | 0 | 0.049 | [0.009, 0.094] | 0.0107 | bootstrap | 0.0214 | yes |
| claude-sonnet-5 | tested | 28/28 | 0 | 0.161 | [0.107, 0.219] | 0.0001 | bootstrap | 0.0006 | yes |
| claude-fable-5 | tested | 28/28 | 0 | 0.071 | [0.022, 0.129] | 0.0005 | bootstrap | 0.0015 | yes |

## H4a: primary-label stale_overwrite rate, none - cas_available (n = 2, aware off)

Decision rule: supported for each model that rejects after Holm. **Verdict: supported for 6 of 6 models.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| claude-haiku-4-5-20251001 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| openrouter:google/gemini-4-argon-20261013 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| claude-sonnet-5 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |
| claude-fable-5 | tested | 16/16 | 0 | 1.000 | [1.000, 1.000] | 0.0000 | sign_test | 0.0001 | yes |

## H4b: (i) write_skew rate under cas_available > 0.50; (ii) drop none - cas_available < 0.25

Decision rule: supported for each model that rejects after Holm. **Verdict: supported for 3 of 6 models.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 8/8 | 0 | (i) 1.000; (ii) 0.000 | (i) [1.000, 1.000]; (ii) [0.000, 0.000] | 0.0039 | (i) sign_test; (ii) sign_test | 0.0234 | yes |
| claude-haiku-4-5-20251001 | tested | 8/8 | 0 | (i) 1.000; (ii) 0.000 | (i) [1.000, 1.000]; (ii) [0.000, 0.000] | 0.0039 | (i) sign_test; (ii) sign_test | 0.0234 | yes |
| openrouter:openai/gpt-5.5-20260423 | tested | 8/8 | 0 | (i) 0.438; (ii) 0.062 | (i) [0.188, 0.688]; (ii) [-0.312, 0.375] | 0.7540 | (i) bootstrap; (ii) bootstrap | 1.0000 | no |
| openrouter:google/gemini-4-argon-20261013 | tested | 8/8 | 0 | (i) 0.062; (ii) -0.062 | (i) [0.000, 0.188]; (ii) [-0.188, 0.000] | 1.0000 | (i) bootstrap; (ii) bootstrap | 1.0000 | no |
| claude-sonnet-5 | tested | 8/8 | 0 | (i) 1.000; (ii) 0.000 | (i) [1.000, 1.000]; (ii) [0.000, 0.000] | 0.0039 | (i) sign_test; (ii) sign_test | 0.0234 | yes |
| claude-fable-5 | tested | 8/8 | 0 | (i) 0.000; (ii) 0.562 | (i) [0.000, 0.000]; (ii) [0.250, 0.875] | 1.0000 | (i) sign_test; (ii) bootstrap | 1.0000 | no |

## H6: OLS slope of non_serializable (0/1) on log2(n), n = 2, 4, 8 (cas_available, aware off, seed 0)

Decision rule: supported for each model that rejects after Holm. **Verdict: supported for 0 of 6 models.** Holm family size: 6. Not tested: none.

| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |
|---|---|---|---|---|---|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | tested | 13/14 | 1 | 0.038 | [0.000, 0.115] | 0.3503 | bootstrap | 1.0000 | no |
| claude-haiku-4-5-20251001 | tested | 14/14 | 0 | 0.000 | [0.000, 0.000] | 1.0000 | sign_test | 1.0000 | no |
| openrouter:openai/gpt-5.5-20260423 | tested | 14/14 | 0 | 0.036 | [0.000, 0.107] | 0.3537 | bootstrap | 1.0000 | no |
| openrouter:google/gemini-4-argon-20261013 | tested | 14/14 | 0 | -0.036 | [-0.107, 0.000] | 1.0000 | bootstrap | 1.0000 | no |
| claude-sonnet-5 | tested | 14/14 | 0 | 0.000 | [0.000, 0.000] | 1.0000 | sign_test | 1.0000 | no |
| claude-fable-5 | tested | 14/14 | 0 | 0.000 | [0.000, 0.000] | 1.0000 | sign_test | 1.0000 | no |

## H5 (pre-specified descriptive): partial actions after a concurrency rejection

| model | partial / eligible agents | rate | 95% Wilson CI |
|---|---|---|---|
| openrouter:qwen/qwen3.6-27b-20260422 | 29 / 37 | 0.78 | [0.63, 0.89] |
| claude-haiku-4-5-20251001 | 32 / 32 | 1.00 | [0.89, 1.00] |
| openrouter:openai/gpt-5.5-20260423 | 1 / 33 | 0.03 | [0.01, 0.15] |
| openrouter:google/gemini-4-argon-20261013 | 1 / 32 | 0.03 | [0.01, 0.16] |
| claude-sonnet-5 | 31 / 37 | 0.84 | [0.69, 0.92] |
| claude-fable-5 | 5 / 37 | 0.14 | [0.06, 0.28] |

Models with at least one: 6 (outcome met before audit: True). pre-specified outcome: >= 1 such agent, confirmed by transcript audit, in >= 3 of 6 models; counts here are before the manual audit.
