#!/usr/bin/env python3
"""How much room is left for prose in the 8-page main text (measurement only; writes no paper text).

    python3 page_budget.py            (after build.sh has produced numbers.tex, tables/ and figures/)

Builds a throw-away copy of main.tex (build/_budget/) with the grey fact boxes and the dry-run banner switched off and
floats kept exactly as in main.tex. Two modes:
  - while \\authorwrites boxes remain: every main-body box is replaced by neutral filler (the same sentence repeated)
    and the abstract by a fixed 180-word filler; the result is the prose capacity for the boxes;
  - once no box remains: the real text is kept and filler is added at the end of the Discussion; the result is the
    SPARE capacity, measured with the \\authorcheck markers as they are and with them removed.
A binary search finds the largest number of filler words for which the main text (everything before Limitations; a
\\clearpage before Limitations flushes the floats) still ends on page 8. A second build without the main-text floats
measures words per full text page, which converts the capacity to pages. Prints the result and writes
build/page_budget.txt. The filler never reaches main.tex or the PDF.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "build", "_budget")
SENT = "agents read the record and then write a new value after another agent has changed it "
ABSTRACT_WORDS = 180
PAGE_LIMIT = 8


def filler(n):
    w = SENT.split()
    return " ".join(w[i % len(w)] for i in range(max(n, 0)))


def variant(src, words, keep_floats=True, drop_markers=False):
    body_start = src.index(r"\begin{document}")
    lim = src.index(r"\section*{Limitations}")
    pre, main, post = src[:body_start], src[body_start:lim], src[lim:]
    pre = pre.replace(r"\newif\iffactboxes\factboxestrue", r"\newif\iffactboxes\factboxesfalse")
    pre += "\n" + r"\renewcommand{\DryBanner}{}" + "\n"
    if drop_markers:
        pre += r"\renewcommand{\authorcheck}[1]{}" + "\n"
    boxes = re.findall(r"\\authorwrites\{", main)
    if not boxes:  # finished draft: keep the text, add filler at the end of the main text
        k = 0
        cut = main.index(r"\FloatBarrier") if r"\FloatBarrier" in main else len(main)
        main = main[:cut] + "\n" + filler(words) + "\n\n" + main[cut:]
    else:
        abstract = re.search(r"\\begin\{abstract\}.*?\\end\{abstract\}", main, re.S)
        main = main[:abstract.start()] + r"\begin{abstract}" + filler(ABSTRACT_WORDS) + r"\end{abstract}" + main[abstract.end():]
        k = len(boxes)
        per = words // k
        out, i = [], 0
        for m in re.finditer(r"\\authorwrites\{", main):
            out.append(main[i:m.start()])
            depth, j = 1, m.end()
            while depth:
                depth += {"{": 1, "}": -1}.get(main[j], 0)
                j += 1
            out.append("\n" + filler(per) + "\n")
            i = j
        out.append(main[i:])
        main = "".join(out)
    if not keep_floats:
        main = re.sub(r"\\begin\{(figure|table)\*?\}.*?\\end\{\1\*?\}", "", main, flags=re.S)
        main = re.sub(r"\\input\{tables/[^}]*\}", "", main)
    # \clearpage flushes every pending main-text float and starts a new page, so the label's page is exactly
    # (last page holding main-text content) + 1, whatever the float placement.
    post = post.replace(r"\section*{Limitations}", r"\clearpage\label{budget:end}\section*{Limitations}", 1)
    post = post[:post.index(r"\appendix")] + r"\end{document}" + "\n"
    return pre + main + post, k


def last_main_page(tex):
    """Last page that holds main-text content (text or floats)."""
    return compile_pages(tex) - 1


def compile_pages(tex):
    with open(os.path.join(WORK, "b.tex"), "w") as f:
        f.write(tex)
    # resolved citations and references from the last full build, so the measured text has its real length
    for ext in ("aux", "bbl"):
        src = os.path.join(HERE, "main." + ext)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(WORK, "b." + ext))
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "b.tex"], cwd=WORK,
                       capture_output=True, text=True, timeout=180)
    aux = open(os.path.join(WORK, "b.aux")).read() if os.path.exists(os.path.join(WORK, "b.aux")) else ""
    m = re.search(r"\\newlabel\{budget:end\}\{\{[^}]*\}\{(\d+)\}", aux)
    if r.returncode != 0 or not m:
        raise SystemExit("budget build failed:\n" + r.stdout[-2000:])
    return int(m.group(1))


def main():
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    # every file main.tex inputs; identity.tex, buildmode.tex and refs_build.bib exist only after build.sh ran
    for name in ("numbers.tex", "acl.sty", "acl_natbib.bst", "refs.bib", "refs_build.bib", "study2.tex", "study2_constants.tex",
                 "study1_full.tex", "study2_prompts.tex", "study2_analysis.tex", "identity.tex", "buildmode.tex"):
        if os.path.exists(os.path.join(HERE, name)):
            shutil.copy(os.path.join(HERE, name), WORK)
    for d in ("tables", "figures", "study2_out"):  # study2_out: Study 2 macros, tables and figures (input by main.tex)
        shutil.copytree(os.path.join(HERE, d), os.path.join(WORK, d))
    src = open(os.path.join(HERE, "main.tex")).read()

    def capacity(**kw):
        if last_main_page(variant(src, 0, **kw)[0]) > PAGE_LIMIT:
            return -1
        lo, hi = 0, 500
        while hi <= 16000 and last_main_page(variant(src, hi, **kw)[0]) <= PAGE_LIMIT:
            lo, hi = hi, hi * 2
        while hi - lo > 25:
            mid = (lo + hi) // 2
            if last_main_page(variant(src, mid, **kw)[0]) <= PAGE_LIMIT:
                lo = mid
            else:
                hi = mid
        return lo

    k = variant(src, 0)[1]
    cap = capacity()
    cap_nomark = capacity(drop_markers=True) if k == 0 and r"\authorcheck{" in src else None
    # words per full text page: no floats, plenty of filler; count filler words on page 2
    compile_pages(variant(src, 6000, keep_floats=False)[0])
    vocab = set(SENT.split())
    wpp = 0
    for pg in range(2, 9):  # densest filler page = a full text page
        txt = subprocess.run(["pdftotext", "-f", str(pg), "-l", str(pg), os.path.join(WORK, "b.pdf"), "-"],
                             capture_output=True, text=True).stdout
        wpp = max(wpp, sum(w in vocab for w in txt.split()))
    def fmt(c):
        if c < 0:
            return f"OVER: the main text already runs past page {PAGE_LIMIT}"
        return f"about {c} words" + (f" (= {c / wpp:.1f} pages at {wpp} words per full text page)" if wpp else "")
    if k:
        lines = [f"main-text boxes filled: {k} (abstract fixed at {ABSTRACT_WORDS} words; fact boxes off)",
                 f"prose capacity with the current main-text floats: {fmt(cap)}"]
    else:
        lines = ["no \\authorwrites boxes left: spare capacity measured after the real text (fact boxes off)",
                 f"spare capacity with the current text and floats: {fmt(cap)}"]
        if cap_nomark is not None:
            lines.append(f"spare capacity once the \\authorcheck markers are removed: {fmt(cap_nomark)}")
    with open(os.path.join(HERE, "build", "page_budget.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    shutil.rmtree(WORK)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
