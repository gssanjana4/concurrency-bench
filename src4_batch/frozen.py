"""Import path to the frozen harness (src4) and a FREEZE.md check. Nothing in src4 is modified.

src4 is found next to this directory (``<repo>/src4``) or at ``$SRC4_DIR``.
Bytecode writing is turned off so importing never writes into src4/.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from typing import Dict, List

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SRC4 = os.path.abspath(os.environ.get("SRC4_DIR") or os.path.join(HERE, "..", "src4"))
if not os.path.exists(os.path.join(SRC4, "run4.py")):
    raise ImportError(f"frozen harness not found at {SRC4} (set SRC4_DIR)")
if SRC4 not in sys.path:
    sys.path.insert(0, SRC4)

_ROW = re.compile(r"^\| `(.*)` \| `([0-9a-f]{64})` \|$")


def freeze_table(src4: str = SRC4) -> Dict[str, str]:
    with open(os.path.join(src4, "FREEZE.md")) as f:
        return {m.group(1): m.group(2) for m in (_ROW.match(line.rstrip("\n")) for line in f) if m}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_freeze(src4: str = SRC4) -> List[str]:
    """Mismatches between FREEZE.md and the files on disk (empty list: all frozen files unchanged)."""
    table = freeze_table(src4)
    if not table:
        return ["FREEZE.md has no hash rows"]
    bad = []
    for name, digest in sorted(table.items()):
        p = os.path.join(src4, name)
        if not os.path.exists(p):
            bad.append(f"{name}: missing")
        elif sha256_file(p) != digest:
            bad.append(f"{name}: sha256 differs from FREEZE.md")
    return bad


def own_hashes() -> Dict[str, str]:
    """sha256 of this driver's own source files (logged with every run)."""
    out = {}
    for fn in sorted(os.listdir(HERE)):
        if fn.endswith((".py", ".sh")):
            out[fn] = sha256_file(os.path.join(HERE, fn))
    return out


if __name__ == "__main__":
    problems = verify_freeze()
    print("\n".join(problems) if problems else f"FREEZE OK: {len(freeze_table())} files in {SRC4} match FREEZE.md")
    sys.exit(1 if problems else 0)
