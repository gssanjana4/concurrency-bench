"""Write src6/study2_costs.json: the observed Study 2 episode costs of the three Study 3 models (core blocks, aware
off, n = 2), per (model, config, family, arm): episodes, mean and max cost (USD, at the price the run paid: batch 0.5
for the Claude models, OpenRouter usage.cost for Qwen) and mean completions. Read from the Study 2 results.csv files;
used only by the Study 3 planner (src6/plan6.py) for the cost estimate. No Study 2 outcome is read.

    python3 -B tools/make_study2_costs.py --base /path/to/data/results5/study2 --out src6/study2_costs.json
"""
import argparse, collections, csv, glob, json, os

MODELS = ("openrouter:qwen/qwen3.6-27b-20260422", "claude-haiku-4-5-20251001", "claude-sonnet-5")
ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
acc = collections.defaultdict(list)
for p in sorted(glob.glob(os.path.join(a.base, "n2-*", "results.csv"))):
    for r in csv.DictReader(open(p)):
        if r["model"] not in MODELS or r["aware_prompt"] != "0" or r["probe"] != "0" or r["n_agents"] != "2":
            continue
        arm = "control" if r["category"] == "control" else "contended"
        acc[(r["model"], r["config"], r["family"], arm)].append((float(r["cost_usd"]), int(r["completions"])))
rows = {}
for (m, c, f, arm), v in sorted(acc.items()):
    rows[f"{m}|{c}|{f}|{arm}"] = {"episodes": len(v), "mean_usd": round(sum(x for x, _ in v) / len(v), 7),
                                  "max_usd": round(max(x for x, _ in v), 7),
                                  "mean_completions": round(sum(k for _, k in v) / len(v), 3)}
out = {"_README": "Observed Study 2 episode cost (USD) per model|config|family|arm (core blocks, aware off, n = 2), "
                  "from data/results5/study2/n2-*/results.csv columns cost_usd and completions only; input to "
                  "src6/plan6.py.", "rows": rows,
       "total_usd": round(sum(x for v in acc.values() for x, _ in v), 4), "episodes": sum(len(v) for v in acc.values())}
with open(a.out, "w") as f:
    json.dump(out, f, indent=1, sort_keys=True)
    f.write("\n")
print(f"{out['episodes']} episodes, ${out['total_usd']} -> {a.out}")
