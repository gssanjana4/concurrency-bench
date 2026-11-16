#!/usr/bin/env python3
"""Observed Study 3 contended-episode cost per model|config|family (together start), for the Study 4 planner.

    python3 tools/make_study3_costs.py DATA_DIR > src7/study3_costs.json

DATA_DIR holds the Study 3 results (results6/study3 or the artifact's data/results6/study3): n2-*/results.csv,
columns model, config, start_mode, task, family, cost_usd, completions. Only contended episodes under the together
start and the configs locks_s2text and locks are kept (the configs Study 4's estimate is built from).
"""
import csv
import glob
import json
import os
import sys

rows = {}
for path in sorted(glob.glob(os.path.join(sys.argv[1], "n2-*", "results.csv"))):
    for r in csv.DictReader(open(path)):
        if r["task"].endswith("_ctrl") or r.get("start_mode", "together") != "together" or r["config"] not in ("locks_s2text", "locks"):
            continue
        k = f"{r['model']}|{r['config']}|{r['family']}"
        d = rows.setdefault(k, {"episodes": 0, "sum_usd": 0.0, "max_usd": 0.0, "sum_completions": 0})
        c = float(r["cost_usd"] or 0)
        d["episodes"] += 1; d["sum_usd"] += c; d["max_usd"] = max(d["max_usd"], c)
        d["sum_completions"] += int(float(r.get("completions") or 0))
out = {k: {"episodes": v["episodes"], "mean_usd": round(v["sum_usd"] / v["episodes"], 6), "max_usd": round(v["max_usd"], 6),
           "mean_completions": round(v["sum_completions"] / v["episodes"], 2)} for k, v in sorted(rows.items())}
json.dump({"_README": "Observed Study 3 cost (USD) per contended episode, model|config|family, together start; input "
                      "to src7/plan7.py (tools/make_study3_costs.py).", "rows": out,
           "total_usd": round(sum(v["sum_usd"] for v in rows.values()), 4)}, sys.stdout, indent=1, sort_keys=True)
print()
