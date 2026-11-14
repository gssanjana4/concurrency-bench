#!/usr/bin/env python3
"""Build the two-study code + data artifact (Study 1 and Study 2) for Zenodo, GitHub and review. Copies only.

    python3 make_artifact_v2.py --out DIR [--zip FILE] [--mode public|anonymous]
                                [--results STUDY1_RESULTS4_FULL] [--results-sql STUDY1_RESULTS_SQL]
                                [--study2-data DIR] [--study2-analysis DIR] [--wrappers DIR ...]
                                [--with-paper-source] [--github URL] [--doi DOI] [--version TAG]
    python3 make_artifact_v2.py --scan-only PATH ...      # identity scan only (nothing copied)

Nothing under src4/, src5/, src5_batch/, src5_verify/, analysis5/, paper-concurrency/latex/ or the data is modified:
every source is read, hashed and copied. The layout of DIR mirrors the build machine, so the frozen tooling runs
unchanged inside it (``src5/freeze5.py --check`` finds ``../src5_batch``, ``../src5_verify/dry_check5.py`` and
``../run_conc_study2.sh``; ``analysis5/analyze5.py`` finds ``../src5/plan_study2.json``):

  README.md, LICENSE, SHA256SUMS, BUILD_INFO.json, FREEZE_OVERRIDE.json [, ANON_CHANGES.md]
  src4/ src4_batch/ src_sql/ orchestrators_as_run/           Study 1 frozen harness, batch drivers, SQL slice, the
                                                             orchestrator scripts exactly as run on the author's Mac
  paper/latex/ paper/audit/ paper/PREREGISTRATION.md          the paper and supplement source (main.tex, study2.tex,
                                                             study2_prompts.tex, supplement.tex, supp_*.tex,
                                                             study2_analysis.tex, study1_full.tex, preamble_shared.tex,
                                                             study2_constants.tex,
                                                             refs.bib, the ACL style files), the generated inputs it
                                                             compiles from (numbers.tex, tables/, figures/, study2_out/),
                                                             the fact sheets (facts/src/), the Study 1 number pipeline
                                                             (scripts and tests) and the H5 audit;
                                                             identity.tex only in public mode (--no-paper-source omits
                                                             the source and the generated inputs)
  paper/paper_<mode>.pdf, paper/supplement_<mode>.pdf          the compiled paper and supplement of the same build (latex/build/)
  preregistration/PREREGISTRATION.md, PREREGISTRATION_STUDY2.md   the two registration texts
  src5/ src5_batch/ src5_verify/ run_conc_study2.sh          Study 2 frozen harness (src5/FREEZE.md, 38 files)
  run_conc_s2go.sh run_conc_s2dry.sh run_conc_elig.sh       non-frozen wrappers, as run (labelled in README.md)
  analysis5/                                                 analyze5.py (frozen, registered), descriptives5.py,
                                                             balance5.py, tests_analyze5.py, PREREG_GAPS.md,
                                                             power_sims/, testdata/, out/ (registered dry-run
                                                             outputs), out_study2/ (eligibility.json, results.json,
                                                             numbers.tex of the registered run)
  CHANGES_V2.md STUDY2_RUN_LOG.md                            harness change log and the paid-run log
  data/results5/study2/                                      Study 2 transcripts, results.csv, spend.jsonl,
                                                             failures.jsonl, summary.md, preflight/, validity/,
                                                             the run and lane logs, openrouter_balance.jsonl
  data/results4/full/, data/results_sql/                     Study 1 data: copied when --results/--results-sql are
                                                             given, otherwise a clearly named placeholder README
                                                             (the data live on the author's Mac)
  reference_outputs/study1_analysis/                         the author's Study 1 analysis outputs (--study1-analysis)
  tools/                                                     this builder, make_anon_artifact.py (its identity
                                                             rules) and compare_json.py (public mode only)

Modes. ``public`` (default): nothing is redacted; every frozen file must match its FREEZE.md hash and every
registered file its registered sha256 (the build refuses otherwise); FREEZE_OVERRIDE.json is written with an empty
list. ``anonymous``: the identity rules of make_anon_artifact.py (plus the Study 2 registration's author line and
the OSF identifiers) are applied line by line to every text file; latex/identity.tex (the author line and the OSF
identifiers of the named build) is not copied, and the self-citation entry of refs.bib is replaced by the same
"Anonymous. Concurrent submission." entry that latex/build.sh --anonymous writes; redacted frozen files are recorded in
FREEZE_OVERRIDE.json exactly as before (original sha256 = FREEZE.md hash, checked at build time; redacted sha256
recorded), ANON_CHANGES.md lists every changed line, and the whole tree is re-scanned (any hit is an error).
paper/latex/pipeline_common.py accepts the src4 override; src5/freeze5.py and the batch driver do not read the
override, so on an anonymous copy they report the redacted files (documented in README.md).

Edits the builder makes in both modes (listed in README.md and BUILD_INFO.json): the ``raw`` field of
openrouter_balance.jsonl (account metadata of the shared key) is replaced by a note; the fields analyze5 reads are
kept. In public mode the author's local filesystem paths in the Study 2 run and lane logs are replaced by the
make_anon_artifact.py path tokens (traceback lines); nothing else is touched.

Checks at build time: src4/FREEZE.md and src5/FREEZE.md against the copies; ``src5/freeze5.py --check`` run inside
the copy; the registered sha256 of analyze5.py, balance5.py, tests_analyze5.py, run_conc_study2.sh, src5/FREEZE.md,
PREREGISTRATION_STUDY2.md, eligibility.json, results.json and numbers.tex; the sha256 of the shipped transcript list
against ``inputs.sha256_of_list`` in results.json and eligibility.json (the shipped data are exactly the files the
registered analysis read); orchestrators_as_run/SHA256SUMS against its copies; that no source changed during the
copy. SHA256SUMS lists every shipped file (``sha256sum -c SHA256SUMS``).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_anon_artifact as A  # noqa: E402  (identity rules, scan, redaction, FREEZE row parser)

ROOT = os.path.dirname(HERE)
SRC5 = os.environ.get("SRC5", os.path.join(ROOT, "src5"))
SRC5_BATCH = os.path.join(ROOT, "src5_batch")
SRC5_VERIFY = os.path.join(ROOT, "src5_verify")
RUN_S2 = os.path.join(ROOT, "run_conc_study2.sh")
ANALYSIS5 = os.path.join(ROOT, "analysis5")
CHANGES_V2 = os.path.join(ROOT, "CHANGES_V2.md")
RUN_LOG = os.path.join(HERE, "STUDY2_RUN_LOG.md")
PREREG2 = os.path.join(HERE, "PREREGISTRATION_STUDY2.md")
OSF_RECORDS = os.path.join(HERE, "osf_registration_records.md")  # review F1 S8: registration records without the embargo lifted
ORCH = os.path.join(HERE, "orchestrators_as_run")
STUDY1_ANALYSIS = os.path.join(HERE, "analysis")
RELEASE = os.path.join(HERE, "release")
DEF_STUDY2_DATA = os.path.join(ROOT, "study2_data", "results5", "study2")
DEF_STUDY2_OUT = os.path.join(ROOT, "study2_data", "analysis5", "out_study2")
DEF_REGISTERED = os.path.join(ROOT, "study2_data", ".study2_registered")
DEF_AUTORUN_LOG = os.path.join(ROOT, "study2_data", ".autorun_conc", "logs", "004_s2go.log")
WRAPPERS = ("run_conc_s2go.sh", "run_conc_s2dry.sh", "run_conc_elig.sh")
DEF_WRAPPER_DIRS = ("/mnt/attach/outputs", ROOT)
ANALYSIS5_FILES = ("analyze5.py", "descriptives5.py", "balance5.py", "tests_analyze5.py", "PREREG_GAPS.md")
ANALYSIS5_DIRS = ("power_sims", "testdata", "out")
STUDY2_OUT_FILES = ("eligibility.json", "results.json", "numbers.tex")
PAPER_SOURCE = ("main.tex",)  # the file the earlier --with-paper-source shipped
# the paper source and everything it compiles from (both modes unless --no-paper-source); identity.tex only in public mode
# since the 2026-11-10 paper/supplement split: the shared preamble, the supplement and its sources
PAPER_TEX = ("main.tex", "study2.tex", "study2_analysis.tex", "study2_prompts.tex", "study1_full.tex", "study2_constants.tex",
             "preamble_shared.tex", "supplement.tex", "supp_study1.tex", "supp_db_sql.tex", "supp_extended.tex",
             "refs.bib", "acl.sty", "acl_natbib.bst", "numbers.tex", "study2_factpass.py", "study2_lint.py",
             "check_model_macros.py",
             # review F1 (2026-11-14): the hash check build.sh runs, and the TMLR build mode (pinned official style files)
             "check_hashes.py", "tmlr_setup.tex", os.path.join("tmlr", "tmlr.sty"), os.path.join("tmlr", "tmlr.bst"),
             os.path.join("tmlr", "LICENSE"), os.path.join("tmlr", "PIN.md"))
PAPER_IDENTITY = "identity.tex"
PAPER_DIRS = ("study2_out", "tables", "figures")
PAPER_FACTS = (os.path.join("facts", "src", "study2_methods_facts.md"), os.path.join("facts", "src", "study2_results_facts.md"),
               os.path.join("facts", "src", "study2_results_crosscheck.md"))
PAPER_PDF = {"public": "main_preprint.pdf", "anonymous": "main_anonymous.pdf"}  # latex/build/<file> -> paper/paper_<mode>.pdf
SUPP_PDF = {"public": "supplement_preprint.pdf", "anonymous": "supplement_anonymous.pdf"}  # -> paper/supplement_<mode>.pdf
# the self-citation entry of refs.bib, replaced in anonymous mode exactly as latex/build.sh --anonymous does (review T8 F26)
ANON_BIB_ENTRY = "@misc{anon2027retries,\n  author = {Anonymous},\n  title  = {Concurrent submission},\n  year   = {n.d.}\n}"
TOOLS = ("make_artifact_v2.py", "make_anon_artifact.py", os.path.join("release", "compare_json.py"))
STUDY2_LANES = ("probe-anthropic", "probe-gemini", "probe-openrouter", "n2-anthropic", "n2-gemini", "n2-openrouter")
LANE_FILES = ("results.csv", "spend.jsonl", "failures.jsonl")
STUDY2_BASE_FILES = ("summary.md", "summary_dry.md", "run_study2.log", "run_study2_dry.log", "validity_run.log",
                     "rehearsal.log", "lane_anthropic.log", "lane_gemini.log", "lane_openrouter.log")
STUDY2_BASE_DIRS = ("preflight", "validity")
SKIP_DIRS = set(A.SKIP_DIRS) | {"batch_state", "held_for_pair", ".pytest_cache", ".run_study2.lock", "rehearsal"}

AUTHOR = "Sanjana Gopnal Swamy"
AUTHOR_CITED = "Gopnal Swamy, Sanjana"
TITLE = "Do LLM Agents Coordinate on Shared Records?"
# the full title, exactly as on the PDF (citation block; Scholar matches titles)
TITLE_FULL = TITLE + " Two Pre-registered Studies of Optional Protection on a Record API"
OSF1, OSF2 = "https://osf.io/a5vec", "https://osf.io/zj3an"
REG1_DATE, REG2_DATE = "2026-10-31", "2026-11-09"
REG2_TS = "2026-11-09T18:35:24Z"
ELIG_SHA = "f4ad4f072fffc0e3a703ab708d61b5371e72f5481cb6f13a639f1598b228341d"
# registered / recorded sha256 (src5/FREEZE.md; PREREGISTRATION_STUDY2.md "Freeze"; STUDY2_RUN_LOG.md). Checked at build.
EXPECTED = {
    "src5/FREEZE.md": "e5834fb5b81565158493acda36b3fb5d32e2455a3504a86ffac646ba09681c6f",
    "run_conc_study2.sh": "76bcfa3f6e2c518ba0dafa50f702f68512490a9eee37f5c24bd0fe6443f9ead9",
    "analysis5/analyze5.py": "99dff56a75c925e48bff0f676bfc60f0ed52c4d3aaa1df88cb6f2c9b609a1357",
    "analysis5/balance5.py": "b387791ec7f530b12f18191b7bf333f78236c512e24591ee27b1cd4dfa4e8e87",
    "analysis5/tests_analyze5.py": "f2c5ffaf4716f81a7589b9c995c466d1af76b3527c1208d4bfcd46aac08ca4f1",
    "preregistration/PREREGISTRATION_STUDY2.md": "8193e9602f0c1257e1ec69d890f15ab4e63c084fa0da77d1eae416c16fd23ee5",
    "analysis5/out_study2/eligibility.json": ELIG_SHA,
    "analysis5/out_study2/results.json": "0c11cec935fee524c55874229c43955f1b9b5f88eacf1106ced4d7fc2c09c6e7",
    "analysis5/out_study2/numbers.tex": "a70c6f84b9c928604dcca18c1584a44cce22eb38bb08e49e89d7e01509d07daa",
}
# anonymous mode: the Study 2 registration names the author in full and links both registrations
ANON_EXTRA_RULES = [
    ("author name", re.compile(r"Sanjana Gopnal Swamy"), "ANON_AUTHOR"),
    ("author name", re.compile(r"Gopnal Swamy, Sanjana"), "ANON_AUTHOR"),
    ("author name", re.compile(r"Gopnal Swamy"), "ANON_AUTHOR"),
    ("OSF link", re.compile(r"(?:https?://)?osf\.io/(?:a5vec|zj3an|9qvpt)\b"), "[OSF LINK REDACTED FOR REVIEW]"),
    ("OSF id", re.compile(r"\b(?:a5vec|zj3an|9qvpt)\b"), "[OSF ID REDACTED FOR REVIEW]"),
]
PATH_RULES = [r for r in A.RULES if r[0] in ("upload path", "desktop path", "home path")]
MIT = """MIT License

Copyright (c) 2026 {holder}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


# ---------------------------------------------------------------------------------------------------- helpers
def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hashes(root: str) -> dict:
    out = {}
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in fs:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = sha_file(p)
    return out


class Build:
    def __init__(self, out: str, mode: str):
        self.out, self.mode = out, mode
        self.rules = (ANON_EXTRA_RULES + A.RULES) if mode == "anonymous" else []
        self.changes = []      # redactions (anonymous mode, or the path scrub of logs in public mode)
        self.copied = []       # relative paths written
        self.notes = []        # builder edits and warnings, for README/BUILD_INFO
        self.warnings = []

    def redact(self, line: str, rules):
        out, hits = line, []
        for name, pat, rep in rules:
            new = pat.sub(rep, out)
            if new != out:
                hits.append(name)
                out = new
        return out, hits

    def write(self, rel: str, data: bytes, mode: int = 0o644):
        dst = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        os.chmod(dst, (mode & 0o777) | 0o644)  # keep execute bits of scripts; never ship unreadable files
        self.copied.append(rel)

    def copy_file(self, src: str, rel: str, rules=None):
        """Copy src to <out>/rel through the given rules (default: the mode's rules); binary files byte for byte."""
        rules = self.rules if rules is None else rules
        mode = os.stat(src).st_mode
        with open(src, "rb") as f:
            data = f.read()
        if not rules or not A.is_text(data):
            self.write(rel, data, mode)
            return
        lines = data.decode("utf-8").split("\n")
        new, changed = [], []
        for i, line in enumerate(lines, 1):
            r, hits = self.redact(line, rules)
            new.append(r)
            if hits:
                changed.append((i, r, hits))
        out = "\n".join(new).encode("utf-8")
        self.write(rel, out, mode)
        if changed:
            self.changes.append({"file": rel, "sha_orig": sha(data), "sha_red": sha(out), "lines": changed})

    def walk(self, src_root: str, prefix: str, rules=None, skip_dirs=SKIP_DIRS, log_rules=None):
        """Copy a tree. ``log_rules``, when given, replaces ``rules`` for ``*.log`` files (the public build scrubs the
        local paths of the author's machine from run logs and alters nothing else)."""
        n = 0
        for d, dirs, files in os.walk(src_root):
            dirs[:] = sorted(x for x in dirs if x not in skip_dirs)
            for fn in sorted(files):
                if fn in A.SKIP_FILES or os.path.splitext(fn)[1] in A.SKIP_EXT:
                    continue
                src = os.path.join(d, fn)
                r = log_rules if (log_rules is not None and fn.endswith(".log")) else rules
                self.copy_file(src, os.path.join(prefix, os.path.relpath(src, src_root)), r)
                n += 1
        return n

    def copy_optional(self, src: str, rel: str, what: str, rules=None) -> bool:
        if os.path.isfile(src):
            self.copy_file(src, rel, rules)
            return True
        self.warnings.append(f"{what} not found at {src}; skipped")
        return False


# ---------------------------------------------------------------------------------------------------- study 2 data
def copy_study2_data(b: Build, base: str, autorun_log: str) -> dict:
    """data/results5/study2: lanes (transcripts, CSV, spend, failures), preflight/, validity/, summary and logs."""
    dst = os.path.join("data", "results5", "study2")
    counts = {}
    for lane in STUDY2_LANES:
        ld = os.path.join(base, lane)
        if not os.path.isdir(ld):
            raise SystemExit(f"ERROR: Study 2 lane directory missing: {ld}")
        t = os.path.join(ld, "transcripts")
        n = b.walk(t, os.path.join(dst, lane, "transcripts"), rules=[])  # transcripts: never altered
        counts[lane] = n
        for fn in LANE_FILES:
            p = os.path.join(ld, fn)
            if os.path.isfile(p):
                b.copy_file(p, os.path.join(dst, lane, fn), rules=[])
    for sub in STUDY2_BASE_DIRS:
        if os.path.isdir(os.path.join(base, sub)):
            b.walk(os.path.join(base, sub), os.path.join(dst, sub))
    log_rules = b.rules if b.mode == "anonymous" else PATH_RULES
    for fn in STUDY2_BASE_FILES:
        p = os.path.join(base, fn)
        if os.path.isfile(p):
            b.copy_file(p, os.path.join(dst, fn), rules=log_rules if fn.endswith(".log") else None)
    if os.path.isfile(autorun_log):
        b.copy_file(autorun_log, os.path.join(dst, "autorun_job004_s2go.log"), rules=log_rules)
    # openrouter_balance.jsonl: keep the fields analyze5.balance_report reads, drop the raw key-account response
    p = os.path.join(base, "openrouter_balance.jsonl")
    if os.path.isfile(p):
        rows = []
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                e["raw"] = ("removed by make_artifact_v2.py: the provider's raw key-account response (key label, user "
                            "and workspace ids, budgets); at_utc, phase, lane, usage_usd, limit_remaining_usd and "
                            "lane_exit are as logged by analysis5/balance5.py")
                rows.append(json.dumps(e, sort_keys=True))
        b.write(os.path.join(dst, "openrouter_balance.jsonl"), ("\n".join(rows) + "\n").encode())
        b.notes.append("data/results5/study2/openrouter_balance.jsonl: the `raw` provider response (account metadata "
                       "of the shared OpenRouter key) was replaced by a note; the fields analyze5 reads are unchanged.")
    return counts


def transcript_list_digest(base: str, probes_only: bool) -> tuple:
    """Same digest as analyze5.load_sample/inputs_digest over the lanes analyze5.discover selects."""
    import glob
    pats = ["probe-*"] if probes_only else ["n2-*", "probe-*"]
    hashes = []
    for pat in pats:
        for d in sorted(glob.glob(os.path.join(base, pat))):
            t = os.path.join(d, "transcripts")
            if not os.path.isdir(t):
                continue
            for p in sorted(glob.glob(os.path.join(t, "*.json"))):
                hashes.append([os.path.relpath(p, base), sha_file(p)])
    hashes.sort()
    return len(hashes), sha("\n".join(f"{a} {b}" for a, b in hashes).encode())


# ---------------------------------------------------------------------------------------------------- placeholders
def study1_placeholder(b: Build, which: str):
    if which == "results4":
        rel = os.path.join("data", "results4", "full", "README_PLACEHOLDER.md")
        text = """# PLACEHOLDER: Study 1 data (results4/full) are added from the author's Mac at packaging time

This directory is empty on purpose. The Study 1 run outputs live on the author's Mac
(the repository's `results4/full` folder); the builder copies them here when it is run with
`--results <path to results4/full>` (see tools/make_artifact_v2.py). Until then the Study 1 number pipeline
(`paper/latex/`) cannot be run from this artifact, and `reference_outputs/study1_analysis/` holds the author's
outputs for comparison.

Expected content, exactly as written by the registered Study 1 run (`src4/run_full.sh` through the orchestrators in
`orchestrators_as_run/`; dry-run rehearsal subfolders are optional and only used by the pipeline tests):

```
data/results4/full/
  phase1/results.csv  phase1/spend.jsonl  phase1/failures.jsonl  phase1/transcripts/*.json   (4,608 transcripts)
  phase2/results.csv  phase2/spend.jsonl  phase2/failures.jsonl  phase2/transcripts/*.json   (576 transcripts)
  phase3/results.csv  phase3/spend.jsonl  phase3/failures.jsonl  phase3/transcripts/*.json   (576 transcripts)
  preflight/ok  preflight/spend.jsonl  preflight/gemini_batch_preflight.json  preflight/gemini_batch_ok
  analysis/confirmatory.json  analysis/confirmatory.md  analysis/numbers.json  analysis/tables.md
  run.log  run_batch.log  run_dry.log  run_everything_after.log
  batch_switch_facts.json  batch_switch_facts_gemini.json  batch_switch_facts_latest.json
  phase{1,2,3}/dry_run/  preflight/dry_run/                 (optional: fake-model rehearsal, used by paper/latex/tests)
```

Transcripts include the ledgers; `batch_state/` directories (provider request/response state) are not shipped.
Licence: CC BY 4.0 (see ../../LICENSE.txt), model outputs subject to the providers' terms.
"""
    else:
        rel = os.path.join("data", "results_sql", "README_PLACEHOLDER.md")
        text = """# PLACEHOLDER: the exploratory SQL-slice results (results_sql) are added from the author's Mac at packaging time

This directory is empty on purpose. The SQL slice (post hoc, not pre-registered; code in `src_sql/`) wrote its
outputs on the author's Mac (the repository's `results_sql` folder); the builder copies them here when it is run with
`--results-sql <path to results_sql>` (see tools/make_artifact_v2.py).

Expected content:

```
data/results_sql/
  results.csv  agents.csv  spend.jsonl  run.log  preflight_ok
  transcripts/*.json                     (128 transcripts)
  dbs/*.sqlite                           (one SQLite database per episode)
  analysis/numbers.json  analysis/tables.md  analysis/tables_appendix.tex
  dry_run/                               (optional: fake-model rehearsal)
```

The Study 1 pipeline reads it through `RESULTS_SQL=<artifact>/data/results_sql` (paper/latex/posthoc_review.py,
make_numbers4.py). Licence: CC BY 4.0 (see ../LICENSE.txt), model outputs subject to the providers' terms.
"""
    b.write(rel, text.encode())


# ---------------------------------------------------------------------------------------------------- freeze checks
def freeze_check(b: Build, sub: str, label: str):
    """Rows of <out>/<sub>/FREEZE.md against the copies: (name, want, ok); override entries for redacted ones."""
    rows = A.freeze_rows(os.path.join(b.out, sub))
    if not rows:
        raise SystemExit(f"ERROR: no FREEZE.md rows under {sub}")
    changed = {c["file"]: c for c in b.changes}
    override, bad = [], []
    for name, want, ok in rows:
        if ok:
            continue
        rel = os.path.normpath(os.path.join(sub, name))
        c = changed.get(rel)
        if c is None:
            bad.append(f"{label}: frozen file {name} differs from FREEZE.md and was not redacted")
        elif c["sha_orig"] != want:
            bad.append(f"{label}: ORIGINAL {rel} does not match FREEZE.md ({c['sha_orig']} != {want})")
        else:
            override.append({"file": name, "frozen_sha256": want, "redacted_sha256": c["sha_red"],
                             "lines_changed": len(c["lines"])})
    if bad:
        raise SystemExit("ERROR: " + "\n".join(bad))
    if b.mode == "public" and override:
        raise SystemExit(f"ERROR: public mode redacted frozen files: {override}")
    return rows, override


def run_freeze5(b: Build) -> str:
    p = subprocess.run([sys.executable, "-I", os.path.join(b.out, "src5", "freeze5.py"), "--check"],
                       capture_output=True, text=True, cwd=b.out)
    return (p.stdout + p.stderr).strip()


# ---------------------------------------------------------------------------------------------------- readmes
def data_readme(b: Build, counts: dict, digests: dict, have_s1: bool, have_sql: bool) -> str:
    anon = b.mode == "anonymous"
    reg2 = "the Study 2 registration (link redacted for review)" if anon else f"the Study 2 registration ({OSF2})"
    L = [f"# Data of \"{TITLE}\"", "",
         "Licence: **CC BY 4.0** for the instances, transcripts (ledgers included), result CSVs and logs, as stated in "
         f"both registrations (`LICENSE.txt`). Model outputs inside the transcripts remain subject to the providers' terms "
         "(Anthropic, OpenAI and Alibaba Qwen through OpenRouter, Google Gemini); the Qwen model licence applies to Qwen "
         "outputs. The CC BY 4.0 terms govern; the data are intended for research use. The records are synthetic (generated "
         "names and numbers): no personal data.", "",
         "## Study 2 (`results5/study2/`)", "",
         f"The paid run of {REG2_DATE} (registered plan: {reg2}, `date_registered` {REG2_TS}; run log: "
         "`../STUDY2_RUN_LOG.md`). One directory per provider lane, exactly as written by `run_conc_study2.sh`:", "",
         "| directory | transcripts | content |", "|---|---|---|"]
    desc = {"probe-anthropic": "first-reply probes, Haiku and Sonnet (one completion per agent, nothing executed)",
            "probe-gemini": "first-reply probes, Gemini 4 Argon", "probe-openrouter": "first-reply probes, Qwen and GPT-5.5",
            "n2-anthropic": "core episodes (n = 2) Haiku, Sonnet; Fable extension block",
            "n2-gemini": "core episodes (n = 2) Gemini, aware off and on under locks/all_available",
            "n2-openrouter": "core episodes (n = 2) Qwen; GPT-5.5 core and extension blocks"}
    for lane in STUDY2_LANES:
        L.append(f"| `{lane}/` | {counts.get(lane, 0):,} | {desc[lane]}; `results.csv`, `spend.jsonl`"
                 + (", `failures.jsonl`" if os.path.isfile(os.path.join(b.out, "data", "results5", "study2", lane, "failures.jsonl")) else "")
                 + " |")
    L += ["", "Each transcript is one episode or probe: the prompts, every completion with its per-completion settings "
          "(`temperature_effective`, `model_served`, `served_host`, reasoning/thinking fields), the tool calls, the ledger "
          "and the stored score of the frozen scorer (`src5/score5.py`). `results.csv` is one row per episode; "
          "`spend.jsonl` one line per completion with cost; `failures.jsonl` provider failures that produced no episode. "
          "Extension-block rows (block priority 4) are descriptive only and enter no registered statistic.", "",
          f"Transcript list digest (the `inputs.sha256_of_list` that `analysis5/analyze5.py` records): all lanes "
          f"`{digests['all'][1]}` over {digests['all'][0]:,} files; probe lanes `{digests['probes'][1]}` over "
          f"{digests['probes'][0]:,} files. Both equal the values in `../analysis5/out_study2/results.json` and "
          "`eligibility.json`, so these are exactly the files the registered analysis read "
          f"({'checked at build' if digests.get('ok') else 'NOT CHECKED: mismatch, see BUILD_INFO.json'}).", "",
          "Also here: `summary.md` (descriptive summary written by the runner), `preflight/` (preflight spend and the Gemini "
          "batch preflight record), `validity/` (the reference-policy validity gate that ran before spending), "
          "`run_study2.log`, `lane_<provider>.log`, `validity_run.log` (the run), `summary_dry.md`, `run_study2_dry.log`, "
          "`rehearsal.log` (the no-cost rehearsal on the author's Mac before registration), `autorun_job004_s2go.log` "
          "(the queued job that started the paid run: freeze check, balance log, lanes, spend by provider) and "
          "`openrouter_balance.jsonl` (the shared key's usage before and after the OpenRouter lane, `analysis5/balance5.py`; "
          "its `raw` provider response was removed, see the top-level README).", "",
          "Not shipped: `batch_state/` (provider batch request/response state; every stored completion is in the "
          "transcripts), `held_for_pair/` (empty at the end of the run), the dry-run rehearsal transcripts (regenerate with "
          "`bash run_conc_study2.sh --dry-run`).", ""]
    L += ["## Study 1 (`results4/full/`, `results_sql/`)", ""]
    if have_s1:
        L.append("`results4/full/`: the registered Study 1 run (three phases; transcripts with ledgers, result CSVs, "
                 "failures and spend logs, preflight record, run logs), copied from the author's Mac.")
    else:
        L.append("`results4/full/` is a **placeholder** (`results4/full/README_PLACEHOLDER.md` lists the expected paths): "
                 "the Study 1 data are added from the author's Mac at packaging time.")
    if have_sql:
        L.append("`results_sql/`: the exploratory SQL slice (post hoc, not pre-registered): CSVs, transcripts, SQLite "
                 "databases and its own analysis outputs.")
    else:
        L.append("`results_sql/` is a **placeholder** (`results_sql/README_PLACEHOLDER.md`): the SQL-slice outputs are "
                 "added from the author's Mac at packaging time.")
    L += ["", "The Study 1 pipeline reads them through `RESULTS4=<artifact>/data/results4/full` and "
          "`RESULTS_SQL=<artifact>/data/results_sql` (top-level README, \"Study 1\").", ""]
    return "\n".join(L)


def cc_by_text() -> str:
    return ("Data licence: Creative Commons Attribution 4.0 International (CC BY 4.0)\n\n"
            "The instances, transcripts (ledgers included), result CSVs, spend and failure logs and run logs under this\n"
            "directory are licensed under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/legalcode\n"
            "(human-readable summary: https://creativecommons.org/licenses/by/4.0/).\n\n"
            "Attribution: cite the paper (top-level README.md, \"Cite\"). Model outputs inside the transcripts remain\n"
            "subject to the terms of the providers that produced them (Anthropic; OpenAI and Alibaba Qwen via OpenRouter;\n"
            "Google Gemini); the Qwen model licence applies to Qwen outputs. The CC BY 4.0 terms govern; the data are intended\n"
            "for research use.\n")


def top_readme(b: Build, a, fz4, fz5, ov4, ov5, freeze5_out: str, counts: dict, digests: dict, expected_ok: dict,
               have_s1: bool, have_sql: bool, wrappers_found: list, n_files: int) -> str:
    anon = b.mode == "anonymous"
    gh = a.github or "[AUTHOR: GitHub repository URL]"
    doi = a.doi or "[AUTHOR: Zenodo DOI, reserved before publishing]"
    head = [f"# Code and data: \"{TITLE}\" (Study 1 and Study 2)", ""]
    if anon:
        head += ["Anonymized for double-blind review. For review only. Author names, user names, local paths, the earlier "
                 "project name and the OSF links are redacted (ANON_CHANGES.md lists every changed line). The public "
                 "release (code MIT, data CC BY 4.0) follows the decision.", ""]
    else:
        head += [f"{AUTHOR} (independent researcher). Artifact version {a.version}. Code: MIT licence (`LICENSE`). Data: CC BY 4.0 "
                 "(`data/LICENSE.txt`), model outputs subject to the providers' terms; intended for research use.", "",
                 f"Pre-registrations: Study 1 {OSF1} (registered {REG1_DATE}); Study 2 {OSF2} (registered {REG2_DATE}, "
                 f"`date_registered` {REG2_TS}). Both texts are in `preregistration/`. "
                 + (f"This artifact is archived at https://doi.org/{a.doi}. " if a.doi
                    else "An archived copy with a DOI will be linked here when the paper is posted. ")
                 + f"Repository: {gh}.", ""]
    L = head + [
        "## What this is", "",
        "Two pre-registered studies of whether LLM agents, each in its own conversation, coordinate when they act on the "
        "same versioned records through tool calls. A seeded scheduler interleaves their calls; the coordination "
        "primitives offered (none, conditional writes, fenced locks, both) and the prompt's mention of other agents are "
        "varied; scoring is deterministic from the ledger and the server call log (no LLM judge). Study 1 is the first "
        "run (frozen harness `src4/`). Four hard reviews of it found harness design flaws (`CHANGES_V2.md`), so Study 2 "
        "re-ran a corrected harness (`src5/`) with matched uncontended controls, fenced locks and first-reply probes, "
        "under a second registration. Study 1 is reported with its deviations; Study 2 carries the registered confirmatory tests of the corrected design.", "",
        "## Layout", "",
        "| path | what it is |", "|---|---|",
        "| `src4/` | Study 1 frozen harness and its confirmatory analysis (`analyze4.py`); `FREEZE.md` lists the 20 frozen sha256 |",
        "| `src4_batch/` | Study 1 batch drivers (Sonnet 5, Fable 5, Gemini 4 Argon episodes) and their offline tests (not frozen) |",
        "| `src_sql/` | the exploratory SQL slice of Study 1 (post hoc, not pre-registered) |",
        "| `orchestrators_as_run/` | the orchestrator scripts exactly as run on the author's Mac for Study 1, with their own `SHA256SUMS` and README |",
        "| `paper/latex/` | " + ("the source of the paper (`main.tex`, `study2.tex`, `study2_prompts.tex`) and of its supplement "
                                 "(`supplement.tex`, `study2_analysis.tex`, `study1_full.tex`, `supp_study1.tex`, `supp_db_sql.tex`, "
                                 "`supp_extended.tex`), the shared preamble (`preamble_shared.tex`), `study2_constants.tex`, `refs.bib`, "
                                 "the ACL style files" + ("" if anon else ", `identity.tex`") + ", "
                                 "`check_model_macros.py` (every model-named number macro belongs to the model its sentence names), the generated "
                                 "inputs it compiles from (`numbers.tex`, `tables/`, `figures/`, `study2_out/`: the Study 2 tables, figures and "
                                 "macros written by `analysis5/descriptives5.py`), the fact sheets (`facts/src/`), "
                                 if a.with_paper_source else "")
        + "the Study 1 number pipeline: every script that produces a Study 1 number, its tests, `deviations.csv`, `build.sh`"
        + ("" if a.with_paper_source else "; the paper source and PDF are not in this artifact (the paper is the preprint cited below)") + " |",
        ("| `paper/paper_" + b.mode + ".pdf`, `paper/supplement_" + b.mode + ".pdf` | the compiled paper and its supplement of the build this "
         "artifact was made from" + (" (anonymous build: no author line, registration links withheld, the self-citation anonymized)" if anon else " (named preprint build)")
         + "; the tables the paper cites as \"Supplement Table S...\" (every registered Study 2 test, the per-family and per-cell "
         "tables, the mechanism tables, the Firth regression, Study 1 in full, the H5 audit, the SQL slice) are in the supplement, "
         "and the paper's appendix holds the Study 2 deviations, prompts and cited tables |")
        if os.path.isfile(os.path.join(b.out, "paper", f"paper_{b.mode}.pdf")) else "| `paper/` | (no compiled paper in this build) |",
        "| `paper/audit/` | the pre-specified H5 transcript audit of Study 1 (performed by an AI agent) and the scoring spot-checks |",
        "| `preregistration/` | the two registration texts: `PREREGISTRATION.md` (Study 1) and `PREREGISTRATION_STUDY2.md` (Study 2); `paper/PREREGISTRATION.md` is the copy the pipeline reads |",
        "| `src5/`, `src5_batch/`, `src5_verify/`, `run_conc_study2.sh` | Study 2 frozen harness, batch layer, verification tools and runner: `src5/FREEZE.md` lists all 38 frozen sha256 (`src5/*.py`, `*.json`, `src5_batch/*.py`, `*.json`, `*.sh`, `src5_verify/dry_check5.py`, `run_conc_study2.sh`); `src5_verify/mutate5.py` and `mut5.json` (mutation testing) are not frozen |",
        "| `run_conc_s2go.sh`, `run_conc_s2dry.sh`, `run_conc_elig.sh` | **non-frozen wrappers**, as run on the Mac: the paid run with the balance log around it, the no-cost rehearsal with the paid interpreter, and the eligibility step. Not in `FREEZE.md`; their hashes are in `SHA256SUMS` |",
        "| `analysis5/` | Study 2 analysis: `analyze5.py` (frozen, registered: eligibility, the confirmatory tests, checks, H4b, budget report, sensitivities 1 to 9), `descriptives5.py` (pre-specified descriptive tables and figures; no test), `balance5.py`, `tests_analyze5.py`, `PREREG_GAPS.md`, `power_sims/` (registered power simulations), `testdata/`, `out/` (the registered dry-run outputs), `out_study2/` (`eligibility.json`, `results.json`, `numbers.tex` of the registered run) |",
        "| `CHANGES_V2.md` | every pre-spend review blocker, its fix and the test that proves it (Rounds 1 to 5) |",
        "| `STUDY2_RUN_LOG.md` | the paid-run log: gates, deviations, cost, the eligibility step, the final counts and the post-run checks |",
        "| `osf_registration_records.md` | both OSF registrations as recorded at the time: identifier, `date_registered`, embargo end, sha256 and location of the registered text, the eligibility file's upload time (checkable without lifting the embargo) |",
        "| `data/` | Study 2 data (`data/results5/study2/`) and the Study 1 data directories (`data/results4/full/`, `data/results_sql/`): see `data/README.md` |",
        "| `reference_outputs/study1_analysis/` | the author's Study 1 analysis outputs, to compare against a rerun |",
        "| `FREEZE_OVERRIDE.json` | the documented FREEZE override for redacted frozen files (empty in the public build; see below) |",
        "| `SHA256SUMS`, `BUILD_INFO.json` | sha256 of every shipped file (`sha256sum -c SHA256SUMS`, on macOS `shasum -a 256 -c SHA256SUMS`); how and when this artifact was built and which checks passed |",
    ]
    if not anon:
        L.append("| `tools/` | `make_artifact_v2.py` (built this artifact; its docstring lists every inclusion, exclusion and edit), `make_anon_artifact.py` (identity rules of the review build), `compare_json.py` |")
    if os.path.isfile(os.path.join(b.out, ".study2_registered")):
        L.append("| `.study2_registered` | the marker written on the Mac after the OSF registration was confirmed; `run_conc_s2go.sh` and `run_conc_elig.sh` refuse to run without it |")
    L += ["", "## Frozen and registered hashes", "",
          f"`src4/FREEZE.md`: {sum(ok for _, _, ok in fz4)}/{len(fz4)} files verify in this copy"
          + (f" ({len(ov4)} redacted, via the documented override)" if ov4 else "") + ". "
          f"`src5/FREEZE.md`: {sum(ok for _, _, ok in fz5)}/{len(fz5)} files verify"
          + (f" ({len(ov5)} redacted; `src5/freeze5.py --check` reports them, see the override section)" if ov5 else "")
          + f". `python3 -I src5/freeze5.py --check` inside this copy printed: `{freeze5_out}`.", "",
          "Registered sha256 (Study 2 registration, \"Freeze\"; `STUDY2_RUN_LOG.md`), each checked against the copy at build time:", "",
          "| file | sha256 | in this copy |", "|---|---|---|"]
    for k, v in EXPECTED.items():
        st = expected_ok.get(k)
        L.append(f"| `{k}` | `{v}` | {'verifies' if st is True else ('redacted (ANON_CHANGES.md)' if anon and st is False else 'DIFFERS')} |")
    L += ["", f"The eligibility file's sha256 (`{ELIG_SHA}`) was posted to the OSF project before any episode result was "
          "opened (`STUDY2_RUN_LOG.md`, \"ELIGIBILITY STEP\"); `analyze5.py analyze` refuses to run unless the eligibility "
          "file it is given has that hash.", "",
          "## Reproduce Study 2 from the shipped transcripts", "",
          "Requirements: Python 3.10 or later (the runs used 3.13); the harness and the registered analysis are standard "
          "library only. `matplotlib` for `descriptives5.py` and the Study 1 figures; the `anthropic` SDK (2.3.0 was used) "
          "for the batch path and its tests; `numpy` and `scipy` only for `analysis5/power_sims/`. Run from the artifact root.", "",
          "```", "# 1. eligibility from the probe transcripts only (must print sha256 " + ELIG_SHA + ")",
          "python3 -I analysis5/analyze5.py eligibility --base data/results5/study2 --out analysis5/out_rerun", "",
          "# 2. the registered analysis (54 tests, about 30 s); refuses unless --eligibility has the posted sha256",
          "python3 -I analysis5/analyze5.py analyze --base data/results5/study2 \\",
          "    --eligibility analysis5/out_study2/eligibility.json \\",
          f"    --eligibility-sha256 {ELIG_SHA} \\",
          "    --out analysis5/out_rerun", "",
          "# 3. compare with the shipped outputs: numbers.tex is byte-identical; results.json is equal up to float",
          "#    summation noise (about 1e-13, platform dependent: the registered run was on macOS)",
          "cmp analysis5/out_rerun/numbers.tex analysis5/out_study2/numbers.tex",
          ("python3 -I tools/compare_json.py analysis5/out_rerun/results.json analysis5/out_study2/results.json"
           if not anon else "diff <(python3 -m json.tool analysis5/out_rerun/results.json) <(python3 -m json.tool analysis5/out_study2/results.json)"), "",
          "# 4. pre-specified descriptive tables and figures (matplotlib), no test; deterministic",
          "python3 -I analysis5/descriptives5.py --base data/results5/study2 --results analysis5/out_study2/results.json \\",
          "    --numbers analysis5/out_study2/numbers.tex --plan src5/plan_study2.json --out study2_out --facts study2_out/facts.md", "",
          "# 5. the 24-call sensitivity re-score from the logged ledgers (also inside analyze5, sensitivity 1; no -I:",
          "#    rescore5 imports its siblings from the script directory)",
          "python3 src5/rescore5.py --cap 24 --out cap24.csv data/results5/study2/n2-*/transcripts", "```", "",
          "`analysis5/out_study2/` is the author's run of exactly these commands on the Mac (see the hash table). "
          "Scores and ledgers are reproducible from the transcripts with the frozen scorer; the model outputs are not: "
          "re-running the harness is a new data collection.", "",
          "### Tests", "", "```",
          "cd src5 && python3 -m unittest tests5 && cd ..                       # 91 harness tests, about 6 s",
          "cd src5_batch && python3 -m unittest tests_batch tests_gemini && cd ..   # 59 batch-path tests incl. the equivalence gate; needs the anthropic SDK; ~17 min",
          "python3 src5/validity5.py --out validity_rerun                           # reference-policy validity table (372 rows, 0 required failures; ~3 min)",
          "bash run_conc_study2.sh --dry-run --base results5/study2_dry             # whole grid with fake models, no keys, no money (needs the anthropic SDK importable); then dry_check5",
          "A5_DRY_BASE=results5/study2_dry PYTHONDONTWRITEBYTECODE=1 python3 analysis5/tests_analyze5.py   # 46 analysis tests (end to end on that dry run; writes analysis5/out/)",
          "python3 src5_verify/mutate5.py                                           # mutation testing (124 mutants; SRC5_DIR=$PWD/src5)",
          "```", "",
          "`tests_analyze5.py` needs a dry run of the final harness (`A5_DRY_BASE`); it rewrites `analysis5/out/`, whose "
          "shipped content is the registered dry-run output (hashes in `SHA256SUMS`). `tests_batch`/`tests_gemini` and the "
          "mutation run take long; the Study 2 registration lists the counts they produced.", "",
          "## Re-run the harness", "",
          "**Dry run (no keys, no money; about 10 minutes).** `bash run_conc_study2.sh --dry-run --base results5/study2_dry` "
          "runs the freeze check, the validity gate, fake preflights, the whole registered grid with fake models that lock "
          "and message, the channel rehearsal and `src5_verify/dry_check5.py` (5,160 transcripts, 1,180 matched pairs; it "
          "needs the `anthropic` SDK importable even though nothing is sent). `run_conc_s2dry.sh` is the wrapper that did this on the "
          "Mac with the paid interpreter (`.venv/bin/python`).", "",
          "**Paid run.** Create `.env` with `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, then "
          "`bash run_conc_study2.sh` (or `bash run_conc_s2go.sh`, which also logs the OpenRouter key balance before and "
          "after and refuses to start without `.study2_registered`). The script refuses to start if any frozen file "
          "differs from `src5/FREEZE.md` or the validity gate fails; it spends at most the per-provider caps in its header "
          "(Anthropic $19, OpenRouter $28, Gemini $22, total $69; the registered run spent $46.40). Haiku, Sonnet and Fable "
          "run through the Anthropic Message Batches API, Gemini through the Google Batch API, Qwen and GPT-5.5 sync "
          "through OpenRouter (Qwen pinned to the Alibaba host). Model versions and prices move: a new run is a new study, "
          "not a reproduction of this one. The eligibility step between the probe block and the analysis is "
          "`run_conc_elig.sh`.", "",
          "## Study 1", "",
          ("The Study 1 data are in `data/results4/full/` and `data/results_sql/`. The" if have_s1 and have_sql else
           "The Study 1 data directories are placeholders in this build (`data/results4/full/README_PLACEHOLDER.md`, "
           "`data/results_sql/README_PLACEHOLDER.md`): they are added from the author's Mac at packaging time, after which the") +
          " Study 1 pipeline runs as on the build machine, with the data location given explicitly:", "",
          "```", "export RESULTS4=$PWD/data/results4/full RESULTS_SQL=$PWD/data/results_sql", "cd paper/latex",
          "python3 run_analysis.py --out ../analysis            # verifies src4/FREEZE.md, runs the frozen src4/analyze4.py (confirmatory)",
          "python3 explore4.py --analysis ../analysis           # EXPLORATORY analyses from saved CSVs and transcripts",
          "python3 rollback_sensitivity.py --analysis ../analysis   # POST HOC rollback rescoring + H5 audit counts",
          "python3 posthoc_review.py --analysis ../analysis     # POST HOC review analyses (saved data only)",
          "python3 reference_policies.py --analysis ../analysis # POST HOC scripted reference agents (no model calls)",
          "cd ../../src4 && python3 -m unittest tests4 tests_full4 tests_model4   # harness tests",
          "```", "",
          "`confirmatory.json` should equal `reference_outputs/study1_analysis/confirmatory.json` except for the input "
          "paths. `make_numbers4.py --check` and `paper/latex/tests/` also need the paper source (`main.tex`, "
          "`facts/`)" + (", which this artifact ships" if a.with_paper_source else ", which is not in this artifact") + ". Study 1 harness tests in "
          "`src4_batch/` import the frozen harness through `src4_batch/frozen.py`, whose own FREEZE gate does not read "
          "`FREEZE_OVERRIDE.json`"
          + ("; they pass on this unredacted copy." if not anon else "; on this redacted copy they fail on the five redacted frozen files and pass on the unredacted release.") + "", "",
          "## FREEZE override", "",
          "`FREEZE_OVERRIDE.json` is the documented mechanism of the review build: a frozen file that had to be redacted "
          "for anonymity is listed with its FREEZE.md hash (equal to the sha256 of the original, checked when the artifact "
          "was built) and the sha256 of the redacted copy; `paper/latex/pipeline_common.py` accepts exactly those bytes "
          "and nothing else. " + ("In this public build nothing is redacted and the list is empty: every frozen file matches "
                                  "its FREEZE.md hash." if not anon else
                                  f"In this review build {len(ov4)} src4 and {len(ov5)} src5 frozen files are redacted "
                                  "(table below and ANON_CHANGES.md). `src5/freeze5.py` and the batch driver do not read "
                                  "the override, so `run_conc_study2.sh` refuses to start on this copy by design; "
                                  "`analysis5/analyze5.py` does not need the freeze and reproduces every number."), ""]
    if ov4 or ov5:
        L += ["| file | FREEZE.md sha256 = original sha256 | redacted sha256 |", "|---|---|---|"]
        L += [f"| `src4/{e['file']}` | `{e['frozen_sha256']}` | `{e['redacted_sha256']}` |" for e in ov4]
        L += [f"| `src5/{e['file']}` | `{e['frozen_sha256']}` | `{e['redacted_sha256']}` |" for e in ov5]
        L.append("")
    L += ["## Edits made by the builder", ""]
    L += [f"- {n}" for n in b.notes] or ["- none"]
    L += ["", "Excluded: `batch_state/` and `held_for_pair/` directories, `__pycache__`, `.env`, the dry-run rehearsal "
          "transcripts, the build logs"
          + (", `paper/latex/identity.tex` (the author line and registration identifiers of the named build)" if anon and a.with_paper_source else "")
          + (", the paper source and PDF" if not a.with_paper_source else "")
          + ", and the AI pre-submission and pre-spend review documents (R1 to R3, T1 to T8, T3b, T3c, T7b, T8b, T8c, "
          "V1, V1b, V2 and V2b: AI-generated, in-pipeline checks, not peer review).", "",
          "## AI use", "",
          "This work was AI-assisted: Claude models (Anthropic, which also provides three of the six evaluated models) "
          "assisted under the author's direction and review. The author chose the research question, scope and budget, "
          "reviewed and approved the designs, hypotheses and analysis plans, filed both registrations under her own "
          "account and ran the experiments on her machine with her API credit (the Study 2 run was started by a queued "
          "job on her Mac after the registration was filed; `STUDY2_RUN_LOG.md`). The paper's Acknowledgments carry its "
          "AI-use statement.", "",
          "## Cite", ""]
    if anon:
        L += ["Anonymous. \"" + TITLE + "\" Under review. (Citation details are added at camera-ready.)", ""]
    else:
        where = (f"https://doi.org/{a.doi} and {gh}" if a.doi else gh)
        pre = "Preprint" if a.doi else "Preprint, forthcoming"
        L += ["```", f"{AUTHOR_CITED}. {TITLE_FULL}. {a.year}. {pre}. Code and data: {where}", "```", "",
              "```bibtex", "@misc{gopnalswamy" + a.year + "coordinate,",
              f"  author       = {{{AUTHOR_CITED}}},", f"  title        = {{{TITLE_FULL}}},", f"  year         = {{{a.year}}},",
              f"  howpublished = {{{pre}}},",
              f"  note         = {{Code and data: {where}; pre-registrations {OSF1} and {OSF2}}}", "}", "```", ""]
    L += [f"Built {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')} (UTC) by `tools/make_artifact_v2.py` ({b.mode} mode); "
          f"{n_files:,} files. Study 2 transcripts: " + ", ".join(f"{k} {v:,}" for k, v in counts.items()) + "."
          + (" Wrappers included: " + ", ".join(wrappers_found) + "." if wrappers_found else " WARNING: no wrapper scripts found."), ""]
    return "\n".join(L)


def anon_changes(b: Build, a, fz4, fz5, ov4, ov5) -> str:
    changed_files = {c["file"] for c in b.changes}
    L = ["# ANON_CHANGES: identity redactions in this artifact", "",
         "Every change made to the copied files is listed below. Only identifying strings were replaced (author name, "
         "user names, home and Desktop paths, the project name of the author's earlier work, e-mail addresses, the OSF "
         "registration identifiers). Each changed line is shown as it appears in the artifact; the replacement tokens "
         "(ANON_*, AnonBench, anonbench, anon@example.org, [REDACTED FOR REVIEW], [OSF ... REDACTED FOR REVIEW]) mark "
         "exactly what changed. No other byte differs, except the builder edits listed in README.md.", "",
         "FREEZE.md files list sha256 hashes of the UNREDACTED files, as registered. Files without redactions verify "
         "against them unchanged; redacted files differ only in the lines listed here. For every redacted frozen file the "
         "original was checked against its FREEZE.md hash when this artifact was built (FREEZE_OVERRIDE.json). The "
         "unredacted files are released at camera-ready.", "",
         f"Pre-registrations: OSF, Study 1 registered {REG1_DATE}, Study 2 registered {REG2_DATE}. The OSF pages are not "
         "linked during review because their text names the author; preregistration/ holds the registered texts with "
         "the author lines redacted. The links are added at camera-ready.", "",
         f"Files copied: {len(b.copied)}; files with redactions: {len(b.changes)}.", ""]
    for title, rows in (("src4", fz4), ("src5", fz5)):
        L += [f"## FREEZE.md check of the copied {title}", "", "| file | frozen sha256 | copy verifies |", "|---|---|---|"]
        for name, want, ok in rows:
            rel = os.path.normpath(os.path.join(title, name))
            why = "yes" if ok else ("no: redacted (lines below); original verified; in FREEZE_OVERRIDE.json"
                                    if rel in changed_files else "NO")
            L.append(f"| `{name}` | `{want}` | {why} |")
        L.append("")
    L += ["## Changed files", ""]
    for c in b.changes:
        L += [f"### `{c['file']}`", "", f"- sha256 original: `{c['sha_orig']}`", f"- sha256 redacted: `{c['sha_red']}`",
              f"- lines changed: {len(c['lines'])}", ""]
        for i, line, hits in c["lines"]:
            L.append(f"    L{i} [{', '.join(sorted(set(hits)))}]: {line.strip()[:300]}")
        L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="artifact directory (its basename is the top-level folder inside the zip)")
    ap.add_argument("--zip", help="zip file to write (default: <out>.zip; 'none' to skip)")
    ap.add_argument("--mode", choices=("public", "anonymous"), default="public")
    ap.add_argument("--results", help="Study 1 results4/full to include (else a placeholder README)")
    ap.add_argument("--results-sql", help="Study 1 results_sql to include (else a placeholder README)")
    ap.add_argument("--study1-analysis", default=STUDY1_ANALYSIS, help="author's Study 1 analysis outputs ('none' to skip)")
    ap.add_argument("--study2-data", default=DEF_STUDY2_DATA, help="results5/study2 of the paid run")
    ap.add_argument("--study2-analysis", default=DEF_STUDY2_OUT, help="analysis5/out_study2 of the registered run")
    ap.add_argument("--registered-marker", default=DEF_REGISTERED, help=".study2_registered (public mode only)")
    ap.add_argument("--autorun-log", default=DEF_AUTORUN_LOG, help="the queued job's log of the paid run")
    ap.add_argument("--wrappers", nargs="*", default=list(DEF_WRAPPER_DIRS), help="dirs searched for the wrapper scripts")
    ap.add_argument("--with-paper-source", dest="with_paper_source", action="store_true", default=True,
                    help="ship the paper source, its generated inputs, the fact sheets and the compiled PDF (default)")
    ap.add_argument("--no-paper-source", dest="with_paper_source", action="store_false", help="omit the paper source and the PDF")
    ap.add_argument("--github", default=None)
    ap.add_argument("--doi", default=None)
    ap.add_argument("--version", default="v2")
    ap.add_argument("--year", default="2026")
    ap.add_argument("--allow-hash-mismatch", action="store_true", help="public mode: warn instead of refusing on a registered-hash mismatch")
    ap.add_argument("--scan-only", nargs="+", metavar="PATH")
    a = ap.parse_args(argv)
    if a.scan_only:
        for fp, i, m, line in A.scan_paths(a.scan_only):
            print(f"{fp}:{i}: [{m}] {line}")
        return 0
    if not a.out:
        ap.error("--out is required")
    out = os.path.abspath(a.out)
    protected = [os.path.abspath(p) for p in (A.SRC4, SRC5, SRC5_BATCH, SRC5_VERIFY, ANALYSIS5, A.LATEX, a.study2_data)]
    for p in protected:
        if out == p or out.startswith(p + os.sep) or p.startswith(out + os.sep):
            raise SystemExit(f"REFUSING: output {out} overlaps a source folder ({p})")
    if out in (ROOT, HERE) or HERE.startswith(out + os.sep):
        raise SystemExit(f"REFUSING: output {out} would contain the paper folder")
    if os.path.isdir(out) and os.listdir(out) and not os.path.exists(os.path.join(out, "BUILD_INFO.json")):
        raise SystemExit(f"REFUSING: {out} exists, is not empty and is not a previous artifact")
    for p, what in ((a.study2_data, "Study 2 data"), (a.study2_analysis, "Study 2 analysis outputs"), (SRC5, "src5"),
                    (A.SRC4, "src4"), (ANALYSIS5, "analysis5"), (ORCH, "orchestrators_as_run")):
        if not os.path.isdir(p):
            raise SystemExit(f"ERROR: {what} not found at {p}")
    watched = {k: tree_hashes(k) for k in (A.SRC4, SRC5, SRC5_BATCH, SRC5_VERIFY, ANALYSIS5)}
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    b = Build(out, a.mode)

    # --- Study 1 (as in make_anon_artifact.py) + orchestrators
    b.walk(A.SRC4, "src4")
    for src_dir, name in ((A.SRC4_BATCH, "src4_batch"), (A.SRC_SQL, "src_sql"), (ORCH, "orchestrators_as_run")):
        if os.path.isdir(src_dir):
            b.walk(src_dir, name)
        else:
            b.warnings.append(f"{name} not found at {src_dir}")
    for rel in (os.path.join("preregistration", "PREREGISTRATION.md"), os.path.join("paper", "PREREGISTRATION.md")):
        b.copy_optional(A.PREREG, rel, "Study 1 registration")
    latex_files = [f for f in A.LATEX_FILES if f not in PAPER_SOURCE]
    if a.with_paper_source:
        latex_files += [f for f in PAPER_TEX if f not in latex_files] + list(PAPER_FACTS)
        if a.mode == "public":
            latex_files.append(PAPER_IDENTITY)
    for f in latex_files:
        src = os.path.join(A.LATEX, f)
        rel = os.path.join("paper", "latex", f)
        if a.mode == "anonymous" and f == "refs.bib" and os.path.isfile(src):
            # the self-citation names the author: replace the entry as latex/build.sh --anonymous does, then the line rules
            text = open(src, encoding="utf-8").read()
            text2 = re.sub(r"@misc\{anon2027retries,.*?\n\}", ANON_BIB_ENTRY, text, count=1, flags=re.S)
            if text2 != text:
                b.notes.append("`paper/latex/refs.bib`: the self-citation entry `anon2027retries` was replaced by "
                               "`Anonymous. Concurrent submission.` (as `latex/build.sh --anonymous` does).")
            lines = text2.split("\n")
            new, changed = [], []
            for i, line in enumerate(lines, 1):
                r, hits = b.redact(line, b.rules)
                new.append(r)
                if hits:
                    changed.append((i, r, hits))
            out_b = "\n".join(new).encode("utf-8")
            b.write(rel, out_b, os.stat(src).st_mode)
            if changed:
                b.changes.append({"file": rel, "sha_orig": sha(text.encode("utf-8")), "sha_red": sha(out_b), "lines": changed})
            continue
        b.copy_optional(src, rel, f"paper/latex/{f}")
    for d in A.LATEX_DIRS + (PAPER_DIRS if a.with_paper_source else ()):
        if os.path.isdir(os.path.join(A.LATEX, d)):
            b.walk(os.path.join(A.LATEX, d), os.path.join("paper", "latex", d))
    if a.with_paper_source:
        pdf = os.path.join(A.LATEX, "build", PAPER_PDF[a.mode])
        if os.path.isfile(pdf):
            b.copy_file(pdf, os.path.join("paper", f"paper_{a.mode}.pdf"))
        else:
            b.warnings.append(f"compiled paper {pdf} not found; run latex/build.sh first")
        spdf = os.path.join(A.LATEX, "build", SUPP_PDF[a.mode])
        if os.path.isfile(spdf):
            b.copy_file(spdf, os.path.join("paper", f"supplement_{a.mode}.pdf"))
        else:
            b.warnings.append(f"compiled supplement {spdf} not found; run latex/build.sh first")
    for f in A.AUDIT_FILES:
        b.copy_optional(os.path.join(A.AUDIT, f), os.path.join("paper", "audit", f), f"audit/{f}")
    have_s1 = bool(a.results and os.path.isdir(a.results))
    have_sql = bool(a.results_sql and os.path.isdir(a.results_sql))
    # public mode: the Study 1 run logs carry local paths of the author's machine; scrub those lines as for Study 2
    s1_log_rules = PATH_RULES if a.mode == "public" else None
    if have_s1:
        b.walk(a.results, os.path.join("data", "results4", "full"), log_rules=s1_log_rules)
    else:
        study1_placeholder(b, "results4")
    if have_sql:
        b.walk(a.results_sql, os.path.join("data", "results_sql"), log_rules=s1_log_rules)
    else:
        study1_placeholder(b, "results_sql")
    if a.study1_analysis != "none" and os.path.isdir(a.study1_analysis):
        b.walk(a.study1_analysis, os.path.join("reference_outputs", "study1_analysis"))

    # --- Study 2 code
    b.walk(SRC5, "src5")
    b.walk(SRC5_BATCH, "src5_batch")
    b.walk(SRC5_VERIFY, "src5_verify")
    b.copy_optional(RUN_S2, "run_conc_study2.sh", "run_conc_study2.sh")
    wrappers_found = []
    for w in WRAPPERS:
        for d in a.wrappers:
            p = os.path.join(d, w)
            if os.path.isfile(p):
                b.copy_file(p, w)
                wrappers_found.append(w)
                break
        else:
            b.warnings.append(f"wrapper {w} not found in {a.wrappers}")
    for f in ANALYSIS5_FILES:
        b.copy_optional(os.path.join(ANALYSIS5, f), os.path.join("analysis5", f), f"analysis5/{f}")
    for d in ANALYSIS5_DIRS:
        if os.path.isdir(os.path.join(ANALYSIS5, d)):
            b.walk(os.path.join(ANALYSIS5, d), os.path.join("analysis5", d))
    for f in STUDY2_OUT_FILES:
        b.copy_optional(os.path.join(a.study2_analysis, f), os.path.join("analysis5", "out_study2", f), f"out_study2/{f}")
    b.copy_optional(CHANGES_V2, "CHANGES_V2.md", "CHANGES_V2.md")
    b.copy_optional(RUN_LOG, "STUDY2_RUN_LOG.md", "STUDY2_RUN_LOG.md")
    b.copy_optional(PREREG2, os.path.join("preregistration", "PREREGISTRATION_STUDY2.md"), "Study 2 registration")
    b.copy_optional(OSF_RECORDS, "osf_registration_records.md", "osf_registration_records.md")
    if a.mode == "public" and os.path.isfile(a.registered_marker):
        b.copy_file(a.registered_marker, ".study2_registered")
    if a.mode == "public":
        for t in TOOLS:
            b.copy_optional(os.path.join(HERE, t), os.path.join("tools", os.path.basename(t)), t)

    # --- Study 2 data
    counts = copy_study2_data(b, a.study2_data, a.autorun_log)
    if a.mode == "public":
        scrubbed = [c["file"] for c in b.changes]
        if scrubbed:
            b.notes.append("Local filesystem paths of the author's machine (log and traceback lines) were replaced by the "
                           "make_anon_artifact.py path tokens in: " + ", ".join(f"`{f}`" for f in scrubbed) + "; "
                           f"{sum(len(c['lines']) for c in b.changes)} line(s) in all, listed in BUILD_INFO.json.")
    data_base = os.path.join(out, "data", "results5", "study2")
    digests = {"all": transcript_list_digest(data_base, False), "probes": transcript_list_digest(data_base, True)}
    with open(os.path.join(out, "analysis5", "out_study2", "results.json")) as f:
        want_all = json.load(f)["inputs"]["sha256_of_list"]
    with open(os.path.join(out, "analysis5", "out_study2", "eligibility.json")) as f:
        want_pr = json.load(f)["inputs"]["sha256_of_list"]
    digests["ok"] = digests["all"][1] == want_all and digests["probes"][1] == want_pr
    if not digests["ok"]:
        msg = (f"shipped transcript list digest {digests['all'][1]} / {digests['probes'][1]} != results.json "
               f"{want_all} / eligibility.json {want_pr}")
        if a.mode == "public" and not a.allow_hash_mismatch:
            raise SystemExit("ERROR: " + msg)
        b.warnings.append(msg)

    # --- licences and data README
    holder = AUTHOR if a.mode == "public" else "the author(s)"
    b.write("LICENSE", MIT.format(holder=holder).encode())
    b.write(os.path.join("data", "LICENSE.txt"), cc_by_text().encode())
    b.write(os.path.join("data", "README.md"), data_readme(b, counts, digests, have_s1, have_sql).encode())

    # --- freeze checks and the override
    fz4, ov4 = freeze_check(b, "src4", "src4")
    fz5, ov5 = freeze_check(b, "src5", "src5")
    freeze5_out = run_freeze5(b)
    if a.mode == "public" and not freeze5_out.startswith("FREEZE OK"):
        raise SystemExit(f"ERROR: src5/freeze5.py --check failed in the copy:\n{freeze5_out}")
    with open(os.path.join(out, "FREEZE_OVERRIDE.json"), "w") as f:
        json.dump({"note": "Documented FREEZE override. Frozen files redacted for anonymity are listed with frozen_sha256 "
                           "(= the FREEZE.md hash = the sha256 of the original file, checked at build time) and "
                           "redacted_sha256 (the copy here). paper/latex/pipeline_common.py accepts exactly these bytes for "
                           "src4 files. src5/freeze5.py and the batch driver do not read this file. Empty lists: nothing "
                           "was redacted (public build). Changed lines: ANON_CHANGES.md.",
                   "mode": a.mode, "redacted_frozen_files": ov4, "redacted_frozen_files_study2": ov5}, f, indent=1)
        f.write("\n")
    b.copied.append("FREEZE_OVERRIDE.json")
    expected_ok = {}
    for rel, want in EXPECTED.items():
        p = os.path.join(out, rel)
        got = sha_file(p) if os.path.isfile(p) else None
        expected_ok[rel] = got == want
        if got != want:
            redacted = rel in {c["file"] for c in b.changes}
            msg = f"registered hash of {rel}: copy {got} != registered {want}" + (" (redacted)" if redacted else "")
            if a.mode == "public" and not a.allow_hash_mismatch:
                raise SystemExit("ERROR: " + msg)
            b.warnings.append(msg)
    orch_ok = None
    sums = os.path.join(out, "orchestrators_as_run", "SHA256SUMS")
    if os.path.isfile(sums):
        orch_ok = True
        for line in open(sums):
            m = re.match(r"^([0-9a-f]{64})\s+\./(.+)$", line.strip())
            if m and sha_file(os.path.join(out, "orchestrators_as_run", m.group(2))) != m.group(1):
                orch_ok = False
                b.warnings.append(f"orchestrators_as_run/{m.group(2)} differs from its SHA256SUMS entry")

    # --- README, ANON_CHANGES, BUILD_INFO, SHA256SUMS
    if a.mode == "anonymous":
        b.write("ANON_CHANGES.md", anon_changes(b, a, fz4, fz5, ov4, ov5).encode())
    n_files = len(b.copied) + 3  # + README.md, BUILD_INFO.json, SHA256SUMS
    b.write("README.md", top_readme(b, a, fz4, fz5, ov4, ov5, freeze5_out, counts, digests, expected_ok, have_s1,
                                    have_sql, wrappers_found, n_files).encode())
    for k, before in watched.items():
        if tree_hashes(k) != before:
            raise SystemExit(f"ERROR: {k} changed during the copy")
    info = {"artifact": os.path.basename(out), "mode": a.mode, "version": a.version,
            "built_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "python": platform.python_version(), "builder": "paper-concurrency/make_artifact_v2.py",
            "sources": {"src4": A.SRC4, "src5": SRC5, "study2_data": os.path.abspath(a.study2_data),
                        "study2_analysis": os.path.abspath(a.study2_analysis), "results4": a.results, "results_sql": a.results_sql},
            "checks": {"src4_freeze": f"{sum(ok for _, _, ok in fz4)}/{len(fz4)}", "src5_freeze": f"{sum(ok for _, _, ok in fz5)}/{len(fz5)}",
                       "freeze5_check": freeze5_out, "registered_hashes": expected_ok,
                       "transcript_list_digest_matches_results_json": digests["ok"],
                       "transcript_list_digest": {"all": digests["all"], "probes": digests["probes"]},
                       "orchestrators_sha256sums_verify": orch_ok, "sources_unchanged_during_copy": True},
            "study2_transcripts": counts, "override": {"src4": ov4, "src5": ov5}, "wrappers": wrappers_found,
            "builder_edits": b.notes, "warnings": b.warnings,
            "changed_lines": [{"file": c["file"], "sha_orig": c["sha_orig"], "sha_new": c["sha_red"],
                               "lines": [[i, sorted(set(h))] for i, _, h in c["lines"]]} for c in b.changes]}
    text = json.dumps(info, indent=1) + "\n"
    if a.mode == "anonymous":  # source paths name the build machine's user: same rules as every text file
        text = "\n".join(b.redact(line, b.rules)[0] for line in text.split("\n"))
    b.write("BUILD_INFO.json", text.encode())
    rows = []
    for rel in sorted(set(b.copied)):
        rows.append(f"{sha_file(os.path.join(out, rel))}  {rel}")
    with open(os.path.join(out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(rows) + "\n")
    if a.mode == "anonymous":
        left = A.scan_paths([out])
        bad = [h for h in left if not h[0].endswith("ANON_CHANGES.md")]
        for fp, i, m, line in bad:
            print(f"IDENTITY STRING LEFT: {fp}:{i}: [{m}] {line}")
        if bad:
            return 1

    # --- zip
    zpath = None
    if a.zip != "none":
        zpath = os.path.abspath(a.zip) if a.zip else out.rstrip(os.sep) + ".zip"
        top = os.path.basename(out.rstrip(os.sep))
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for d, dirs, files in os.walk(out):
                dirs.sort()
                for fn in sorted(files):
                    p = os.path.join(d, fn)
                    z.write(p, os.path.join(top, os.path.relpath(p, out)))
    for w in b.warnings:
        print(f"WARNING: {w}")
    print(f"artifact: {out} ({len(rows) + 1} files, {len(b.changes)} files with changed lines, mode {a.mode}); "
          f"src4 freeze {info['checks']['src4_freeze']}, src5 freeze {info['checks']['src5_freeze']}; {freeze5_out}; "
          f"transcript digests match results.json: {digests['ok']}"
          + (f"; zip: {zpath} ({os.path.getsize(zpath) / 1e6:.1f} MB)" if zpath else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
