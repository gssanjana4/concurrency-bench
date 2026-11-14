"""Analysis of the EXPLORATORY raw-SQL slice (post hoc, NOT pre-registered).

    python3 src_sql/analyze_sql.py results_sql/results.csv --out results_sql/analysis
    python3 src_sql/analyze_sql.py results_sql/dry_run/results.csv --out /tmp/x --include-dry-run

Reads results.csv (one row per episode) and the agents.csv next to it (one row
per agent). Dry-run rows are dropped unless --include-dry-run. Provider
failures (failures.jsonl next to each results.csv, episodes never written) are
counted and reported, never imputed.

Per model x template x n (plus "all templates" per model x n):
  * integrity: episodes with a data-invariant violation / episodes, Wilson 95%
    interval (episodes are the unit), with counts of primary kinds;
    report mismatch (finish claims vs committed effects) likewise;
  * protection behavior: share of agents with each flag (classify_sql), Wilson
    95% intervals with agents as the unit. Agents in one episode are not
    independent, so these intervals are descriptive approximations.
    ``retried_after_busy`` uses agents that got >= 1 busy error as denominator;
    ``atomic_pair`` is reported for the order template only.

Outputs in --out: numbers.json, tables.md and tables_appendix.tex (booktabs +
adjustbox, as in the paper). Every output is labelled EXPLORATORY.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BANNER = ("EXPLORATORY (post hoc, not pre-registered): raw-SQL slice with truly concurrent agents. "
          "Not part of the confirmatory analysis of PREREGISTRATION.md; no hypothesis tests.")

TEMPLATE_ORDER = ("counter", "handle", "withdraw", "order")
BEHAVIORS: Tuple[Tuple[str, str], ...] = (
    ("used_txn", "explicit txn"),
    ("txn_immediate", "BEGIN IMMEDIATE/EXCL."),
    ("rmw_in_txn", "read+write in one txn"),
    ("used_atomic_update", "atomic update"),
    ("used_conditional_update", "conditional update"),
    ("used_cas", "CAS (WHERE col = old)"),
    ("used_guarded_insert", "guarded INSERT"),
    ("added_constraint", "added constraint"),
    ("used_conflict_clause", "conflict clause"),
    ("checked_rows_affected", "checked rows affected"),
    ("retried_after_busy", "retried after BUSY"),
    ("blind_write", "blind write"),
    ("all_protected", "all writes protected"),
    ("left_txn_open", "left txn open"),
    ("atomic_pair", "stock+order in one txn"),
    ("no_write", "no write"),
)
TEX_BEHAVIORS = ("used_txn", "rmw_in_txn", "used_atomic_update", "used_cas", "used_guarded_insert", "added_constraint",
                 "checked_rows_affected", "blind_write", "all_protected")
MODEL_SHORT = {"claude-haiku-4-5-20251001": "Haiku 4.5", "openrouter:qwen/qwen3.6-27b-20260422": "Qwen3.6-27B"}


def wilson(k: int, n: int, z: float = 1.959963984540054) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(rate, lo, hi) Wilson score interval; (None, None, None) when n = 0."""
    if n <= 0:
        return None, None, None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def rate(k: int, n: int) -> Dict[str, Any]:
    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": p, "lo": lo, "hi": hi}


def fmt(r: Dict[str, Any]) -> str:
    if r["n"] == 0:
        return "-"
    return f"{r['k']}/{r['n']} ({r['rate']:.2f} [{r['lo']:.2f}, {r['hi']:.2f}])"


def fmt_short(r: Dict[str, Any]) -> str:
    return "-" if r["n"] == 0 else f"{r['rate']:.2f}"


def read_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load(paths: Sequence[str], include_dry: bool) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, Any]]:
    eps: List[Dict[str, str]] = []
    ags: List[Dict[str, str]] = []
    info: Dict[str, Any] = {"inputs": list(paths), "dropped_dry_run": 0, "provider_failures": 0, "failed_episode_ids": []}
    for p in paths:
        rows = read_csv(p)
        arows = read_csv(os.path.join(os.path.dirname(p), "agents.csv"))
        for r in rows:
            if r.get("dry_run") == "1" and not include_dry:
                info["dropped_dry_run"] += 1
                continue
            eps.append(r)
        keep = {r["episode_id"] for r in eps}
        ags.extend(a for a in arows if a["episode_id"] in keep)
        fpath = os.path.join(os.path.dirname(p), "failures.jsonl")
        if os.path.exists(fpath):
            done = {r["episode_id"] for r in rows}
            with open(fpath) as f:
                ids = sorted({json.loads(line)["episode_id"] for line in f if line.strip()})
            info["provider_failures"] += len(ids)
            info["failed_episode_ids"].extend(i for i in ids if i not in done)
    info["dry_run_input"] = any(r.get("dry_run") == "1" for r in eps)
    return eps, ags, info


def _key_order(models: Iterable[str], ns: Iterable[int]) -> Tuple[List[str], List[int]]:
    return sorted(set(models)), sorted(set(ns))


def analyze(eps: List[Dict[str, str]], ags: List[Dict[str, str]]) -> Dict[str, Any]:
    models, ns = _key_order((r["model"] for r in eps), (int(r["n_agents"]) for r in eps))
    templates = [t for t in TEMPLATE_ORDER if any(r["task"] == t for r in eps)]
    cells: "OrderedDict[str, Any]" = OrderedDict()
    for m in models:
        for n in ns:
            for t in templates + ["all"]:
                e = [r for r in eps if r["model"] == m and int(r["n_agents"]) == n and (t == "all" or r["task"] == t)]
                a = [r for r in ags if r["model"] == m and int(r["n_agents"]) == n and (t == "all" or r["task"] == t)]
                if not e:
                    continue
                viol = sum(int(r["violation"]) for r in e)
                kinds = Counter(r["primary_kind"] for r in e if r["primary_kind"])
                all_kinds = Counter(k for r in e for k in r["violation_kinds"].split("|") if k)
                rep_kinds = Counter(k for r in e for k in r["report_kinds"].split("|") if k)
                beh: Dict[str, Any] = {}
                for flag, _ in BEHAVIORS:
                    if flag == "atomic_pair" and t not in ("order",):
                        continue
                    if flag == "retried_after_busy":
                        den = [r for r in a if int(r.get("busy_errors") or 0) > 0]
                    else:
                        den = a
                    beh[flag] = rate(sum(int(r.get(flag) or 0) for r in den), len(den))
                beh["got_busy"] = rate(sum(1 for r in a if int(r.get("busy_errors") or 0) > 0), len(a))
                claims = Counter(r.get("claim") or "none" for r in a)
                blind_eps = [r for r in e if int(r.get("n_blind") or 0) > 0]
                clean_eps = [r for r in e if int(r.get("n_blind") or 0) == 0]
                cells[f"{m}|{n}|{t}"] = {
                    "model": m, "n_agents": n, "task": t, "episodes": len(e), "agents": len(a),
                    "violation": rate(viol, len(e)),
                    "primary_kinds": dict(kinds), "all_kinds": dict(all_kinds),
                    "report_mismatch": rate(sum(int(r["report_mismatch"]) for r in e), len(e)),
                    "report_kinds": dict(rep_kinds),
                    "violation_if_blind_writer": rate(sum(int(r["violation"]) for r in blind_eps), len(blind_eps)),
                    "violation_if_no_blind_writer": rate(sum(int(r["violation"]) for r in clean_eps), len(clean_eps)),
                    "behaviors": beh, "claims": dict(claims),
                    "cost_usd": round(sum(float(r["cost_usd"]) for r in e), 4),
                }
    return {"models": models, "n_agents": ns, "templates": templates, "cells": cells}


def tables_md(res: Dict[str, Any], info: Dict[str, Any]) -> str:
    L = [f"# Raw-SQL slice: tables", "", f"**{BANNER}**", ""]
    if info["dry_run_input"]:
        L += ["**DRY RUN INPUT (scripted fake agents): these numbers say nothing about models.**", ""]
    L += [f"Inputs: {', '.join(info['inputs'])}. Dry-run rows dropped: {info['dropped_dry_run']}. "
          f"Provider-failure episodes logged: {info['provider_failures']} "
          f"(never written; {len(info['failed_episode_ids'])} still missing).", ""]
    L += ["## Integrity (episodes)", "",
          "Violation = a data invariant failed on the final database (tasks_sql.check_integrity). "
          "Cells: k/n (rate [Wilson 95%]).", "",
          "| model | n | template | episodes | violation | primary kinds | report mismatch | viol. if blind writer | viol. if none |",
          "|---|---|---|---|---|---|---|---|---|"]
    for c in res["cells"].values():
        kinds = ", ".join(f"{k} {v}" for k, v in sorted(c["primary_kinds"].items(), key=lambda kv: -kv[1])) or "-"
        L.append(f"| {c['model']} | {c['n_agents']} | {c['task']} | {c['episodes']} | {fmt(c['violation'])} | {kinds} | "
                 f"{fmt(c['report_mismatch'])} | {fmt(c['violation_if_blind_writer'])} | {fmt(c['violation_if_no_blind_writer'])} |")
    L += ["", "## Protection behavior (agents)", "",
          "Share of agents with each flag (classify_sql docstring). Agents are not independent within an episode; "
          "intervals are descriptive. `retried after BUSY`: denominator = agents that got a busy error.", ""]
    for c in res["cells"].values():
        L.append(f"### {c['model']}, n = {c['n_agents']}, {c['task']} ({c['agents']} agents; claims {c['claims']})")
        L.append("")
        L.append("| behavior | agents |")
        L.append("|---|---|")
        L.append(f"| got a BUSY error | {fmt(c['behaviors']['got_busy'])} |")
        for flag, label in BEHAVIORS:
            if flag in c["behaviors"]:
                L.append(f"| {label} | {fmt(c['behaviors'][flag])} |")
        L.append("")
    return "\n".join(L) + "\n"


def _tex(s: str) -> str:
    return s.replace("\\", "\\textbackslash{}").replace("_", "\\_").replace("&", "\\&").replace("%", "\\%").replace("#", "\\#")


def _tex_rate(r: Dict[str, Any]) -> str:
    if r["n"] == 0:
        return "--"
    return f"{r['k']}/{r['n']} \\scriptsize[{r['lo']:.2f}, {r['hi']:.2f}]"


def tables_tex(res: Dict[str, Any], info: Dict[str, Any]) -> str:
    tag = "DRY RUN (fake agents) -- " if info["dry_run_input"] else ""
    labels = dict(BEHAVIORS)
    L = ["% GENERATED by src_sql/analyze_sql.py -- do not edit. " + BANNER,
         "% Input: " + ("DRY RUN (fake agents)" if info["dry_run_input"] else "real model runs") + ".",
         "\\begin{table*}[t]", "\\centering\\small", "\\begin{adjustbox}{max width=\\textwidth}",
         "\\begin{tabular}{llr" + "c" * (len(res["templates"]) + 1) + "}", "\\toprule",
         "Model & $n$ & episodes & " + " & ".join(_tex(t) for t in res["templates"]) + " & all \\\\", "\\midrule"]
    for m in res["models"]:
        for n in res["n_agents"]:
            row = [_tex(MODEL_SHORT.get(m, m)), str(n)]
            allc = res["cells"].get(f"{m}|{n}|all")
            if not allc:
                continue
            row.append(str(allc["episodes"]))
            for t in res["templates"] + ["all"]:
                c = res["cells"].get(f"{m}|{n}|{t}")
                row.append(_tex_rate(c["violation"]) if c else "--")
            L.append(" & ".join(row) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}", "\\end{adjustbox}",
          "\\caption{" + tag + "EXPLORATORY, post hoc, not pre-registered. Raw-SQL slice: episodes whose final database "
          "violates the template's data invariant (violations/episodes, Wilson 95\\% interval). Agents share one SQLite "
          "file (WAL) through a \\texttt{run\\_sql} tool, each on its own connection, truly concurrently.}",
          "\\label{tab:sql-integrity}", "\\end{table*}", "",
          "\\begin{table*}[t]", "\\centering\\small", "\\begin{adjustbox}{max width=\\textwidth}",
          "\\begin{tabular}{ll" + "c" * len(TEX_BEHAVIORS) + "}", "\\toprule",
          "Model & $n$ & " + " & ".join(_tex(labels[b]) for b in TEX_BEHAVIORS) + " \\\\", "\\midrule"]
    for m in res["models"]:
        for n in res["n_agents"]:
            c = res["cells"].get(f"{m}|{n}|all")
            if not c:
                continue
            L.append(" & ".join([_tex(MODEL_SHORT.get(m, m)), str(n)]
                                + [fmt_short(c["behaviors"][b]) for b in TEX_BEHAVIORS]) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}", "\\end{adjustbox}",
          "\\caption{" + tag + "EXPLORATORY, post hoc, not pre-registered. Share of agents showing each SQL behavior, "
          "all four templates pooled (definitions in \\texttt{src\\_sql/classify\\_sql.py}; flags overlap). A blind write "
          "is an effective write to the contended table protected by none of: read and write in one transaction, an "
          "in-place update, a compare-and-set \\texttt{WHERE}, a guarded \\texttt{INSERT}, a \\texttt{UNIQUE} index.}",
          "\\label{tab:sql-behavior}", "\\end{table*}"]
    return "\n".join(L) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("results", nargs="+", help="results.csv file(s)")
    p.add_argument("--out", required=True)
    p.add_argument("--include-dry-run", action="store_true")
    args = p.parse_args(argv)
    eps, ags, info = load(args.results, args.include_dry_run)
    if not eps:
        print("no episodes to analyse (dry-run rows need --include-dry-run)", file=sys.stderr)
        return 1
    res = analyze(eps, ags)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "numbers.json"), "w") as f:
        json.dump({"label": BANNER, "info": info, **res}, f, indent=1, sort_keys=False)
    with open(os.path.join(args.out, "tables.md"), "w") as f:
        f.write(tables_md(res, info))
    with open(os.path.join(args.out, "tables_appendix.tex"), "w") as f:
        f.write(tables_tex(res, info))
    print(BANNER)
    print(f"{len(eps)} episodes, {len(ags)} agents -> {args.out}/numbers.json, tables.md, tables_appendix.tex")
    for c in res["cells"].values():
        if c["task"] == "all":
            print(f"  {c['model']} n={c['n_agents']}: violation {fmt(c['violation'])}; "
                  f"blind-writer agents {fmt(c['behaviors']['blind_write'])}; txn {fmt(c['behaviors']['used_txn'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
