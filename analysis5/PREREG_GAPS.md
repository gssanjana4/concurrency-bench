# Pre-registration gaps: how each was closed

The 23 gaps found while implementing `analyze5.py` against the first draft of `paper-concurrency/PREREGISTRATION_STUDY2.md`. Each is now closed by registered text, and the code does what that text says. `GAP n` comments in `analyze5.py` mark the code. The section named is where the rule now sits in the registration.

| # | gap | resolution | registration section |
|---|---|---|---|
| 1 | Re-run rule: the harness never re-runs | No re-run. An episode or probe with an agent `truncated`/`provider_error`/`error` end, or a last completion `content_filter`/`refusal`, is excluded with its pair partner. Duplicate transcripts: the earliest is used. Counted per cell and arm. Sensitivity 9 scores these pairs against equivalence. | Data exclusion; Sensitivity 9 |
| 2 | 24-call re-score: indeterminate episodes | `score5.rescore_at_cap`, cap 24. Statuses unchanged / rescored / indeterminate, each defined. Indeterminate episodes are dropped with their partners, counted per cell and arm. | Sensitivity 1 |
| 3 | `cap_truncated`: text vs code | One definition, score5's: a `failed` episode with any agent ending `turn_cap`, fulfilled or not. It is a flag and an `outcome_stratum` value; `outcome` stays `failed`. | Measured variables |
| 4 | Plan vs text | Block table now has GPT probes K = 2, Fable no probes, Fable core 4 × 2 × 2 × 1 × 1 (2 families). Fable's probe-based items are reported as not run. | Study design; Sample size; Pre-specified descriptive |
| 5 | Bootstrap not reproducible | RNG key strings listed (`H1eq`, …; `qwen`, …, `pooled`; config labels; `|sens<k>`; `|signflip`; `|mc2`), draw procedure and interval index rule stated. | Bootstrap; Decision tests |
| 6 | Pooled tests with different cluster sets | Intersection of the pooled models' clusters; pooled cluster value = mean over models; one-sample tests on those values. | Pooled tests |
| 7 | Pooled tests in the -diff families | Yes: H1-diff has up to 12 members, H4-diff up to 8. | Holm families and gatekeeping |
| 8 | Reading when both reject | Claim table with four rows, including "added failures, by less than δ". | H1, Reading per cell |
| 9 | Calibration scope | Each confirmatory model and pooled, raw α, no eligibility rule, same margins. A failed calibration makes that model's H1 equivalences uninformative. | H1, Calibration |
| 10 | Minimum-cluster rule for probe tests | 75 % of registered units: clusters, or (family, instance) probe units; both configs for two-config tests. | Missing data |
| 11 | Leakage check method | Sign-flip, two-sided, on (config, aware, family, instance) units under `locks` and `all_available`; a rejection changes how H4 is described. | Check 1 |
| 12 | Exposure for the H4 gate | Replaced by the informativeness gate q (exposed and not protected before the first signal), per cell and pooled. | H4, Informativeness gate |
| 13 | H4b definitions | At risk: exposed, `protect_before_contention` not True. Reacting: first primitive after the signal. Clusters with no agent at risk dropped. | H4 |
| 14 | Eligibility denominator and 75 % rule | Over agents; `lock`/`cas` tokens; excluded probes leave the denominator; listed codes count as no primitive; 75 % of registered probes; fixed for all sensitivities. Eligibility now applies to H4 only. | Common definitions |
| 15 | H2 pairing | Unit (family, instance, schedule, arm) with both configs; episode value = share of agents; cluster value = mean over units. | H2 |
| 16 | H3 units | A unit needs on/off pairs in both configs; per-config estimates use the units with that config. | H3 |
| 17 | Sign fallback for two-sided and TOST tests | The fallback is gone. θ0 = 0 tests are exact sign-flip tests; TOST sides are bootstrap-t, with the sign test only when SE = 0, per side. | Decision tests |
| 18 | Sensitivity 4 field | `model_served` per completion (Gemini: `modelVersion`); majority over rows; rows served entirely by the majority kept; mixed pairs counted. | Sensitivity 4 |
| 19 | Extension blocks | H-statistics use core and probe blocks only; extension rows are counted and reported separately. | Pre-specified descriptive; Data exclusion |
| 20 | Sensitivity 6 | Holm across all per-model tests of H1-eq, H1-diff, H2, H3, H4-eq, H4-diff within each model, no gatekeeping; pooled tests left out. The unregistered H1-to-H3 variant was removed from the code. | Sensitivity 6 |
| 21 | Sensitivity 7 | Family means; TOST: t-test (df 6) at ±δ; θ0 = 0: exact sign-flip over 128 assignments. | Sensitivity 7 |
| 22 | Sensitivity 3 | Same selection, no episode or partner excluded. | Sensitivity 3 |
| 23 | Scope of `analyze5.py` | Confirmatory tests, claims, checks, H4b, budget report, sensitivities 1 to 9. Descriptive tables, the cross-model model and exploratory analyses come from a separate script and support no confirmatory claim. | Analysis code |

## Changes made with the T3b review

- Decision tests: exact sign-flip for θ0 = 0; bootstrap-t for TOST sides, with SE*_b = 0 replaced by the observed SE (T3b proposed ±∞, which capped power near 0.5 when failures are rare; see `power_sims/variants_out.json`).
- Margins: δ = 0.25 per (model, config), 0.15 pooled, for H1 and H4 (were 0.20 / 0.10; the pooled 0.10 cannot be reached at the planned n).
- Two-stage Holm (serial gatekeeping) for H1-eq and H4-eq.
- Claim table, headline claims, H1 calibration gate, H4 q gate, sensitivity 9 and its rule.
- Budget: `balance5.py` logs the shared OpenRouter key; `analyze5.balance_report` computes spend by others and flags external stops.
