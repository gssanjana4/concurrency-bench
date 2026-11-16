"""Write src7/FREEZE.md: sha256 of every Study 4 harness file (run once, before the first paid episode).

Derived from src6/freeze6.py (Study 3); the frozen set is the same pattern one directory over: every ``*.py`` and
``*.json`` in src7, every ``*.py``, ``*.json`` and ``*.sh`` in src7_batch, ``src7_verify/dry_check7.py`` and
``run_conc_study4.sh``.

    python3 src7/freeze7.py            # writes FREEZE.md
    python3 src7/freeze7.py --check    # exit 1 if any frozen file differs, is missing, or is not listed

Frozen set (Round 3, review V2b finding 6 / task item 7): every ``*.py`` and ``*.json`` in src7 (this script
included), every ``*.py``, ``*.json`` and ``*.sh`` in src7_batch (the batch layer builds the model input of the three Claude models), ``src7_verify/dry_check7.py`` (run by the dry run) and the runner
``run_conc_study4.sh``. Paths outside src7 are listed relative to src7 (``../src7_batch/batch_driver.py``).
``run_conc_study4.sh`` (via ``--check``) and the batch driver (``src7_batch/harness.verify_freeze``) refuse to
start on any mismatch, so a Study 4 run uses exactly the harness the pre-registration cites.
"""

from __future__ import annotations

import hashlib
import os
import sys
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC5_EXTS = (".py", ".json")
BATCH_EXTS = (".py", ".json", ".sh")
EXTRA = ("../src7_verify/dry_check7.py", "../run_conc_study4.sh")


def _listed(d: str, exts: Tuple[str, ...], prefix: str) -> List[str]:
    p = os.path.join(HERE, d) if d else HERE
    if not os.path.isdir(p):
        return []
    return sorted(prefix + f for f in os.listdir(p) if f.endswith(exts) and os.path.isfile(os.path.join(p, f)))


def files() -> List[str]:
    """Frozen files, as paths relative to src7."""
    out = _listed("", SRC5_EXTS, "") + _listed("../src7_batch", BATCH_EXTS, "../src7_batch/")
    out += [f for f in EXTRA if os.path.isfile(os.path.join(HERE, f))]
    return out


def sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def problems(text: str) -> List[str]:
    """Every frozen file whose row is missing from ``text`` or whose sha256 differs."""
    return [f"{f}: differs or unlisted" for f in files() if f"| `{f}` | `{sha(os.path.join(HERE, f))}` |" not in text]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = os.path.join(HERE, "FREEZE.md")
    rows = [(f, sha(os.path.join(HERE, f))) for f in files()]
    if "--check" in argv:
        with open(path) as fh:
            bad = problems(fh.read())
        print("\n".join(bad) or f"FREEZE OK ({len(rows)} files)")
        return 1 if bad else 0
    with open(path, "w") as fh:
        fh.write("# FREEZE: Study 4 harness (src7, src7_batch, src7_verify/dry_check7.py, run_conc_study4.sh)\n\n"
                 "sha256 of every frozen file (paths relative to src7/); any later change is a deviation. "
                 "`run_conc_study4.sh` and the batch driver refuse to start on any mismatch.\n\n"
                 "| file | sha256 |\n|---|---|\n")
        for name, h in rows:
            fh.write(f"| `{name}` | `{h}` |\n")
    print(f"wrote {path} ({len(rows)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
