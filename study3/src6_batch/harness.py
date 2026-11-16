"""Import path to the Study 2 harness (src6) and its FREEZE.md check. Nothing in src6 is modified here.

src6 is found next to this directory (``<repo>/src6``) or at ``$SRC6_DIR``. Bytecode writing is turned off so
importing never writes into src6/. (Study 1's frozen src4 is never imported by the batch layer.)
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from typing import Dict, List

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.environ.get("SRC6_DIR") or os.path.join(HERE, "..", "src6"))
if not os.path.exists(os.path.join(SRC, "run6.py")):
    raise ImportError(f"Study 2 harness not found at {SRC} (set SRC6_DIR)")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

_ROW = re.compile(r"^\| `(.*)` \| `([0-9a-f]{64})` \|$")


def freeze_table(src: str = SRC) -> Dict[str, str]:
    path = os.path.join(src, "FREEZE.md")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {m.group(1): m.group(2) for m in (_ROW.match(line.rstrip("\n")) for line in f) if m}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_freeze(src: str = SRC) -> List[str]:
    """Mismatches between src6/FREEZE.md and the files on disk (empty list: every frozen file unchanged). Round 3:
    the frozen set is src6/freeze6.files() (src6, this batch layer, src6_verify/dry_check6.py and
    run_conc_study3.sh); a frozen file without a row is a mismatch too."""
    table = freeze_table(src)
    if not table:
        return ["src6/FREEZE.md has no hash rows (run: python3 src6/freeze6.py)"]
    bad = []
    for name, digest in sorted(table.items()):
        p = os.path.join(src, name)
        if not os.path.exists(p):
            bad.append(f"{name}: missing")
        elif sha256_file(p) != digest:
            bad.append(f"{name}: sha256 differs from FREEZE.md")
    try:
        import freeze6  # noqa: PLC0415 - src6 is on sys.path
        bad += [f"{name}: frozen file not listed in FREEZE.md" for name in freeze6.files() if name not in table]
    except ImportError:
        bad.append("src6/freeze6.py not importable")
    return bad


def own_hashes() -> Dict[str, str]:
    """sha256 of this batch layer's own source files (logged with every run)."""
    out = {}
    for fn in sorted(os.listdir(HERE)):
        if fn.endswith((".py", ".sh")):
            out[fn] = sha256_file(os.path.join(HERE, fn))
    return out


if __name__ == "__main__":
    problems = verify_freeze()
    print("\n".join(problems) if problems else f"FREEZE OK: {len(freeze_table())} files in {SRC} match FREEZE.md")
    sys.exit(1 if problems else 0)
