#!/usr/bin/env python3
"""Compare two JSON files leaf by leaf, allowing floating-point noise.

    python3 -I compare_json.py A.json B.json [--rel 1e-9] [--abs 1e-9] [--show 20]

Exit 0 when every leaf is equal, or differs only by a float difference within the tolerances (|a-b| <= abs or
|a-b| <= rel * max(|a|, |b|)). Exit 1 on any other difference (a missing key, a different type or string, a float
outside the tolerance), listing up to --show of them. Numbers that are only float noise are counted and the largest
difference is printed, so "byte-identical or float-noise only" can be read off the last line.
"""
from __future__ import annotations

import argparse
import json
import math
import sys


def leaves(obj, path="$"):
    if isinstance(obj, dict):
        for k in sorted(obj):
            yield from leaves(obj[k], f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, f"{path}[{i}]")
    else:
        yield path, obj


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--rel", type=float, default=1e-9)
    ap.add_argument("--abs", type=float, default=1e-9)
    ap.add_argument("--show", type=int, default=20)
    args = ap.parse_args(argv)
    with open(args.a) as f:
        a = dict(leaves(json.load(f)))
    with open(args.b) as f:
        b = dict(leaves(json.load(f)))
    material, noise, max_diff, max_at = [], 0, 0.0, None
    for k in sorted(set(a) | set(b)):
        if k not in a or k not in b:
            material.append(f"{k}: only in {'B' if k not in a else 'A'}")
            continue
        x, y = a[k], b[k]
        if x == y and type(x) is type(y):
            continue
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool) \
                and not isinstance(y, bool) and math.isfinite(x) and math.isfinite(y):
            d = abs(x - y)
            if d <= args.abs or d <= args.rel * max(abs(x), abs(y)):
                noise += 1
                if d > max_diff:
                    max_diff, max_at = d, k
                continue
            material.append(f"{k}: {x!r} != {y!r}")
            continue
        material.append(f"{k}: {x!r} != {y!r}")
    print(f"leaves compared: {len(set(a) | set(b))}; identical: {len(set(a) | set(b)) - noise - len(material)}; "
          f"float noise within tolerance: {noise} (largest |a-b| = {max_diff:.3g}"
          + (f" at {max_at}" if max_at else "") + f"); material differences: {len(material)}")
    for m in material[:args.show]:
        print("  " + m)
    if len(material) > args.show:
        print(f"  ... {len(material) - args.show} more")
    if material:
        return 1
    print("OK: byte-identical" if noise == 0 else "OK: equal up to float noise")
    return 0


if __name__ == "__main__":
    sys.exit(main())
