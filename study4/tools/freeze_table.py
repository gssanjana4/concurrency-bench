"""Print the Freeze table of PREREGISTRATION_STUDY4.md (sha256 of src7/FREEZE.md and of every frozen file outside
src7), or check it: python3 tools/freeze_table.py [--check PREREGISTRATION_STUDY4.md]. Run from the study4 folder."""
import glob, hashlib, sys

FILES = (["src7/FREEZE.md", "run_conc_study4.sh", "analysis7/analyze7.py", "analysis7/core7.py", "analysis7/balance7.py",
          "analysis7/tests_analyze7.py", "analysis7/out/results.json", "analysis7/out/numbers.tex",
          "analysis7/power_study4.json"] + sorted(glob.glob("tools/*.py")))


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
