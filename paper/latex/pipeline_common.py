"""Shared helpers for the paper pipeline (read-only with respect to src4).

- verify_freeze(): recompute sha256 of every file listed in src4/FREEZE.md and
  compare. Every pipeline step calls it and refuses to run on a mismatch. In the
  anonymized review artifact only, FREEZE_OVERRIDE.json (written by
  make_anon_artifact.py) lets exactly the redacted bytes of the redacted frozen
  files pass; see freeze_override().
- detect_dry_run(): an input set counts as dry-run if any path has a
  ``dry_run`` component or any CSV row has dry_run = 1.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
from typing import Dict, List, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)                          # paper-concurrency/
ROOT = os.path.dirname(PAPER)                          # /home/claude
SRC4 = os.environ.get("SRC4", os.path.join(ROOT, "src4"))
RESULTS = os.environ.get("RESULTS4", os.path.join(ROOT, "results4", "full"))

_ROW = re.compile(r"^\| `(.+)` \| `([0-9a-f]{64})` \|$")


class FreezeError(RuntimeError):
    pass


def freeze_table(src4: str = SRC4) -> Dict[str, str]:
    path = os.path.join(src4, "FREEZE.md")
    if not os.path.exists(path):
        raise FreezeError(f"{path} not found")
    out = {}
    with open(path) as f:
        for line in f:
            m = _ROW.match(line.rstrip("\n"))
            if m:
                out[m.group(1)] = m.group(2)
    if not out:
        raise FreezeError("FREEZE.md lists no files")
    return out


OVERRIDE_NAME = "FREEZE_OVERRIDE.json"


def freeze_override(src4: str = SRC4) -> Dict[str, Dict[str, str]]:
    """Documented FREEZE override of the anonymized review artifact (empty outside it).

    ``make_anon_artifact.py`` writes ``FREEZE_OVERRIDE.json`` next to the artifact's ``src4/`` only for frozen
    files that it redacted for anonymity, after checking that the ORIGINAL file's sha256 equals its FREEZE.md
    hash. Each entry records ``frozen_sha256`` (= original) and ``redacted_sha256``. A listed file is accepted only
    if its FREEZE.md hash equals ``frozen_sha256`` and its current bytes hash to ``redacted_sha256`` exactly, so
    the override accepts these redacted bytes and nothing else. ANON_CHANGES.md lists every changed line.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(src4)), OVERRIDE_NAME)
    if not os.path.exists(path):
        return {}
    import json
    with open(path) as f:
        data = json.load(f)
    return {e["file"]: e for e in data.get("redacted_frozen_files", [])}


def verify_freeze(src4: str = SRC4) -> Tuple[Dict[str, str], List[str]]:
    """Return (table, problems). problems is empty iff every hash verifies (or matches the documented override)."""
    table = freeze_table(src4)
    override = freeze_override(src4)
    problems = []
    for name, want in table.items():
        p = os.path.join(src4, name)
        if not os.path.exists(p):
            problems.append(f"{name}: missing")
            continue
        with open(p, "rb") as f:
            got = hashlib.sha256(f.read()).hexdigest()
        if got != want:
            o = override.get(name)
            if o and o.get("frozen_sha256") == want and o.get("redacted_sha256") == got:
                continue  # documented anonymity redaction (FREEZE_OVERRIDE.json, ANON_CHANGES.md)
            problems.append(f"{name}: sha256 {got} != frozen {want}")
    return table, problems


def require_freeze(src4: str = SRC4) -> Dict[str, str]:
    table, problems = verify_freeze(src4)
    if problems:
        raise SystemExit("REFUSING TO RUN: src4 FREEZE hashes do not verify:\n  " + "\n  ".join(problems))
    return table


def path_is_dry(p: str) -> bool:
    return "dry_run" in os.path.normpath(os.path.abspath(p)).split(os.sep)


def csv_has_dry_rows(p: str) -> bool:
    with open(p, newline="") as f:
        for row in csv.DictReader(f):
            if str(row.get("dry_run", "0")).strip() not in ("", "0"):
                return True
    return False


def detect_dry_run(paths: Sequence[str]) -> bool:
    return any(path_is_dry(p) or csv_has_dry_rows(p) for p in paths)


def sha256_file(p: str) -> str:
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def default_inputs(dry: bool) -> List[str]:
    sub = "dry_run" if dry else ""
    return [os.path.join(RESULTS, f"phase{i}", sub, "results.csv") for i in (1, 2, 3)]
