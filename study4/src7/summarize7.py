"""Descriptive summary of Study 2 results (no inference): outcomes, flags, choices, cap endings, interleavings.

    python3 summarize7.py results5/study2/n2/results.csv [more.csv ...] [--out summary.md]

Per (model, n, config, aware, contended|control): episodes, outcome shares (clean / compensated / failed), the
failed primary labels, fs_nonserializable and dsg_cycle rates, ever_violated, agent-level lock / CAS / promote /
compensate / message use, fulfilled share, agents ending at the call cap. Then the interleaving distribution
(first mover, reads_overlap, top patterns) per model, and the spend per provider family recorded in the rows.

V2: lock use is reported as attempted (the primary measure) / granted / effective; deadlock episodes, agents that
ended truncated / provider_error / error (refusal / content_filter ends are in ``end_reasons``), and control episodes with a delivered message (not verified
uncontended: reported separately) get their own columns; first-reply probe rows (``probe`` = 1) get their own
table of first-reply codes per (model, config, aware, arm).

Round 3: ``exposure`` = share of agents with a peer-caused contention signal (the manipulation check; 0 in
controls), ``cap-trunc`` = failed episodes with a cap ending (stratum); episodes without their matched partner
are dropped and counted.
"""

from __future__ import annotations

import argparse
import collections
import csv
import sys
from typing import Dict, List


def load(paths: List[str]) -> List[Dict[str, str]]:
    rows: Dict[str, Dict[str, str]] = {}
    for p in paths:
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                rows[r["episode_id"]] = r
    return list(rows.values())


def choice_share(rows: List[Dict[str, str]], choice: str) -> float:
    agents = [c for r in rows for c in r["choices"].split(";") if c]
    return sum(choice in c.split(":", 1)[1].split("|") for c in agents) / max(len(agents), 1)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="+")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    rows = load(a.csv)
    probes = [r for r in rows if r.get("probe") == "1"]
    rows = [r for r in rows if r.get("probe") != "1"]
    import run7  # noqa: PLC0415
    lone = set(run7.unpaired(rows))  # Round 3: an episode without its matched partner is dropped (should be none)
    rows = [r for r in rows if r["episode_id"] not in lone]
    cells = collections.defaultdict(list)
    for r in rows:
        arm = "control" if r["category"] == "control" else "contended"
        cells[(r["model"], r["n_agents"], r["config"], r["aware_prompt"], arm)].append(r)
    out = ["| model | n | config | aware | arm | eps | clean | comp. | failed | top failed labels | fs | dsg | basis dsg "
           "| ever viol. | lock att/gr/eff | cas | promote | msg | fulfilled | cap ends | deadlocks | agent errors "
           "| ctrl w/ msg | exposure | cap-trunc |", "|" + "---|" * 25]
    for k in sorted(cells):
        rs = cells[k]
        n = len(rs)
        oc = collections.Counter(r["outcome"] for r in rs)
        labels = collections.Counter(r["primary_label"] for r in rs if r["outcome"] == "failed").most_common(2)
        n_agents = sum(int(r["n_agents"]) for r in rs)
        out.append(
            f"| {k[0].split('/')[-1]} | {k[1]} | {k[2]} | {k[3]} | {k[4]} | {n} | {oc['clean'] / n:.2f} | {oc['compensated'] / n:.2f} "
            f"| {oc['failed'] / n:.2f} | {', '.join(f'{l} {c}' for l, c in labels)} "
            f"| {sum(int(r['fs_nonserializable']) for r in rs) / n:.2f} | {sum(int(r['dsg_cycle']) for r in rs) / n:.2f} "
            f"| {sum(int(r.get('dsg_basis_cycle') or 0) for r in rs) / n:.2f} "
            f"| {sum(int(r['ever_violated']) for r in rs) / n:.2f} | {choice_share(rs, 'lock'):.2f}/"
            f"{sum(int(r.get('lock_granted_agents') or 0) for r in rs) / n_agents:.2f}/"
            f"{sum(int(r.get('lock_effective_agents') or 0) for r in rs) / max(sum(int(r.get('lock_committed_agents') or 0) for r in rs), 1):.2f} "
            f"| {choice_share(rs, 'cas'):.2f} "
            f"| {choice_share(rs, 'promote'):.2f} | {choice_share(rs, 'message'):.2f} "
            f"| {sum(int(r['n_fulfilled']) for r in rs) / n_agents:.2f} | {sum(int(r['cap_endings']) for r in rs)}/{n_agents} "
            f"| {sum(int(r.get('deadlock') or 0) for r in rs)} | {sum(int(r.get('agent_errors') or 0) for r in rs)} "
            f"| {sum(1 for r in rs if k[4] == 'control' and int(r.get('messages_delivered') or 0) > 0)} "
            f"| {sum(int(r.get('contention_exposed_agents') or 0) for r in rs) / n_agents:.2f} "
            f"| {sum(int(r.get('cap_truncated') or 0) for r in rs)} |")
    if probes:
        pc = collections.defaultdict(collections.Counter)
        for r in probes:
            arm = "control" if r["category"] == "control" else "contended"
            for item in r["first_replies"].split(";"):
                if ":" in item:
                    agent, code = item.split(":", 1)
                    pc[(r["model"], r["config"], r["aware_prompt"], arm)][code] += 1
        out += ["", "## First-reply probes (one completion per agent; codes from model_agent7.first_reply_code)", "",
                "| model | config | aware | arm | probes | first-reply codes |", "|---|---|---|---|---|---|"]
        for k in sorted(pc):
            c = pc[k]
            out.append(f"| {k[0].split('/')[-1]} | {k[1]} | {k[2]} | {k[3]} | {sum(c.values())} | "
                       + ", ".join(f"{code} {v}" for code, v in c.most_common()) + " |")
    out += ["", "## Interleavings (contended episodes)", ""]
    by_model = collections.defaultdict(list)
    for r in rows:
        if r["category"] != "control":
            by_model[r["model"]].append(r)
    for m, rs in sorted(by_model.items()):
        movers = collections.Counter(r["first_mover"] or "-" for r in rs)
        pats = collections.Counter(r["interleaving"] for r in rs).most_common(5)
        out.append(f"- {m}: {len(rs)} episodes; first mover {dict(movers)}; reads overlap "
                   f"{sum(int(r['reads_overlap']) for r in rs) / len(rs):.2f}; top patterns {pats}")
    out += ["", f"Episodes dropped because their matched partner is missing: {len(lone)}"]
    spend = collections.defaultdict(float)
    for r in rows + probes:
        spend[r["provider_family"]] += float(r["cost_usd"])
    out += ["", f"Recorded episode cost by provider family: {dict((k, round(v, 2)) for k, v in spend.items())}", ""]
    text = "\n".join(out)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
