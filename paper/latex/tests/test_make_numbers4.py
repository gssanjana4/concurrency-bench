"""Tests for make_numbers4 on the dry-run analysis (run: python3 -m unittest discover -s tests).

Uses ANALYSIS_DIR (env) or ../analysis_dry; builds it with run_analysis.py if missing.

make_numbers4 runs in a throw-away copy of the latex folder (OUT), so the tests never overwrite the
real build's numbers.tex, tables/, facts/*.md or build/figdata.json with dry-run values. Generated files
are read from OUT; hand-written sources (main.tex, facts/src) are read from LATEX.
"""
import atexit
import shutil
import tempfile
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LATEX = os.path.dirname(HERE)
sys.path.insert(0, LATEX)
ANALYSIS = os.environ.get("ANALYSIS_DIR", os.path.join(os.path.dirname(LATEX), "analysis_dry"))

import pipeline_common as P  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="mn4test_")
atexit.register(shutil.rmtree, _TMP, True)
OUT = os.path.join(_TMP, "paper-concurrency", "latex")


def make_copy():
    """Copy the latex sources to OUT (with PREREGISTRATION.md beside it, as make_numbers4 expects)."""
    if os.path.isdir(OUT):
        return
    shutil.copytree(LATEX, OUT, ignore=shutil.ignore_patterns("__pycache__", "_budget", "main.pdf", "*.aux", "*.log",
                                                            "main.txt", "main.bbl", "main.blg", "main.out"))
    os.symlink(os.path.join(os.path.dirname(LATEX), "PREREGISTRATION.md"), os.path.join(_TMP, "paper-concurrency", "PREREGISTRATION.md"))


def defined_macros():
    txt = open(os.path.join(OUT, "numbers.tex")).read()
    return dict(re.findall(r"^\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}$", txt, re.M))


def strip_comments(t):
    return re.sub(r"(?<!\\)%.*", "", t)


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        make_copy()
        if not os.path.exists(os.path.join(ANALYSIS, "confirmatory.json")):
            subprocess.run([sys.executable, os.path.join(LATEX, "run_analysis.py"), "--dry-run", "--out", ANALYSIS],
                           check=True, cwd=LATEX, env=env)
        if not os.path.exists(os.path.join(ANALYSIS, "exploratory_posthoc.json")):
            subprocess.run([sys.executable, os.path.join(LATEX, "explore4.py"), "--analysis", ANALYSIS],
                           check=True, cwd=LATEX, env=env)
        if not os.path.exists(os.path.join(ANALYSIS, "rollback_sensitivity.json")):
            subprocess.run([sys.executable, os.path.join(LATEX, "rollback_sensitivity.py"), "--analysis", ANALYSIS],
                           check=True, cwd=LATEX, env=env)
        for script, out_name in (("posthoc_review.py", "posthoc_review.json"), ("reference_policies.py", "reference_policies.json")):
            if not os.path.exists(os.path.join(ANALYSIS, out_name)):
                subprocess.run([sys.executable, os.path.join(LATEX, script), "--analysis", ANALYSIS], check=True, cwd=LATEX,
                               env=dict(env, RESULTS_SQL=os.path.join(P.ROOT, "results_sql")))
        r = subprocess.run([sys.executable, os.path.join(OUT, "make_numbers4.py"), "--analysis", ANALYSIS, "--check"],
                           cwd=OUT, env=dict(env, SRC4=P.SRC4, RESULTS_SQL=os.path.join(P.ROOT, "results_sql")),
                           capture_output=True, text=True)
        cls.out = r.stdout + r.stderr
        cls.rc = r.returncode
        cls.nums = defined_macros()

    def test_runs_and_lint_clean(self):
        self.assertEqual(self.rc, 0, self.out)
        self.assertIn("lint: ok", self.out)

    def test_freeze_verifies(self):
        _, problems = P.verify_freeze()
        self.assertEqual(problems, [])

    def test_dry_run_marked(self):
        self.assertEqual(self.nums["PipelineDryRun"], "1")
        self.assertIn("DRY RUN", open(os.path.join(OUT, "numbers_report.txt")).readline())
        self.assertTrue(json.load(open(os.path.join(OUT, "build", "figdata.json")))["dry_run"])
        for f in os.listdir(os.path.join(OUT, "tables")):
            self.assertIn("Input: DRY RUN", open(os.path.join(OUT, "tables", f)).readline(), f)
        self.assertTrue(json.load(open(os.path.join(ANALYSIS, "provenance.json")))["dry_run"])

    def test_every_macro_used_is_defined(self):
        """Every \\command in main.tex and tables/*.tex is defined in numbers.tex, main.tex, or LaTeX/packages.

        Generated-name macros are checked against numbers.tex; the remaining names must be
        defined in main.tex or be in a short list of standard commands."""
        # since the 2026-11-10 split (CUT_LOG.md) the shared preamble (preamble_shared.tex) defines the macros of both
        # documents, and the supplement (supplement.tex and its supp_*.tex inputs) is checked like the paper
        main = strip_comments(open(os.path.join(LATEX, "main.tex")).read() + open(os.path.join(LATEX, "preamble_shared.tex")).read()
                              + open(os.path.join(LATEX, "supplement.tex")).read())
        srcs = [main] + [strip_comments(open(os.path.join(OUT, "tables", f)).read()) for f in os.listdir(os.path.join(OUT, "tables"))]
        srcs += [strip_comments(open(os.path.join(LATEX, f)).read()) for f in ("study2.tex", "study1_full.tex", "study2_prompts.tex", "study2_analysis.tex",
                                                                             "supp_study1.tex", "supp_db_sql.tex", "supp_extended.tex")]
        used = set()
        for s in srcs:
            used |= {u for u in re.findall(r"\\([A-Za-z@]+)", s) if "@" not in u}
        local = set(re.findall(r"\\(?:newcommand|providecommand|def)\{?\\([A-Za-z@]+)", main)) | set(re.findall(r"\\newif\\if([A-Za-z]+)", main))
        # Study 2 macros: the registered analysis (verbatim copy of analysis5/out_study2/numbers.tex), the descriptives
        # and the fixed constants, all input by main.tex's preamble (2026-11-09)
        for f in ("study2_constants.tex", os.path.join("study2_out", "study2_registered_numbers.tex"),
                  os.path.join("study2_out", "study2_numbers.tex")):
            local |= set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", open(os.path.join(LATEX, f)).read()))
        local |= {"if" + x for x in re.findall(r"\\newif\\if([A-Za-z]+)", main)} | {x + "true" for x in re.findall(r"\\newif\\if([A-Za-z]+)", main)} \
            | {x + "false" for x in re.findall(r"\\newif\\if([A-Za-z]+)", main)}
        standard = set("""documentclass usepackage IfFileExists input newcommand providecommand def edef makeatletter makeatother ifx else fi
            ifnum newif title author begin end maketitle section subsection appendix label ref caption centering includegraphics
            columnwidth textwidth linewidth small scriptsize footnotesize tiny bfseries textbf texttt textcolor color fcolorbox parbox
            dimexpr fboxsep fboxrule relax par smallskip noindent mbox definecolor SetWatermarkText SetWatermarkScale SetWatermarkColor
            nocite bibliography toprule midrule bottomrule multicolumn shortstack mathrm max allowbreak detokenize textasciitilde
            textbackslash geq in leq times vs alpha FloatBarrier PENDING log dagger
            citet citep citealp paragraph emph item ldots S if quad qquad text renewcommand outauthor raggedright clearpage
            BuildAnonymous ifacl itshape ttfamily textrm bmod tabularnewline href hsize hss hfil hskip vskip acl
            Delta delta pm addlinespace
            externaldocument usepackage SuppSec SuppSecs SuppTab SuppTabs SuppTabsAnd SuppFig PaperRef AtBeginDocument
            NewCommandCopy DeclareRobustCommand renewenvironment ifundefined thesection thetable thefigure theHsection
            theHtable theHfigure arabic tabcolsep setlength resizebox subsubsection""".split())
        gen = re.compile(r"^(H(one|two|three|fourA|fourB|five|six)|Rb[A-Z]|Sens|X[A-Z]|Cmp|Des|Pilot|Plan|Budget|Mutants|Excl|Expl|Obs|Cost|Served|Model[A-Z]|Raw[A-Z]|DataStatus|PipelineDryRun|Ref[A-Z]|Tpl[A-Z]|Exact[A-Z]|Use[A-Z]|Store[A-Z]|Lease[A-Z]|"
                         r"SameReply|RunFirst|RunLast|Qwen[A-Z]|SqlN[A-Z]|SqlViol|SqlCost)")
        missing = sorted(u for u in used if u not in self.nums and u not in local and u not in standard)
        self.assertEqual(missing, [], "macros used but not defined")
        gen_missing = sorted(u for u in used if gen.match(u) and u not in self.nums)
        self.assertEqual(gen_missing, [])

    def test_no_literal_result_digits_in_main_body(self):
        import make_numbers4 as M
        undefined, digits = M.lint_main(os.path.join(LATEX, "main.tex"), self.nums)
        self.assertEqual(undefined, [])
        self.assertEqual(digits, [], "literal digits in main.tex body")

    def test_lint_catches_a_typed_number(self):
        import make_numbers4 as M
        tmp = os.path.join(HERE, "_lint_probe.tex")
        with open(tmp, "w") as f:
            f.write("\\begin{document}\nThe rate was 0.73 \\cite{x2026} in H1 and \\HoneNoSuchMacro.\n\\end{document}\n")
        try:
            undefined, digits = M.lint_main(tmp, self.nums)
        finally:
            os.remove(tmp)
        self.assertEqual(undefined, ["HoneNoSuchMacro"])
        self.assertEqual(len(digits), 1)

    def test_values_match_confirmatory_json(self):
        c = json.load(open(os.path.join(ANALYSIS, "confirmatory.json")))["registered"]
        for t in c["hypotheses"]["H1"]["tests"]:
            if t["status"] != "tested":
                continue
            import make_numbers4 as M
            k = M.model_key(t["model"])
            self.assertEqual(self.nums[f"Hone{k}Rate"], M.f2(t["estimate"]))
            self.assertEqual(self.nums[f"Hone{k}Reject"], "yes" if t["reject"] else "no")
        self.assertEqual(self.nums["HoneVerdict"], c["hypotheses"]["H1"]["verdict"])

    def test_macro_names_letters_only(self):
        self.assertTrue(all(re.match(r"^[A-Za-z]+$", k) for k in self.nums))

    def test_facts_render_without_unknown_macros(self):
        for f in os.listdir(os.path.join(OUT, "facts")):
            if f.endswith(".md"):
                self.assertNotIn("UNDEFINED", open(os.path.join(OUT, "facts", f)).read(), f)

    def test_refuses_on_freeze_mismatch(self):
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            for n in P.freeze_table():
                shutil.copy(os.path.join(P.SRC4, n), tmp)
            shutil.copy(os.path.join(P.SRC4, "FREEZE.md"), tmp)
            with open(os.path.join(tmp, "score4.py"), "a") as f:
                f.write("\n# tampered\n")
            r = subprocess.run([sys.executable, os.path.join(OUT, "make_numbers4.py"), "--analysis", ANALYSIS],
                               cwd=OUT, env=dict(os.environ, SRC4=tmp, PYTHONDONTWRITEBYTECODE="1"), capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("REFUSING", r.stdout + r.stderr)
        finally:
            shutil.rmtree(tmp)


    # ---------------- layout (REVIEW_PREDATA.md section 6)
    def test_main_text_floats(self):
        """Layout since the 2026-11-10 paper/supplement split (CUT_LOG.md): the 12-page main text keeps the compact
        what-changed table, the S2-H1 Delta figure and the task-class table; the appendix keeps the Study 2 tables the
        main text cites and the Study 1 verdict table; everything else (Study 1 in full, the per-family figure, the
        full Study 2 tables) is in the supplement."""
        main = strip_comments(open(os.path.join(LATEX, "main.tex")).read())
        body, app = main.split(r"\section*{Limitations}", 1)
        s2 = strip_comments(open(os.path.join(LATEX, "study2.tex")).read())
        for keep in ("study2_out/figures/fig_s2_delta.pdf", r"\label{tab:s2-class}", r"\label{tab:study2-changes}"):
            self.assertIn(keep, body + s2, keep)
        appendix = app.split(r"\appendix", 1)[1]
        for keep in ("tables/verdicts.tex", "s2_deviations_all", "s2_example", "s2_h1", "s2_primitives", "s2_outcomes",
                     "s2_probes", "s2_exposure", "s2_budget", "s2_selection"):
            self.assertIn(keep, appendix, keep)
        supp = "".join(strip_comments(open(os.path.join(LATEX, f)).read())
                       for f in ("supplement.tex", "study1_full.tex", "supp_study1.tex", "supp_db_sql.tex"))
        for moved in ("figures/fig_labels.pdf", "figures/fig_choices.pdf", "tables/configs.tex", "tables/main_results.tex",
                      "tables/coordination.tex", "figures/fig_nonser_by_config.pdf", "figures/fig_h6_scaling.pdf",
                      "study2_out/figures/fig_s2_family.pdf", "s2_tests_full_all", "s2_firth", "tables/h5_audit.tex",
                      "tables/sql_slice.tex"):
            self.assertNotIn(moved, main + s2, moved)
            self.assertIn(moved, supp, moved)
        for ex in ("goodput", "post_rejection", "ws_prevent", "loto", "diagnostics"):
            self.assertIn(f"tables/{ex}.tex", supp)

    def test_verdict_table_shows_estimates_cis_and_reject(self):
        t = open(os.path.join(OUT, "tables", "verdicts.tex")).read()
        for hk in ("Hone", "Htwo", "Hthree", "HfourA", "Hsix"):
            self.assertIn(f"\\VerdictCell{{\\{hk}HaikuReject}}{{\\{hk}HaikuEst}}", t)
            self.assertIn(f"\\{hk}HaikuCI", t)
        self.assertIn("HfourBHaikuEstI", t)
        self.assertIn("HfourBHaikuCIII", t)
        self.assertIn("HfiveHaikuK", t)
        self.assertNotIn("PHolm", t, "p-values belong in the appendix table")

    def test_configs_table_is_single_column(self):
        t = open(os.path.join(OUT, "tables", "configs.tex")).read()
        self.assertIn(r"\begin{table}[t]", t)
        self.assertNotIn(r"\begin{table*}", t)

    # ---------------- facts (review sections 3, 7)
    def facts(self, name):
        if not os.path.isdir(os.path.join(LATEX, "facts", "src")):
            self.skipTest("facts/src not shipped (review artifact)")
        return open(os.path.join(LATEX, "facts", "src", name)).read()

    def test_scorer_facts_corrected(self):
        """Review R1 W1: verify-and-compensate is penalised by the registered scorer; promotion is not."""
        t = self.facts("introduction.md")
        self.assertIn("Verify-and-compensate IS penalised", t)
        self.assertIn("Promotion is not penalised", t)
        main = strip_comments(open(os.path.join(LATEX, "main.tex")).read())
        self.assertNotIn("Neither strategy is penalised", main)
        for f in ("introduction.md", "results.md", "discussion.md"):
            for line in self.facts(f).splitlines():
                if "promotion or verify-and-compensate would prevent" in line:
                    self.fail(f"{f}: {line}")

    def test_no_unscoped_novelty_or_group_claims_in_facts(self):
        self.facts("results.md")  # skips when facts/src is not shipped
        for f in os.listdir(os.path.join(LATEX, "facts", "src")):
            for line in self.facts(f).splitlines():
                if "nobody measures" in line.lower():
                    self.assertRegex(line, r"NOT|No ")
        t = self.facts("results.md")
        self.assertNotIn("Summary of the split", t)
        self.assertIn("Cross-model description", t)

    def test_no_fact_says_cas_cannot_prevent_write_skew(self):
        self.facts("introduction.md")
        bad = re.compile(r"(cas|conditional writes?|version checks?|per-record[^.\n]{0,30})\s+(cannot|can't|can not|do(es)? not)\s+"
                         r"(prevent|stop|remove)[^.\n]{0,20}write skew|write skew[^.\n]{0,40}(impossible to prevent|unpreventable)", re.I)
        for f in os.listdir(os.path.join(LATEX, "facts", "src")):
            txt = re.sub(r"## Must NOT claim.*?(?=\n## )", "", self.facts(f), flags=re.S)
            for line in txt.splitlines():
                if "NOT" in line or "Never" in line or "never" in line or "registered title" in line:
                    continue  # the must-not-claim list and the note on H4b's registered title quote the phrase
                self.assertIsNone(bad.search(line), f"{f}: {line}")
        self.assertIn("preventable", self.facts("introduction.md"))
        self.assertIn("version + 1", self.facts("introduction.md"))

    def test_introduction_has_claim_lists_and_contributions(self):
        t = self.facts("introduction.md")
        for h in ("## Must claim", "## Must NOT claim", "## Contributions (three bullets"):
            self.assertIn(h, t)
        contrib = t.split("## Contributions (three bullets", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(len([x for x in contrib.splitlines() if x.startswith("- ")]), 3)

    def test_limitations_new_items(self):
        t = self.facts("limitations.md")
        for needle in ("Aware off is not", "lock tool description", "Agents you can message", "held by someone else",
                       "DesNContendedTemplates", "paired with goodput"):
            self.assertIn(needle, t)

    def test_checklist_ai_disclosure_complete(self):
        t = self.facts("checklist.md")
        for needle in ("The harness and the frozen confirmatory analysis", "literature search", "reference verification",
                       "drafted the pre-registration", "write-skew templates", "aware-prompt arm", "scaling phase",
                       "reviewed and adopted", "src4_batch", "src_sql", "rollback_sensitivity.py", "make_anon_artifact.py",
                       "performed by an AI agent", "style revision", "deviations-table cell text", "reference drafts",
                       "drafted by an AI assistant on 2026-11-02", "Author contributions and AI use", "authorcheck", "AI_DRAFTED_SECTIONS.md", "do NOT link the OSF page",
                       "redacted copy", "Registration date", "camera-ready", "wrote all paper prose\" is false"):
            self.assertIn(needle, t)
        # the drafted sections are never described as "low-novelty" text (ACL definition does not cover them)
        for line in t.splitlines():
            if "low-novelty" in line:
                self.assertIn("Do NOT label", line)

    def test_no_gendered_wording_in_boxes(self):
        main = strip_comments(open(os.path.join(LATEX, "main.tex")).read())
        self.assertNotRegex(main, r"\b(she|her|herself|his|him|himself)\b")

    def test_h5_audit_not_called_manual(self):
        for f in ("h5.tex", "h5_audit.tex"):
            t = open(os.path.join(OUT, "tables", f)).read()
            self.assertNotIn("manual", t)
            self.assertIn("AI agent", t)

    def test_author_sections_reviewed(self):
        """The author's sections (abstract, Introduction, Results, Discussion, Acknowledgments) hold no \\authorwrites
        placeholder: an AI assistant drafted them for the author to revise. Each carried an orange \\authorcheck marker
        until the author's review; the markers were cleared on 2026-11-14, so none may remain in the paper or the
        supplement (preflight and make_arxiv.sh fail on a marker). The H2-threshold sentence must say plainly that the
        registration gives no rationale."""
        main = strip_comments(open(os.path.join(LATEX, "main.tex")).read())
        body = main.split(r"\begin{document}", 1)[1]
        self.assertNotIn(r"\authorwrites", body)
        spans = [(r"\begin{abstract}", r"\end{abstract}"), (r"\section{Introduction}", r"\section{Related Work}"),
                 (r"\section{\SOne: The First Run}", r"\section{\STwo: Corrected Harness}"), (r"\section{Discussion}", r"\FloatBarrier"),
                 (r"\section*{Acknowledgments}", r"\bibliography")]
        for start, end in spans:
            self.assertIn(start, body, start)
            part = body.split(start, 1)[1].split(end, 1)[0]
            self.assertNotIn(r"\authorcheck{", part, start)
        for f in ("study2.tex", "study2_prompts.tex", "supplement.tex", "study2_analysis.tex", "study1_full.tex", "supp_study1.tex",
                  "supp_db_sql.tex", "supp_extended.tex"):
            self.assertNotIn(r"\authorcheck{", strip_comments(open(os.path.join(LATEX, f)).read()), f)
        study1 = strip_comments(open(os.path.join(LATEX, "study1_full.tex")).read())
        self.assertIn("without a rationale", study1)
        ack = body.split(r"\section*{Acknowledgments}", 1)[1].split(r"\bibliography", 1)[0]
        for needle in ("Claude models assisted with the designs, code and writing", "which the author directed and reviewed"):
            self.assertIn(needle, ack)
        # Study 2 (2026-11-09): the placeholder is gone; the section inputs study2.tex
        s2 = body.split(r"\section{\STwo: Corrected Harness}", 1)[1].split(r"\section{Discussion}", 1)[0]
        self.assertIn(r"\input{study2}", s2)
        self.assertNotIn(r"\studytwo{", body)
        s2tex = strip_comments(open(os.path.join(LATEX, "study2.tex")).read())
        self.assertNotIn(r"\studytworesults", s2tex)
        self.assertIn(r"\subsection{Results}", s2tex)

    def test_ai_drafted_sections_listed(self):
        """Every section marked AI-DRAFTED in main.tex is listed in AI_DRAFTED_SECTIONS.md (needed for the disclosure)."""
        if not os.path.exists(os.path.join(LATEX, "AI_DRAFTED_SECTIONS.md")):
            self.skipTest("AI_DRAFTED_SECTIONS.md not shipped (review artifact)")
        # main.tex plus the section files it inputs (2026-11-10: the Study 1 appendix, the Study 2 prompts and the
        # Study 2 analysis appendix carry their own \section headings)
        main = "".join(open(os.path.join(LATEX, f)).read() for f in ("main.tex", "study1_full.tex", "study2_prompts.tex", "study2_analysis.tex",
                                                                     "supplement.tex", "supp_study1.tex", "supp_db_sql.tex", "supp_extended.tex"))
        listing = open(os.path.join(LATEX, "AI_DRAFTED_SECTIONS.md")).read()
        for needle in ("src4_batch", "performed by an AI agent", "deviations.csv", "STYLE_GUIDE_ACL.md", "REFERENCE_DRAFTS_FOR_AUTHOR.md",
                       "Database Foundations", "product of Anthropic", "T5-T8_resolution.md"):
            self.assertIn(needle, listing)
        self.assertNotRegex(listing, r"\b(she|her|herself)\b")
        for name in ("Related Work", "Testbed", "The First Run", "Limitations", "Ethics Statement",
                     "Coordination Configs and Tool Specifications", "Task Templates and Prompts", "Scoring Rules",
                     "Deviations from the", "Full Results", "Exploratory Analyses from Saved Data",
                     "Reproducibility", "Database Foundations", "Exploratory Slice on a Real Database",
                     "Prompts and Tool Texts", "in Full", "Registered Analysis, Budget and Sensitivity"):
            self.assertIn(name, main, name)
            self.assertIn(name, listing, name)

if __name__ == "__main__":
    unittest.main()
