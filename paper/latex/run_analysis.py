#!/usr/bin/env python3
"""Run the frozen src4/analyze4.py without modifying it.

    python3 run_analysis.py [--dry-run | CSV ...] --out DIR

Real data: analyze4.py is called on the given CSVs as-is.

Dry-run data: analyze4.py drops every row with dry_run = 1 (correct for the
paper), so on dry-run CSVs it analyses 0 episodes. To exercise the pipeline,
this wrapper copies each dry-run CSV to DIR/_staged_dryrun/phaseN/results.csv
with the dry_run column set to 0, symlinks the transcripts directory next to
it (H5 reads transcripts relative to the CSV), copies failures.jsonl if
present, and runs analyze4.py on the staged copies. Staging happens ONLY when
the inputs are dry-run (path component ``dry_run`` or rows with dry_run = 1);
the result is marked in DIR/provenance.json (``dry_run: true``) and every
downstream output carries a DRY RUN watermark.

Refuses to run if src4 FREEZE hashes do not verify.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys

from pipeline_common import (SRC4, default_inputs, detect_dry_run, require_freeze, sha256_file)


def stage(paths, out):
    staged = []
    root = os.path.join(out, "_staged_dryrun")
    if os.path.isdir(root):
        shutil.rmtree(root)
    for i, p in enumerate(paths):
        src_dir = os.path.dirname(os.path.abspath(p))
        # phaseN name from the path when available, else index
        parts = os.path.normpath(src_dir).split(os.sep)
        tag = next((x for x in reversed(parts) if x.startswith("phase")), f"input{i}")
        d = os.path.join(root, tag)
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, "results.csv")
        with open(p, newline="") as fi, open(dst, "w", newline="") as fo:
            r = csv.DictReader(fi)
            w = csv.DictWriter(fo, fieldnames=r.fieldnames, lineterminator="\n")
            w.writeheader()
            for row in r:
                row["dry_run"] = "0"
                w.writerow(row)
        tr = os.path.join(src_dir, "transcripts")
        if os.path.isdir(tr):
            os.symlink(tr, os.path.join(d, "transcripts"))
        fj = os.path.join(src_dir, "failures.jsonl")
        if os.path.exists(fj):
            shutil.copy(fj, os.path.join(d, "failures.jsonl"))
        staged.append(dst)
    return staged


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="*")
    ap.add_argument("--dry-run", action="store_true", help="use results4/full/phase*/dry_run/results.csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    freeze = require_freeze()
    paths = a.csv or default_inputs(a.dry_run)
    for p in paths:
        if not os.path.exists(p):
            raise SystemExit(f"input not found: {p}")
    dry = detect_dry_run(paths)
    os.makedirs(a.out, exist_ok=True)
    run_paths = stage(paths, a.out) if dry else list(paths)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, os.path.join(SRC4, "analyze4.py"), *run_paths, "--out", a.out]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)
    prov = {
        "dry_run": dry,
        "inputs": [{"path": os.path.abspath(p), "sha256": sha256_file(p)} for p in paths],
        "analyzed_paths": [os.path.abspath(p) for p in run_paths],
        "staged_dry_run_flag_cleared": dry,
        "analyze4_sha256": freeze["analyze4.py"],
        "freeze_verified": True,
    }
    with open(os.path.join(a.out, "provenance.json"), "w") as f:
        json.dump(prov, f, indent=1)
        f.write("\n")
    print(f"provenance: dry_run={dry}; wrote {a.out}/provenance.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
