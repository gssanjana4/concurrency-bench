#!/bin/bash
# Build the concurrency paper from data:
#   frozen analysis (run_analysis.py -> src4/analyze4.py) -> explore4.py (EXPLORATORY) -> rollback_sensitivity.py,
#   posthoc_review.py, reference_policies.py (POST HOC) -> make_numbers4.py -> figures -> pdflatex/bibtex
#
#   bash build.sh                 real data: results4/full/phase{1,2,3}/results.csv -> ../analysis; both PDF builds
#   bash build.sh --dry-run       fake-model dry run: results4/full/phase*/dry_run/results.csv -> ../analysis_dry
#                                 (PDF carries a DRY RUN DATA watermark)
#   bash build.sh --no-analysis   reuse the existing analysis dir (fast rebuild after editing the .tex files)
#   bash build.sh --preprint      only the named preprint build (author named, OSF identifiers shown, no line numbers)
#   bash build.sh --anonymous     only the anonymous build (no author, "[registration link withheld]", the concurrent
#                                 paper cited as "Anonymous. Concurrent submission.", no line numbers)
#   bash build.sh --tmlr          only the TMLR build: the same content as the anonymous build in the official TMLR style
#                                 (tmlr/tmlr.sty and tmlr/tmlr.bst, pinned in tmlr/PIN.md; tmlr_setup.tex), anonymous as
#                                 TMLR requires; the supplement is a separate PDF in the same style
#   (no mode flag: all three builds, preprint, anonymous and tmlr)
#   bash build.sh --descriptives  also rerun analysis5/descriptives5.py (Study 2 tables, figures, post hoc counts)
#
# Outputs: main.pdf and supplement.pdf (the preprint), build/main_<mode>.pdf (mode: preprint, anonymous, tmlr), build/supplement_<mode>.pdf,
# build/build_<mode>.log, build/build_supplement_<mode>.log, build/pages_<mode>.txt. The paper and the supplement
# cross-reference each other (xr-hyper) and are built in alternation; any undefined reference, undefined control
# sequence, overfull box or other LaTeX warning in either fails the build. Every step refuses to run if the src4 FREEZE hashes do not verify.
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1

DRY=0; ANALYSIS=1; MODES="preprint anonymous tmlr"; DESCR=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --no-analysis) ANALYSIS=0 ;;
    --preprint) MODES="preprint" ;;
    --anonymous) MODES="anonymous" ;;
    --tmlr) MODES="tmlr" ;;
    --descriptives) DESCR=1 ;;
    *) echo "unknown argument $a"; exit 2 ;;
  esac
done
if [ $DRY = 1 ]; then OUT=../analysis_dry; FLAG=--dry-run; else OUT=../analysis; FLAG=""; fi

# ---- TeX
if ! command -v pdflatex >/dev/null || ! command -v bibtex >/dev/null; then
  echo "pdflatex/bibtex missing: installing TeX Live (apt)"
  SUDO=""; [ "$(id -u)" != 0 ] && SUDO=sudo
  $SUDO apt-get update -qq && $SUDO apt-get install -y -qq texlive-latex-recommended texlive-latex-extra \
      texlive-fonts-recommended texlive-bibtex-extra poppler-utils >/dev/null || { echo "TeX install failed"; exit 1; }
fi
python3 -c "import matplotlib" 2>/dev/null || pip install -q matplotlib || { echo "matplotlib install failed"; exit 1; }

# ---- 1. frozen analysis
if [ $ANALYSIS = 1 ]; then
  python3 run_analysis.py $FLAG --out "$OUT" || { echo "analysis failed"; exit 1; }
fi
# ---- 1b. exploratory analyses from saved CSVs/transcripts (EXPLORATORY; writes only $OUT/exploratory_posthoc.json)
python3 explore4.py --analysis "$OUT" || { echo "exploratory analyses failed"; exit 1; }
# ---- 1c. POST HOC rollback sensitivity + H5 audit counts (writes only $OUT/rollback_sensitivity.json; imports frozen code read-only)
python3 rollback_sensitivity.py --analysis "$OUT" || { echo "rollback sensitivity failed"; exit 1; }
# ---- 1d. POST HOC review analyses (saved data only; writes only $OUT/posthoc_review.json) and the scripted
#          reference policies under the registered schedule (frozen agents4.py, no model calls; $OUT/reference_policies.json)
python3 posthoc_review.py --analysis "$OUT" || { echo "post hoc review analyses failed"; exit 1; }
python3 reference_policies.py --analysis "$OUT" || { echo "reference policies failed"; exit 1; }
# ---- 1e. Study 2 descriptives (optional rerun; read-only on the data) and the registered macros:
#          study2_out/study2_registered_numbers.tex is a verbatim copy of the frozen analyze5.py output
#          (analysis5/out_study2/numbers.tex). Refresh the copy when the source is present and check its sha256 against the
#          value recorded by descriptives5.py in study2_out/study2_numbers.tex. Never edit the copy.
if [ $DESCR = 1 ]; then
  python3 -I ../../analysis5/descriptives5.py || { echo "descriptives5 failed"; exit 1; }
fi
# ---- 1f. (removed in the v11 three-review round: the two caption pointers of T8c C5 are now written by descriptives5.py)
S2DATA="${STUDY2_DATA:-$HOME/study2_data}";[ -d "$S2DATA" ] || S2DATA=../../study2_data
S2SRC="${STUDY2_NUMBERS:-$S2DATA/analysis5/out_study2/numbers.tex}"
export STUDY2_RESULTS="${STUDY2_RESULTS:-$S2DATA/analysis5/out_study2/results.json}"
S2DST=study2_out/study2_registered_numbers.tex
[ -f "$S2SRC" ] && cp "$S2SRC" "$S2DST"
S2EXP=$(sed -n 's/.*registered numbers.tex sha256 \([0-9a-f]\{64\}\).*/\1/p' study2_out/study2_numbers.tex | head -1)
S2SHA=$(sha256sum "$S2DST" | cut -c1-64)
[ -n "$S2EXP" ] && [ "$S2SHA" = "$S2EXP" ] || { echo "Study 2 registered numbers: sha256 $S2SHA does not match the recorded $S2EXP"; exit 1; }
# ---- 2. numbers, tables, facts (+ lint of main.tex)
python3 make_numbers4.py --analysis "$OUT" --check || { echo "make_numbers4 failed or lint problems"; exit 1; }
# ---- 2b. lint of the Study 2 and appendix sources (no typed digits in prose; undefined Study 2 macros) and the fact pass
python3 study2_lint.py || { echo "study2 lint problems"; exit 1; }
# ---- 2c. a model-named number macro in a sentence or table row belongs to the model named there, in the order named (T8c C1)
python3 check_model_macros.py || { echo "model/macro attribution problems"; exit 1; }
# ---- 3. figures
python3 figures/make_figs.py || { echo "figures failed"; exit 1; }
# ---- 4. LaTeX, one build per mode
mkdir -p build
STATUS=0
for MODE in $MODES; do
  if [ "$MODE" = anonymous ] || [ "$MODE" = tmlr ]; then
    echo '\newcommand{\BuildAnonymous}{1}' > buildmode.tex
    # the TMLR build: the anonymous content in the official TMLR style (tmlr_setup.tex)
    [ "$MODE" = tmlr ] && echo '\newcommand{\BuildTMLR}{1}' >> buildmode.tex
    # the concurrent paper: no title, no year (T8 F26)
    python3 - <<'EOF'
import re
s = open("refs.bib").read()
s = re.sub(r"@misc\{anon2027retries,.*?\n\}", "@misc{anon2027retries,\n  author = {Anonymous},\n  title  = {Concurrent submission},\n  year   = {n.d.}\n}", s, count=1, flags=re.S)
open("refs_build.bib", "w").write(s)
EOF
  else
    echo '\newcommand{\BuildAnonymous}{0}' > buildmode.tex
    cp refs.bib refs_build.bib
  fi
  # the paper (main) and the supplement read each other's .aux through xr-hyper, so they are built in alternation
  rm -f main.aux main.bbl main.out supplement.aux supplement.bbl supplement.out
  TLM="timeout 240 pdflatex -interaction=nonstopmode -halt-on-error main"
  TLS="timeout 240 pdflatex -interaction=nonstopmode -halt-on-error supplement"
  $TLM >/dev/null; $TLS >/dev/null; bibtex main >/dev/null; bibtex supplement >/dev/null
  $TLM >/dev/null; $TLS >/dev/null; $TLM >/dev/null; $TLS >/dev/null
  $TLM > build/build_$MODE.log; $TLS > build/build_supplement_$MODE.log
  for DOC in main supplement; do
    LOGF=build/build_$MODE.log; [ $DOC = supplement ] && LOGF=build/build_supplement_$MODE.log
    grep -n "^!" -A3 $LOGF | head -20
    grep -q "Output written" $LOGF || { echo "NO PDF ($DOC, $MODE)"; exit 1; }
  done
  cp main.pdf build/main_$MODE.pdf
  cp main.log build/main_$MODE.log
  cp supplement.pdf build/supplement_$MODE.pdf
  cp supplement.log build/supplement_$MODE.log
  # ---- 5. checks (both documents)
  PAGES=$(pdfinfo main.pdf | awk '/^Pages:/{print $2}')
  SPAGES=$(pdfinfo supplement.pdf | awk '/^Pages:/{print $2}')
  LIMPAGE=$(sed -n 's/^\\newlabel{sec:limitations}{{[^}]*}{\([0-9]*\)}.*/\1/p' main.aux)
  ENDPAGE=$(sed -n 's/^\\newlabel{sec:end-main}{{[^}]*}{\([0-9]*\)}.*/\1/p' main.aux)
  APPPAGE=$(sed -n 's/^\\newlabel{app:s2-deviations}{{[^}]*}{\([0-9]*\)}.*/\1/p' main.aux)
  pdftotext main.pdf main.txt
  pdftotext supplement.pdf supplement.txt
  UNDEF=0; UCS=0; OVER=0; WARN=0
  for L in main.log supplement.log; do
    UNDEF=$((UNDEF + $(grep -cE 'Warning: (Citation|Reference).*undefined|There were undefined references|LABELS NOT IMPORTED' $L)))
    UCS=$((UCS + $(grep -c 'Undefined control sequence' $L)))
    OVER=$((OVER + $(grep -c 'Overfull' $L)))
    WARN=$((WARN + $(grep -c 'Warning' $L)))
  done
  MARKP=$(grep -o 'AI draft [^a-z]* author to review and revise' main.txt | wc -l)
  MARKS=$(grep -o 'AI draft [^a-z]* author to review and revise' supplement.txt | wc -l)
  { echo "mode: $MODE"; echo "paper pages total: $PAGES";
    echo "paper main text: pages 1 to $ENDPAGE (body to page $((LIMPAGE-1)); Limitations, Ethics Statement and Acknowledgments from page $LIMPAGE)";
    echo "paper appendix: pages $APPPAGE to $PAGES ($((PAGES-APPPAGE+1)) pages)";
    echo "supplement pages total: $SPAGES";
    echo "undefined refs/cites (paper + supplement): $UNDEF"; echo "undefined control sequences: $UCS";
    echo "overfull hboxes: $OVER"; echo "LaTeX warnings of any kind: $WARN";
    echo "AI-draft markers (\\authorcheck) left for the author: $((MARKP+MARKS)) (paper $MARKP, supplement $MARKS)";
    echo "PENDING values in PDF: $(cat main.txt supplement.txt | grep -c 'PENDING')"; } | tee build/pages_$MODE.txt
  [ "$UNDEF" = 0 ] && [ "$UCS" = 0 ] && [ "$OVER" = 0 ] || { echo "BUILD CHECK FAILED ($MODE): refs/macros/overfull"; STATUS=1; }
  [ "$WARN" = 0 ] || { echo "BUILD CHECK FAILED ($MODE): $WARN LaTeX warnings (see main.log, supplement.log)"; STATUS=1; }
  if [ "$MODE" = anonymous ] || [ "$MODE" = tmlr ]; then
    # identity strings come from identity.tex (never shipped in the anonymous artifacts), so this script carries none;
    # both PDFs of the anonymous build are scanned
    REGHOST=$(grep -o 'https://[a-z]*\.io/' identity.tex | sort -u | head -1 | sed 's#https://##; s#/$##')
    NEEDLES=$(sed -n 's/^\\newcommand{\\AuthorLine}{\([^\\]*\).*/\1/p' identity.tex | tr ' ' '\n' | grep -v '^$'; grep -o "$REGHOST/[a-z0-9]*" identity.tex | sed "s#$REGHOST/##" | sort -u; echo "$REGHOST")
    # the repository owner and the Zenodo record numbers of identity.tex must not appear either (added 2026-11-14)
    NEEDLES="$NEEDLES $(grep -o 'github\.com/[A-Za-z0-9_-]*' identity.tex | sed 's#github\.com/##' | sort -u) $(grep -o 'zenodo\.[0-9][0-9]*' identity.tex | sort -u)"
    for needle in $NEEDLES; do
      for T in main.txt supplement.txt; do
        grep -q "$needle" $T && { echo "ANONYMITY LEAK ($needle) in the anonymous PDF ($T)"; STATUS=1; }
      done
    done
  fi
  if [ $DRY = 1 ]; then
    grep -q "DRY RUN DATA" main.txt && echo "dry-run watermark: present" || { echo "dry-run watermark: MISSING"; exit 1; }
  else
    cat main.txt supplement.txt | grep -q "DRY RUN DATA" && { echo "REAL BUILD BUT PDF SAYS DRY RUN"; exit 1; }
  fi
done
# leave the preprint as main.pdf when both were built
if [ -f build/main_preprint.pdf ]; then cp build/main_preprint.pdf main.pdf; cp build/main_preprint.log main.log; pdftotext main.pdf main.txt; fi
if [ -f build/supplement_preprint.pdf ]; then cp build/supplement_preprint.pdf supplement.pdf; cp build/supplement_preprint.log supplement.log; pdftotext supplement.pdf supplement.txt; fi
# ---- 6. fact pass (Study 2 claim sentences -> macros -> sources), the advisory AI-text audit, and the tests
python3 study2_factpass.py || { echo "fact pass failed"; STATUS=1; }
# every sha256 printed in the paper and the supplement against the files it names (review F1 M1)
if [ -f check_hashes.py ]; then python3 check_hashes.py || { echo "hash check failed"; STATUS=1; }; else echo "hash check: check_hashes.py not present (not shipped), skipped"; fi
python3 ../release/ai_text_audit.py main.tex --json build/ai_text_audit.json | tail -5
python3 ../release/ai_text_audit.py study2.tex --json build/ai_text_audit_study2.json | tail -3
# ---- 7. nothing-lost check against the v10 snapshot (labels, floats, table inputs, macros; CUT_LOG.md)
[ -d ../latex_v10_snapshot ] && { python3 check_nothing_lost.py --quiet || { echo "nothing-lost check failed"; STATUS=1; }; }
python3 -m unittest discover -s tests -q 2>&1 | tail -3
exit $STATUS
