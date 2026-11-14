#!/usr/bin/env python3
"""Build the anonymized review artifact (copies only; never modifies src4).

    python3 make_anon_artifact.py --out DIR [--results RESULTS_DIR] [--results-sql RESULTS_SQL_DIR]
                                  [--analysis ANALYSIS_DIR] [--registration-date YYYY-MM-DD] [--scan-only PATH ...]

Copies into DIR, in the same layout as the build machine, so the paper pipeline runs unchanged inside it:
  src4/                       every file of ../src4 except caches (__pycache__, *.pyc, .env, .DS_Store)
  src4_batch/                 the batch drivers that collected the Sonnet 5, Fable 5 and Gemini episodes
  src_sql/                    the exploratory SQL slice (harness, classifier, analysis)
  preregistration/            PREREGISTRATION.md (the OSF registration text), redacted
  paper/PREREGISTRATION.md    the same redacted text, where make_numbers4.py reads the pilot facts
  paper/latex/                the paper pipeline: every script that produces a number (run_analysis, explore4,
                              rollback_sensitivity, posthoc_review, reference_policies, make_numbers4,
                              pipeline_common, figures/make_figs.py, page_budget, build.sh), its tests, main.tex,
                              deviations.csv and README.md
  paper/audit/                the H5 transcript audit (H5_AUDIT.md, H5_AUDIT.csv) and SPOT_CHECK.md
  results4/full/              RESULTS_DIR (CSVs, transcripts, failures.jsonl, spend.jsonl, logs), when given
  results_sql/                RESULTS_SQL_DIR (SQL-slice CSVs, transcripts, analysis), when given
  reference_outputs/analysis/ ANALYSIS_DIR outputs (json/md) of the author's build, for comparison, when given
  FREEZE_OVERRIDE.json        the documented FREEZE override for redacted frozen files (see below)
  ARTIFACT_README.md          layout, commands, the override, hashes of src4_batch/ and src_sql/, terms of use
Text files pass through the identity rules below; binary files are copied byte for byte.

FREEZE override. Five frozen src4 files contain identifying strings and are redacted, so their bytes no longer
match FREEZE.md. For each redacted frozen file the builder checks that the ORIGINAL file hashes to its FREEZE.md
entry (it refuses to build otherwise) and records frozen/original and redacted sha256 in FREEZE_OVERRIDE.json.
paper/latex/pipeline_common.py accepts a file whose hash differs from FREEZE.md only if it is listed there with
that FREEZE hash and its current bytes match the recorded redacted hash. Nothing else is relaxed.

Writes DIR/ANON_CHANGES.md: for every changed file, the sha256 of the original and of the redacted copy and
every changed line (line number and the redacted line, with each replacement visible as its token, so the
identifying text itself is not repeated); the FREEZE.md check of every frozen file in the copy (unchanged files
verify; redacted files differ only in the listed lines); and the registration date.

After copying, the whole DIR is scanned again with the identity patterns; any hit is an error (exit 1).
--scan-only PATH... prints identity hits in the given files/trees and exits (nothing is copied).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC4 = os.environ.get("SRC4", os.path.join(ROOT, "src4"))
SRC4_BATCH = os.path.join(ROOT, "src4_batch")
SRC_SQL = os.path.join(ROOT, "src_sql")
PREREG = os.path.join(HERE, "PREREGISTRATION.md")
LATEX = os.path.join(HERE, "latex")
AUDIT = os.path.join(HERE, "audit")
# paper pipeline files copied into paper/latex (scripts that produce numbers, their tests, the paper source)
LATEX_FILES = ("run_analysis.py", "explore4.py", "rollback_sensitivity.py", "posthoc_review.py", "reference_policies.py",
               "make_numbers4.py", "pipeline_common.py", "page_budget.py", "build.sh", "deviations.csv", "README.md",
               "main.tex", "AI_DRAFTED_SECTIONS.md", os.path.join("figures", "make_figs.py"))
LATEX_DIRS = ("tests",)
AUDIT_FILES = ("H5_AUDIT.md", "H5_AUDIT.csv", "SPOT_CHECK.md", "AUTHOR_SPOT_CHECK_answers.json")
SKIP_DIRS = {"__pycache__", ".git", "_staged_dryrun"}
SKIP_FILES = {".env", ".DS_Store"}
SKIP_EXT = {".pyc"}

# (name, pattern, replacement); applied in order, line by line. Replacement tokens are self-describing.
RULES = [
    ("contributors line", re.compile(r"\*\*Contributors\.\*\*.*$"), "**Contributors.** [REDACTED FOR REVIEW]"),
    ("upload path", re.compile(r"/mnt/user-data/uploads/[^\s\"']*"), "/path/to/ANON_PATH"),
    ("desktop path", re.compile(r"~/Desktop/[A-Za-z0-9_.-]+"), "~/ANON_REPO"),
    ("desktop path", re.compile(r"(/Users|/home)/[A-Za-z0-9_.-]+/Desktop/[A-Za-z0-9_.-]+"), "/path/to/ANON_REPO"),
    ("home path", re.compile(r"/Users/[A-Za-z0-9_.-]+"), "/Users/ANON_USER"),
    ("home path", re.compile(r"/home/[A-Za-z0-9_.-]+"), "/home/ANON_USER"),
    ("project name", re.compile(r"IdempotencyBench"), "AnonBench"),
    ("project name", re.compile(r"idempotencybench", re.I), "anonbench"),
    ("project env prefix", re.compile(r"\bIBENCH_"), "ANONBENCH_"),
    ("github user", re.compile(r"gssanjana4", re.I), "ANON_USER"),
    ("author name", re.compile(r"sanjana", re.I), "ANON_AUTHOR"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.(?:com|org|net|edu|io|ai|dev|co)\b"), "anon@example.org"),
]


def _private_rules():
    """Identity rules that must not be published with this script (for example an employer name).

    They are read from a local JSON file that is never shipped: the path in ANON_PRIVATE_RULES, or
    identity_private.json next to this script. Each entry is {"name": ..., "pattern": ..., "replacement": ...};
    the pattern is compiled case-insensitively, applied after the rules above and added to the scan.
    """
    path = os.environ.get("ANON_PRIVATE_RULES") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                               "identity_private.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [(e["name"], re.compile(e["pattern"], re.I), e["replacement"]) for e in json.load(f)]


PRIVATE_RULES = _private_rules()
RULES = RULES + PRIVATE_RULES
# Scan patterns: everything a rule targets (used for --scan-only and the post-copy check).
_SCAN_BASE = (r"sanjana|gssanjana|gopnal|swamy|idempotencybench|\bIBENCH_|~/Desktop|/Desktop/|/Users/(?!ANON_USER)[A-Za-z]|"
              r"/home/(?!ANON_USER)[A-Za-z]|/mnt/user-data|osf\.io|a5vec|orcid|"
              r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.(?:com|org|net|edu|io|ai|dev|co)\b")
SCAN = re.compile("|".join([_SCAN_BASE] + [p.pattern for _n, p, _r in PRIVATE_RULES]), re.I)
ALLOWED_EMAIL = {"anon@example.org", "noreply@anthropic.com"}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def redact_line(line):
    out, hits = line, []
    for name, pat, rep in RULES:
        new = pat.sub(rep, out)
        if new != out:
            hits.append(name)
            out = new
    return out, hits


def is_text(b):
    if b"\0" in b[:8192]:
        return False
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def copy_file(src, dst, changes, rel):
    data = open(src, "rb").read()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not is_text(data):
        with open(dst, "wb") as f:
            f.write(data)
        return
    lines = data.decode("utf-8").split("\n")
    new, changed = [], []
    for i, line in enumerate(lines, 1):
        r, hits = redact_line(line)
        new.append(r)
        if hits:
            changed.append((i, r, hits))
    out = "\n".join(new).encode("utf-8")
    with open(dst, "wb") as f:
        f.write(out)
    if changed:
        changes.append({"file": rel, "sha_orig": sha(data), "sha_red": sha(out), "lines": changed})


def walk(src_root, dst_root, prefix, changes, copied):
    for d, dirs, files in os.walk(src_root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for fn in sorted(files):
            if fn in SKIP_FILES or os.path.splitext(fn)[1] in SKIP_EXT:
                continue
            src = os.path.join(d, fn)
            rel = os.path.join(prefix, os.path.relpath(src, src_root))
            copy_file(src, os.path.join(dst_root, rel), changes, rel)
            copied.append(rel)


def scan_paths(paths):
    hits = []
    for p in paths:
        files = [p] if os.path.isfile(p) else [os.path.join(d, f) for d, ds, fs in os.walk(p)
                                                for f in fs if not any(x in SKIP_DIRS for x in d.split(os.sep))]
        for fp in sorted(files):
            try:
                data = open(fp, "rb").read()
            except OSError:
                continue
            if not is_text(data):
                continue
            for i, line in enumerate(data.decode("utf-8").split("\n"), 1):
                for m in SCAN.finditer(line):
                    if m.group(0).lower() in ALLOWED_EMAIL:
                        continue
                    hits.append((fp, i, m.group(0), line.strip()[:160]))
    return hits


def freeze_rows(src4_copy):
    path = os.path.join(src4_copy, "FREEZE.md")
    rows = re.findall(r"^\| `(.+)` \| `([0-9a-f]{64})` \|$", open(path).read(), re.M) if os.path.exists(path) else []
    out = []
    for name, want in rows:
        p = os.path.join(src4_copy, name)
        got = sha(open(p, "rb").read()) if os.path.exists(p) else None
        out.append((name, want, got == want))
    return out


def sha_file(p):
    return sha(open(p, "rb").read())


def artifact_readme(out, a, override, batch_hashes, sql_hashes, n_files):
    L = ["# Review artifact: \"Do LLM Agents Coordinate on Shared Records?\"", "",
         "Anonymized for double-blind review. For review only. After the decision, code is released under the MIT "
         "licence and instances, transcripts and results under CC BY 4.0; model outputs remain subject to the providers' "
         "terms, and the Qwen model licence applies to Qwen outputs. Research use only.", "",
         "## Layout", "",
         "| path | content |", "|---|---|",
         "| `src4/` | frozen harness and confirmatory analysis (`analyze4.py`); `FREEZE.md` lists the frozen sha256 |",
         "| `src4_batch/` | batch drivers that collected every Sonnet 5, Fable 5 and Gemini 4 Argon episode, and their offline tests |",
         "| `src_sql/`, `results_sql/` | exploratory SQL slice (post hoc, not pre-registered): code, results, its own analysis |",
         "| `results4/full/` | result CSVs, transcripts (ledgers included), failures and spend logs of the registered run |",
         "| `paper/latex/` | the paper pipeline: every script that produces a number, its tests, `main.tex`, `deviations.csv` |",
         "| `paper/audit/` | the pre-specified H5 transcript audit (performed by an AI agent) and scoring spot-checks |",
         "| `paper/PREREGISTRATION.md`, `preregistration/` | the registration text, contributor line redacted |",
         "| `reference_outputs/analysis/` | the author's analysis outputs, to compare against your rerun |",
         "| `ANON_CHANGES.md` | every redacted line, with sha256 of original and redacted files |",
         "| `FREEZE_OVERRIDE.json` | documented FREEZE override for the redacted frozen files (below) |", "",
         "## AI use", "",
         "The paper's Acknowledgments give a short statement. The full, section-by-section account of AI involvement "
         "(code, data-collection drivers, design suggestions, the pre-registration text, the AI-performed H5 transcript "
         "audit, post hoc analyses proposed by AI reviewers, literature and reference checks, fact sheets, tables, "
         "figures and captions, AI pre-submission reviews, every AI-drafted section of the paper including the abstract, "
         "introduction, results and discussion, and the AI style revision) is in `paper/latex/AI_DRAFTED_SECTIONS.md`. "
         "The AI assistant was Claude. No human has yet checked the transcripts or the H5 audit (update this line, the "
         "Acknowledgments and deviations.csv if the author spot-checks them).", "",
         "## Reproduce", "",
         "Python 3.10+ standard library for the harness and analyses; matplotlib only for figures; pdflatex only for the PDF.", "",
         "```", "cd paper/latex",
         "python3 run_analysis.py --out ../analysis            # verifies FREEZE, runs the frozen src4/analyze4.py (confirmatory)",
         "python3 explore4.py --analysis ../analysis           # EXPLORATORY analyses from saved CSVs and transcripts",
         "python3 rollback_sensitivity.py --analysis ../analysis   # POST HOC rollback rescoring + H5 audit counts",
         "python3 posthoc_review.py --analysis ../analysis     # POST HOC review analyses (saved data only)",
         "python3 reference_policies.py --analysis ../analysis # POST HOC scripted reference agents (no model calls)",
         "python3 make_numbers4.py --analysis ../analysis --check   # numbers.tex, tables/, lint of main.tex",
         "python3 -m unittest discover -s tests                # pipeline tests",
         "cd ../../src4 && python3 -m unittest tests4 tests_full4 tests_model4   # harness tests",
         "```", "",
         "`confirmatory.json` should equal `reference_outputs/analysis/confirmatory.json` except for the input paths; "
         "`numbers.tex` should equal the author's except for the path comments at its top. "
         "Ledgers and scores can be regenerated from the transcripts with the frozen scorer: `rollback_sensitivity.py` "
         "recomputes `serial_witness` for every episode and stops if any recorded score is not reproduced. "
         "Model outputs cannot be regenerated.", "",
         "Known limitation of this redacted copy: the tests in `src4_batch/` that drive the frozen harness import it through "
         "`src4_batch/frozen.py`, whose own FREEZE gate (used when the data were collected, unchanged here) does not read "
         "`FREEZE_OVERRIDE.json`, so they fail on the five redacted frozen files. They pass when `SRC4_DIR` points at the "
         "unredacted `src4/` (checked by the author before building this artifact; released at camera-ready). "
         "`src_sql/tests_sql.py`, the `src4/` tests and the `paper/latex/` tests run on this copy.", "",
         "## FREEZE override (redacted frozen files)", "",
         "FREEZE.md lists the sha256 of the UNREDACTED files, as registered. The files below contain identifying strings and "
         "are redacted here, so they no longer match FREEZE.md. When this artifact was built, each ORIGINAL file was checked "
         "against its FREEZE.md hash (all match). `paper/latex/pipeline_common.py` accepts a frozen file whose hash differs "
         "from FREEZE.md only if it is listed in `FREEZE_OVERRIDE.json` with that FREEZE hash and its current bytes match "
         "the recorded redacted hash; nothing else is relaxed. The changed lines are in ANON_CHANGES.md; the unredacted "
         "files are released at camera-ready.", "",
         "| file | FREEZE.md sha256 = original sha256 | redacted sha256 |", "|---|---|---|"]
    for e in override:
        L.append(f"| `src4/{e['file']}` | `{e['frozen_sha256']}` | `{e['redacted_sha256']}` |")
    for title, hashes in (("src4_batch/ (not frozen; hashed here at artifact build)", batch_hashes),
                          ("src_sql/ (not frozen; hashed here at artifact build)", sql_hashes)):
        L += ["", f"## sha256 of {title}", "", "| file | sha256 of the copy in this artifact |", "|---|---|"]
        L += [f"| `{k}` | `{v}` |" for k, v in sorted(hashes.items())]
    L += ["", f"Files: {n_files}. Pre-registration date: {a.registration_date or '[author: add]'}.", ""]
    with open(os.path.join(out, "ARTIFACT_README.md"), "w") as f:
        f.write("\n".join(L))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out")
    ap.add_argument("--results", help="results root to include (e.g. ../results4/full)")
    ap.add_argument("--results-sql", help="SQL-slice results root to include (e.g. ../results_sql)")
    ap.add_argument("--analysis", help="analysis output dir to include as reference outputs (e.g. analysis)")
    ap.add_argument("--registration-date", default=None)
    ap.add_argument("--scan-only", nargs="+", metavar="PATH")
    a = ap.parse_args(argv)
    if a.scan_only:
        for fp, i, m, line in scan_paths(a.scan_only):
            print(f"{fp}:{i}: [{m}] {line}")
        return 0
    if not a.out:
        ap.error("--out is required")
    out = os.path.abspath(a.out)
    src4 = os.path.abspath(SRC4)
    if out == src4 or out.startswith(src4 + os.sep) or src4.startswith(out + os.sep) or HERE.startswith(out + os.sep) \
            or out == HERE or out.startswith(HERE + os.sep) or out == ROOT:
        raise SystemExit(f"REFUSING: output {out} overlaps src4 or the paper folder")
    if os.path.isdir(out) and os.listdir(out) and not os.path.exists(os.path.join(out, "ANON_CHANGES.md")):
        raise SystemExit(f"REFUSING: {out} exists, is not empty and is not a previous artifact")
    src4_before = {f: sha(open(os.path.join(d, f), "rb").read()) for d, _, fs in os.walk(SRC4) for f in fs
                   if "__pycache__" not in d}
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    changes, copied = [], []
    walk(SRC4, out, "src4", changes, copied)
    for src_dir, name in ((SRC4_BATCH, "src4_batch"), (SRC_SQL, "src_sql")):
        if os.path.isdir(src_dir):
            walk(src_dir, out, name, changes, copied)
    for rel in (os.path.join("preregistration", "PREREGISTRATION.md"), os.path.join("paper", "PREREGISTRATION.md")):
        copy_file(PREREG, os.path.join(out, rel), changes, rel)
        copied.append(rel)
    for f in LATEX_FILES:
        rel = os.path.join("paper", "latex", f)
        copy_file(os.path.join(LATEX, f), os.path.join(out, rel), changes, rel)
        copied.append(rel)
    for d in LATEX_DIRS:
        walk(os.path.join(LATEX, d), out, os.path.join("paper", "latex", d), changes, copied)
    for f in AUDIT_FILES:
        rel = os.path.join("paper", "audit", f)
        copy_file(os.path.join(AUDIT, f), os.path.join(out, rel), changes, rel)
        copied.append(rel)
    if a.results:
        walk(a.results, out, os.path.join("results4", "full"), changes, copied)
    if a.results_sql:
        walk(a.results_sql, out, "results_sql", changes, copied)
    if a.analysis and os.path.isdir(a.analysis):
        walk(a.analysis, out, os.path.join("reference_outputs", "analysis"), changes, copied)
    fz = freeze_rows(os.path.join(out, "src4"))
    changed = {c["file"]: c for c in changes}
    # documented FREEZE override: only redacted frozen files whose ORIGINAL bytes match FREEZE.md
    override = []
    for name, want, ok in fz:
        if ok:
            continue
        c = changed.get(os.path.join("src4", name))
        if c is None:
            raise SystemExit(f"ERROR: frozen file {name} differs from FREEZE.md but was not redacted")
        if c["sha_orig"] != want:
            raise SystemExit(f"ERROR: ORIGINAL src4/{name} does not match FREEZE.md ({c['sha_orig']} != {want})")
        override.append({"file": name, "frozen_sha256": want, "redacted_sha256": c["sha_red"],
                         "lines_changed": len(c["lines"])})
    with open(os.path.join(out, "FREEZE_OVERRIDE.json"), "w") as f:
        json.dump({"note": "Documented FREEZE override for the anonymized review artifact: these frozen files were "
                           "redacted for anonymity; frozen_sha256 is both the FREEZE.md hash and the sha256 of the original "
                           "file (checked at build time); redacted_sha256 is the hash of the copy here. "
                           "paper/latex/pipeline_common.py accepts exactly these bytes. Changed lines: ANON_CHANGES.md.",
                   "redacted_frozen_files": override}, f, indent=1)
        f.write("\n")
    copied.append("FREEZE_OVERRIDE.json")
    batch_hashes = {k: v for k, v in ((os.path.relpath(p, "src4_batch"), sha_file(os.path.join(out, p)))
                                      for p in copied if p.startswith("src4_batch" + os.sep))}
    sql_hashes = {k: v for k, v in ((os.path.relpath(p, "src_sql"), sha_file(os.path.join(out, p)))
                                    for p in copied if p.startswith("src_sql" + os.sep))}
    artifact_readme(out, a, override, batch_hashes, sql_hashes, len(copied) + 2)
    copied.append("ARTIFACT_README.md")
    changed_files = set(changed)
    L = ["# ANON_CHANGES: identity redactions in this artifact", "",
         "Every change made to the copied files is listed below. Only identifying strings were replaced (author name, "
         "user names, home and Desktop paths, the project name of the author's earlier work, e-mail addresses). "
         "Each changed line is shown as it appears in the artifact; the replacement tokens (ANON_*, AnonBench, anonbench, "
         "anon@example.org, [REDACTED FOR REVIEW]) mark exactly what changed. No other byte differs.", "",
         "FREEZE.md lists sha256 hashes of the UNREDACTED files, as registered. Files without redactions verify against "
         "it unchanged; redacted files differ only in the lines listed here. For every redacted frozen file the original "
         "was checked against FREEZE.md when this artifact was built, and FREEZE_OVERRIDE.json lets the pipeline accept "
         "exactly the redacted bytes (ARTIFACT_README.md). The unredacted files are released at camera-ready.", "",
         f"Pre-registration: OSF, registered {a.registration_date or '[author: add the registration date]'}. "
         "The OSF page is not linked during review because its text names the author; preregistration/PREREGISTRATION.md "
         "is the registered text with the contributor line redacted. The link is added at camera-ready.", "",
         f"Files copied: {len(copied)}; files with redactions: {len(changes)}.", "", "## FREEZE.md check of the copied src4", "",
         "| file | frozen sha256 | copy verifies |", "|---|---|---|"]
    for name, want, ok in fz:
        why = "yes" if ok else ("no: redacted (lines below); original verified; in FREEZE_OVERRIDE.json"
                                if os.path.join("src4", name) in changed_files else "NO")
        L.append(f"| `{name}` | `{want}` | {why} |")
    L += ["", "## Changed files", ""]
    for c in changes:
        L += [f"### `{c['file']}`", "", f"- sha256 original: `{c['sha_orig']}`", f"- sha256 redacted: `{c['sha_red']}`",
              f"- lines changed: {len(c['lines'])}", ""]
        for i, line, hits in c["lines"]:
            L.append(f"    L{i} [{', '.join(sorted(set(hits)))}]: {line.strip()[:300]}")
        L.append("")
    with open(os.path.join(out, "ANON_CHANGES.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    src4_after = {f: sha(open(os.path.join(d, f), "rb").read()) for d, _, fs in os.walk(SRC4) for f in fs
                  if "__pycache__" not in d}
    if src4_after != src4_before:
        raise SystemExit("ERROR: src4 changed during the copy")
    left = scan_paths([out])
    bad = [h for h in left if not h[0].endswith("ANON_CHANGES.md")]
    for fp, i, m, line in bad:
        print(f"IDENTITY STRING LEFT: {fp}:{i}: [{m}] {line}")
    print(f"artifact: {out} ({len(copied)} files, {len(changes)} redacted, "
          f"{sum(ok for _, _, ok in fz)}/{len(fz)} frozen files verify unchanged, {len(override)} via the documented override)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
