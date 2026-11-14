# Paper pipeline: "Do LLM Agents Coordinate on Shared Records?"

This folder holds structure, generated numbers, tables, figures and fact sheets. AI use is stated in the paper's Acknowledgments and, for the code, in the "AI use" section of the artifact README.

**Two studies, two documents, two builds (2026-11-10).** The paper reports Study 1 (the registered run on `src4`, summarised in §4) and Study 2 (the corrected harness `src5`, registered on the OSF on 2026-11-09 and embargoed until 2027-11-01; section 5, `study2.tex`). Since the 12-page cut of 2026-11-10 there are two documents from one source:

- **the paper** (`main.tex`): a 12-page main text (through the Acknowledgments) and a 15-page appendix: the Study 2 registration and complete deviations table, the worked verdict, the prompts and tool texts (`study2_prompts.tex`), the Study 2 tables the main text cites, the Study 1 verdict table and the reproducibility record;
- **the supplement** (`supplement.tex` -> `build/supplement_<mode>.pdf`): the Study 2 registered analysis in full (`study2_analysis.tex`), every registered test and every per-family, per-cell, mechanism and Firth table, three Study 2 figures, Study 1 in full (`study1_full.tex`, `supp_study1.tex`: configs, templates, scoring rules and glossary, deviations, full and exploratory results, the H5 audit), the database foundations and the SQL slice (`supp_db_sql.tex`), and the v10 text of the five shortened sections (`supp_extended.tex`).

Both input `preamble_shared.tex` (packages, macro files, identity text, constants, names, the cross-document macros); `study2_constants.tex` (input there) holds the Study 2 fixed constants and the registration record. The supplement prefixes its labels with `s` and numbers everything S1, S2, ...; each document reads the other's `.aux` through `xr-hyper`, and the paper cites "Supplement §S5, Table S12" with `\SuppSec{...}`/`\SuppTab{...}`. A reference that resolves in neither document fails the build. The source builds in two modes:

```
bash build.sh                # all three builds of both documents: build/{main,supplement}_{preprint,anonymous,tmlr}.pdf
                             # (main.pdf and supplement.pdf = the preprint)
bash build.sh --preprint     # named: author line and OSF identifiers from identity.tex, no line numbers
bash build.sh --anonymous    # "Anonymous authors", "[registration link withheld]", the concurrent paper as
                             # "Anonymous. Concurrent submission." (refs_build.bib), no line numbers
bash build.sh --tmlr         # the anonymous content in the official TMLR style (tmlr/tmlr.sty, tmlr/tmlr.bst, pinned
                             # in tmlr/PIN.md; tmlr_setup.tex); anonymous as TMLR requires; supplement as its own PDF
```

The TMLR build (2026-11-14, review F1 M4) sets `\BuildTMLR` 1 (with `\BuildAnonymous` 1) in `buildmode.tex`; `main.tex` and `supplement.tex` then use `\documentclass[10pt]` and input `tmlr_setup.tex` instead of `\usepackage[preprint]{acl}`. The text is identical; two layout-only macros differ (`\ColFigWidth`, the width of the one-column figures, and `\DeviationTableFont`, which sets the two deviations tables in Times so that each page-sized part still fits), and the font is tmlr.sty's Latin Modern. The anonymity scan runs on the TMLR PDFs as on the anonymous ones.

`build.sh` writes `buildmode.tex` (`\BuildAnonymous` 0 or 1) and `refs_build.bib` before each pdflatex run; `identity.tex` is the only file that carries the author's name and the registration identifiers, and it is never copied into the anonymized artifacts (the anonymizer tests fail on an identity string anywhere else). The anonymous build is checked for every identity string taken from `identity.tex`. Both builds of both documents must compile with no undefined reference, no undefined control sequence, no overfull box and no LaTeX warning of any kind, which `build.sh` enforces (`build/pages_<mode>.txt` reports the page counts of the paper's main text, its appendix and the supplement); the anonymous build scans both PDFs for the identity strings.

Study 2 numbers come from three macro files and nowhere else:

| file | prefix | made by | what |
|---|---|---|---|
| `study2_out/study2_registered_numbers.tex` | `\Sii...` | frozen `analysis5/analyze5.py` (sha256 `99dff56a…`); a verbatim copy of `analysis5/out_study2/numbers.tex` (sha256 `a70c6f84…`), refreshed and hash-checked by `build.sh` step 1e against the value recorded in `study2_numbers.tex` | every registered estimate, interval, p, claim word, eligibility rate, leakage statistic, check and sensitivity count |
| `study2_out/study2_numbers.tex` | `\SiiD...` | `analysis5/descriptives5.py` (read-only on the data; also writes `study2_out/tables/*.tex`, `study2_out/figures/*`, `study2_deviations.csv`, `facts/src/study2_results_facts.md`) | pre-specified descriptive rates per arm, counts, spend; since 2026-11-10 every post hoc mechanism count (lock-failure mechanisms, protocol order, lock scope, missing-leg codes, endings after a 409, success reports without a write, read overlap by task class, write-skew protocols, serial reachability, the worked example), the table of all 114 registered tests, the Firth cross-model regression (standard library; wild cluster bootstrap) and the complete deviations table; each table caption states the rule behind its counts |
| `study2_constants.tex` | `\Sii...` (design), `\SiiSha...`, `\SiiReg...`, `\SiiV...` | hand-written | registration constants (`facts/src/study2_methods_facts.md`), the sha256 of the frozen analysis and its outputs, the registration record, and the three remaining counts of the AI-assisted verification `review/V3_results_verification.md` (labels read, scripted episodes and families) |

`study2_factpass.py` (build.sh step 6) writes `facts/src/study2_results_crosscheck.md`: every Study 2 claim sentence of the paper (`main.tex`, `study2.tex`, `study2_prompts.tex`) and the supplement (`supplement.tex`, `study2_analysis.tex`, `study1_full.tex`, `supp_*.tex`) with its macros and sources; every registered macro is recomputed from `results.json` (95 on 2026-11-10, 0 mismatches) and the build fails on a mismatch or an undefined macro. `study2_lint.py` (step 2b) forbids typed digits in the prose of `study2.tex`, `study1_full.tex`, `study2_analysis.tex` and the `supp_*.tex` files and undefined `\Sii...`/`\SH...` macros anywhere; `make_numbers4.py --check` lints `main.tex` and `supplement.tex`. The generated files must never be edited by hand; rerun `descriptives5.py` (`bash build.sh --descriptives`) to regenerate the descriptive ones, and never edit `analysis5/analyze5.py`, `src5/` or the data.

## Rebuild once real data lands

Real runs write `results4/full/phase{1,2,3}/results.csv` (no `dry_run/` component), with transcripts and `failures.jsonl` next to each CSV.

```
cd paper-concurrency/latex
bash build.sh               # real data -> ../analysis -> numbers.tex, tables, figures, facts, both PDFs
bash build.sh --dry-run     # fake-model dry run -> ../analysis_dry (watermarked "DRY RUN DATA")
bash build.sh --no-analysis # reuse the analysis dir after editing the .tex files only
bash build.sh --descriptives  # also rerun analysis5/descriptives5.py (Study 2 tables, figures, post hoc counts)
```

`build.sh` runs these steps:
1. `run_analysis.py`: verifies the src4 FREEZE hashes, then runs the frozen `src4/analyze4.py` unchanged. It also writes `provenance.json` (input hashes and the dry-run flag).
1b. `explore4.py`: EXPLORATORY analyses from the saved CSVs and transcripts (no model calls): E1 goodput, E3 CAS form-filling, E4 response after a rejection, E5 write-skew preventability, E6 per-template and leave-one-template-out, E7 lock quality, E8 turn cap and truncation, E10 competence proxy. Writes only `<analysis>/exploratory_posthoc.json` and refuses to write any analyze4/run_analysis output. Definitions: its docstring.
1d. `posthoc_review.py` and `reference_policies.py`: POST HOC analyses added after the 2026-11-02 reviews (template-level bootstrap, exact bounds, control-template choice use, store-based fulfilment, lease-expiry split, same-reply shares, serving facts, SQL-slice counts; the frozen scripted agents under the registered schedule). Write only `<analysis>/posthoc_review.json` and `<analysis>/reference_policies.json` (`\Tpl...`, `\Exact...`, `\Use...`, `\StoreFulfil...`, `\Lease...`, `\SameReply...`, `\Ref...`, `\Sql...` macros). Its `review2` block and the seed-invariance and scripted-promoter blocks of `reference_policies.py` were added after the 2026-11-03 reviews (`review/T1`-`T4`; `\Rev...` macros and `\Tpl...Sign...`): sign-test Holm, exact template-level tests, H6 detectable effect, graph agreement, stale overwrites by config, 409 version leak, partial-action mechanisms, write skew at any point, first-reply locks, schedule overlap, turn-cap endings, Qwen lock use by host, Gemini settings, orchestrator hashes.
1c. `rollback_sensitivity.py`: POST HOC sensitivity (not pre-registered). Rescores rollback-only `partial_action` episodes (no invariant violation, a committed agent whose writes net to zero, final store reproduced by a serial order of the other agents) as serializable and reruns the frozen `analyze4.confirmatory` on the relabelled rows; H1 and H6 can move, H4a/H4b cannot. Also carries the per-model counts of the H5 transcript audit (`../audit/H5_AUDIT.csv`). Writes only `<analysis>/rollback_sensitivity.json` (`\Rb...`, `\HfiveAudit...` macros; `tab:rollback`, `tab:h5-audit`).
1e. Study 2 registered macros: copies `analysis5/out_study2/numbers.tex` (path `STUDY2_NUMBERS`, default `$HOME/study2_data/analysis5/out_study2/numbers.tex`) to `study2_out/study2_registered_numbers.tex` when the source is present and fails if the copy's sha256 differs from the one `descriptives5.py` recorded in `study2_out/study2_numbers.tex`.
2. `make_numbers4.py --check`: writes `numbers.tex`, `numbers_report.txt`, `tables/*.tex`, `build/figdata.json` and `facts/*.md`, then lints `main.tex` (literal digits and undefined generated macros).
2b. `study2_lint.py`: the same digit rule for `study2.tex`, `study1_full.tex` and `study2_analysis.tex`; undefined `\Sii...`/`\SH...` macros in any section file; no "[author: ...]" cell in a generated Study 2 table.
3. `figures/make_figs.py`: builds the Study 1 vector PDFs from `build/figdata.json` (the Study 2 figures come from `descriptives5.py`).
4. One LaTeX build per mode of both documents, in alternation so that each reads the other's labels (`pdflatex` main and supplement, `bibtex` both, then two more rounds and a final pass of each) after writing `buildmode.tex` and `refs_build.bib`; `build/main_<mode>.pdf`, `build/supplement_<mode>.pdf` and their logs.
5. Checks per mode over both documents: undefined refs and control sequences, overfull boxes and any other LaTeX warning (each fails the build), PENDING values, the watermark (present for dry runs, absent for real runs), the page counts (`build/pages_<mode>.txt`: main text through the Acknowledgments, appendix, supplement), and for the anonymous build every identity string from `identity.tex` in both PDFs.
6. `study2_factpass.py` (fails on a mismatch), `check_hashes.py` (every sha256 printed in the paper and the supplement against the file it names) and the unit tests (`tests/`).

`page_budget.py` (not run by build.sh) measures the prose capacity of an 8-page main text; it is a leftover of the ACL format and reports OVER for this paper.

Paths can be overridden with `SRC4=...` and `RESULTS4=...` (defaults: `../../src4`, `../../results4/full`). Explicit CSVs also work: `python3 run_analysis.py a.csv b.csv --out DIR`.

After real data lands:
- Check `numbers_report.txt` → "warnings". It lists any registered cell with fewer episodes than planned, cross-check failures, and PENDING values.
- Fill `deviations.csv` (columns `deviation,reason,before_after,effect,registered_result`). It renders as the deviations table; `make_numbers4.py` splits it into page-sized parts ("part k of m" captions, the label on part 1) once the estimated height passes one page, since a single float taller than the page is clipped without an error.
- Read `facts/*.md` again. The values change and the macro names stay the same.

## Rules
- **No typed result numbers.** `main.tex` prints values only through macros from `numbers.tex`. `make_numbers4.py --check` fails on literal digits in the body (it ignores citations, labels, refs, input paths, lengths and hypothesis names like H4a) and on undefined generated macros.
- Generated tables use macros too, so `numbers.tex` is the single source.
- Confirmatory numbers come only from the `\H...` macros (`confirmatory.json`). `\X...` (cell rates), `\Cmp...` (permutation comparisons) and `\Raw...` (CSV counts) and `\Expl...` (explore4.py) are EXPLORATORY.
- Do not edit `numbers.tex`, `tables/`, `facts/*.md` or the figures by hand. Edit `facts/src/*.md` (with `{{Macro}}` tokens), `make_numbers4.py` or `figures/make_figs.py`.
- Never modify `src4/`. Every script refuses to run if a FREEZE hash differs.
- Study 2: every number in `study2.tex`, `study2_analysis.tex` and the Study 2 passages of `main.tex` is a `\Sii...`, `\SiiD...` or `study2_constants.tex` macro; the registered claim wording (PREREGISTRATION_STUDY2.md, claims-per-outcome table) governs every registered result, and a non-rejection is written as "did not reject"; pre-specified descriptive numbers carry the inline tag "descriptive", registered-exploratory ones "exploratory", everything else "post hoc". Post hoc counts come from `descriptives5.py` under rules stated in the table captions, never from a review or verification text. Four readings the prose must keep (verification V3, reviews T5 to T8): the CAS-config differences come from the constraint-spanning families (write skew and transfer) and no single-record episode failed under either CAS config; the `locks` failures have three mechanisms (read then lock, a lock on the written record only, no lock) on a lock whose waited acquire differs from an immediate grant only in the token value; the same-amount instances explain the decision not to repair most half-done transfers, which came from both legs sent in one reply; the measure is committed-intent serializability and does not score the agent's report.
- The in-pipeline reviews (R1 to R3, T1 to T8, V1 to V2b, T3b, T3c) and the verification (V3) are AI-generated; the paper says so at every mention (`\AIreviews`, `\AIverification`) and never calls them peer review. The AI assistant is a product of Anthropic, provider of three evaluated models (artifact README, "AI use").
- Study 1 and Study 2 lock-use levels are text-dependent and are never compared as rates across studies (registration).

## Macro names (letters only)
| kind | pattern | example |
|---|---|---|
| confirmatory | `\H<one,two,three,fourA,fourB,six><Model><Field>` | `\HoneHaikuRate`, `\HoneHaikuVerdict`, `\HfourBGPTEstII`, `\HsixFablePHolm` |
| per hypothesis | `\H<..>Verdict`, `FamilySize`, `NReject`, `NNotTested` | `\HtwoVerdict` |
| H5 | `\Hfive<Model><K,N,Rate,CI>` | `\HfiveSonnetK` |
| sensitivity | `\Sens<H..><Model><..>`, `\SensTruncatedExcluded` | `\SensHoneVerdict` |
| cell rates | `\X<Metric><Config><Model><Off,On><Two,Four,Eight><Est,CI,Num,Den,Inst>` | `\XNonserCasAvailHaikuOffTwoEst` |
| comparisons | `\CmpCfg<Metric><Config><Model><Off,On><N><Diff,P,PHolm,Inst>`, `\CmpAware<Metric><Config><Model><N><..>` | `\CmpAwareCasCasAvailHaikuTwoDiff` |
| design | `\Des...` (from frozen code), `\Pilot...`, `\Plan...` (from the prereg, checked by exact substring) | `\DesGap`, `\PilotSpendUSD` |
| observed | `\Excl...`, `\Obs...`, `\Cost<Model>USD`, `\Served<Model>`, `\Raw...` | `\ObsNAnalyzed` |
| exploratory E (explore4.py) | `\Expl<Fulfil,Giveup,Clean,Complete><Config><Model><Off,On><Est,CI,Num,Den>`, `\ExplPost<Code>...`, `\ExplWs...`, `\ExplTpl...`, `\ExplLoto...`, `\ExplLock...`, `\ExplTurnCap...`, `\ExplTrunc...`, `\ExplCtlFulfil...` | `\ExplFulfilCasAvailHaikuOffEst` |
| post hoc, second review round | `\Rev...` (posthoc_review.py review2; reference_policies.py seed invariance and promoter), `\Tpl<H><Model>PSignflipHolm`, `\ExactTplBound` | `\RevFirstLockGPTK`, `\RevWsEverFable`, `\RevHsixKAlpha` |

Models: Qwen, Haiku, GPT, Gemini, Sonnet, Fable. Configs: None, Reread, CasAvail, CasReq, Locks, Messages. Metrics: Nonser, Stale, Partial, Skew, Inv, Reread, Cas, Lock, Msg, NoCoord, Giveup, Abandon.

## Things to know about analyze4's outputs (wrapped here, not changed)
- analyze4 drops every `dry_run = 1` row. On the dry-run CSVs it therefore analyses 0 episodes and marks every hypothesis "not tested". To exercise the pipeline, `run_analysis.py` copies the dry-run CSVs with `dry_run` set to 0 into `<out>/_staged_dryrun/`, symlinks the transcripts, and marks everything as DRY RUN. It does this only when the inputs are dry-run.
- When no model is tested, the verdict string still reads "not supported" for H1/H2, following the rule. The macro prints it verbatim. `\H..NNotTested` and the report warning give the reason.
- H4b has no top-level estimate (`estimate: null`). The two parts are in `component_i` and `component_ii`, so the macros are `EstI`, `EstII` and so on.
- Verdicts are free-text strings ("supported for 6 of 6 models"). Per-model macros are derived from the structured `reject` and `status` fields.
- `numbers.json` repeats the whole confirmatory block. make_numbers4 reads `confirmatory.json` and checks that both carry the frozen analyze4 hash.
- Cell rates cover the whole cell (every instance and seed). H6's registered subset (instances 0–1, seed 0) is not in `numbers.json`. make_numbers4 recomputes the per-n means for the H6 figure with `analyze4.load` and asserts that their slope equals analyze4's H6 estimate.
- analyze4 does not aggregate lock leaks, stalls, `graph_cycle` agreement or control-template outcomes, although the prereg lists them as exploratory. They are added as `\Raw...` episode counts read from the CSV columns.
- p-values below 0.001 print as `<0.001`. Sign-test p-values can be about 1e-9.

## Known gaps
- Paper length: the main text runs to page 12 of the two-column ACL layout through the Acknowledgments and the appendix to page 28; the supplement has 70 pages.
- The registered cross-model regression is reported with CR1 (sandwich) standard errors and a wild cluster bootstrap; the CR2 correction the registration names is listed as not done (Study 2 deviations table).
- Orchestrators outside the freeze (`tab:orchestrators`): the scripts as run are in `orchestrators_as_run/` at the artifact root, with their own `SHA256SUMS`.
- The message-content coding (Study 1 prereg exploratory, E9) is manual, not in the pipeline, and has not been done.
- The H5 transcript audit was performed by an AI agent (`../audit/H5_AUDIT.md`); its counts enter through `rollback_sensitivity.py` (`\HfiveAudit...`).
- Anonymized Study 1 artifact: `python3 ../make_anon_artifact.py --out DIR --results ../../results4/full --results-sql ../../results_sql --analysis ../analysis --registration-date YYYY-MM-DD` (src4, src4_batch, src_sql, this pipeline, the audit, results; redacted copies plus `ANON_CHANGES.md`, `FREEZE_OVERRIDE.json`, `ARTIFACT_README.md`; never touches src4). Verified 2026-11-02: every confirmatory, exploratory and post hoc output and every `numbers.tex` macro reproduce from inside the artifact. The two-study artifact is `../make_artifact_v2.py`.
