"""Print the Freeze table of PREREGISTRATION_STUDY3.md (sha256 of src6/FREEZE.md and of every frozen file outside
src6), or check it: python3 tools/freeze_table.py [--check PREREGISTRATION_STUDY3.md]. Run from the study3 folder."""
import glob, hashlib, os, sys

FILES = (["src6/FREEZE.md", "run_conc_study3.sh", "analysis6/analyze6.py", "analysis6/balance6.py",
          "analysis6/tests_analyze6.py", "analysis6/out/results.json", "analysis6/out/numbers.tex"]
         + sorted(glob.glob("analysis6/power_sims/*.py")) + ["analysis6/power_sims/power6_out.json"]
         + sorted(glob.glob("tools/*.py")))


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


rows = "| file | sha256 |\n|---|---|\n" + "".join(f"| `{p}` | `{sha(p)}` |\n" for p in FILES)
if "--check" in sys.argv:
    text = open(sys.argv[sys.argv.index("--check") + 1]).read()
    bad = [ln for ln in rows.splitlines()[2:] if ln not in text]
    print("\n".join(bad) or f"FREEZE TABLE OK ({len(rows.splitlines()) - 2} files)")
    sys.exit(1 if bad else 0)
print(rows, end="")
