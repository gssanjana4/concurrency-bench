"""Reference-policy validity table (the built-in manipulation check), checker agreement and interleaving report.

    python3 validity5.py --out validity            # writes validity/validity.json and validity/validity.md

For every scripted policy x template family x Study 2 configuration that offers the policy's primitive x
n in {2, 4}, it runs every instance (``--instances``, default 4) under every schedule (``--schedules``,
default 8) on the contended template and on its matched control, at the Study 2 call cap, and checks:

* correct protocols (``agents5.CORRECT``): contended outcomes only ``clean`` (``clean`` or ``compensated``
  for verify_and_compensate); control outcomes only ``clean``; no cap ending; the most calls any agent used
  <= 80 % of the cap. At n = 4 the write-skew protocols are reported but not required (Study 2 runs n = 2).
* naive policies (``agents5.NAIVE_FOR``): contended failure rate >= 0.10; controls all ``clean``.
* probes (two lock-misuse rejection probes and the lock-order deadlock diagnostic): never ``failed``.
* controls: zero cross-agent edges in every episode (record DSG edges plus delivered messages), and (Round 3,
  review V2b C1) zero agents with a peer-caused contention signal (``score5.peer_signal_calls``).
* locks: the lease-aware mutual-exclusion gate (``score5.mutual_exclusion_violations``: every fenced write inside
  its token's validity window, no write by a non-holder while a lock is live).

V2 rows (reviews V1 B1, B5, V2 F5): ``naive_claim`` and ``cas_claim`` on seat/ticket, ``reacquire_no_reread`` and
``lease_then_tokenless`` (naive under locks), ``lock_own_first`` (deadlock diagnostic). Each row also reports the
share of agents that attempted / were granted / used a lock effectively, fenced writes with a stale basis, lock
waits granted vs 423, and deadlock episodes.

It also reports the agreement of ``fs_nonserializable`` with the all-reads DSG (``dsg_cycle``) and the per-write
basis DSG (``dsg_basis_cycle``) with the disagreement classes; a large-sample tail of the write-skew protocols
(``--tail-schedules`` schedules per instance: share above 80 % of the cap, cap endings); and the interleaving
distribution of the Study 2 scheduler next to a Study-1-like schedule (fixed gap 2, no jitter, no latency), plus
naive-vs-rereader failure rates under both.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from typing import Any, Dict, List, Tuple

import agents5 as A
import instances5 as I
from design5 import CAP_MARGIN, CONFIGS, SCHEDULE_DEFAULTS, SCHEDULE_SPACE, call_cap
from scheduler5 import ScheduleConfig, run_episode, schedule_seed
from score5 import mutual_exclusion_violations, score_episode
from world5 import world_config

NAIVE_MIN_FAIL = 0.10
STUDY1_LIKE = {"gap_min": 2, "gap_max": 2, "start_jitter": 0, "latency_p": 0.0, "latency_max": 0}


def schedule_for(template: str, instance: int, s: int, n: int, config: str, overrides: Dict[str, Any] = None) -> ScheduleConfig:
    kw = dict(SCHEDULE_DEFAULTS)
    kw.update(overrides or {})
    fam = I.family_of(template)  # contended task and control share the schedule seed
    return ScheduleConfig(seed=schedule_seed(SCHEDULE_SPACE, fam, instance, s, n), turn_cap=call_cap(n, config), **kw)


def run_cell(policy: str, template: str, config: str, n: int, k: int, s_count: int, overrides=None) -> List[Any]:
    spec = A.REFERENCE_POLICIES[policy]
    wc = world_config(config)
    out = []
    for i in range(k):
        task = I.build(template, i, n)
        for s in range(s_count):
            ep = run_episode(task, spec, wc, schedule_for(template, i, s, n, config, overrides))
            sc = score_episode(ep)
            out.append((ep, sc))
    return out


def summarize(results: List[Any], cap: int) -> Dict[str, Any]:
    outcomes = collections.Counter(sc.outcome for _, sc in results)
    labels = collections.Counter(sc.primary_label for _, sc in results if sc.outcome == "failed")
    agents = [a for _, sc in results for a in sc.agents.values()]
    maxcalls = max(a.turns for a in agents)
    waits = [(c.status == 200) for ep, _ in results for c in ep.ledger.calls if c.tool == "acquire_lock" and c.waited_rounds]
    return {
        "episodes": len(results), "outcomes": dict(outcomes), "failed_labels": dict(labels),
        "fail_rate": outcomes["failed"] / len(results),
        "fulfilled_rate": sum(a.fulfilled for a in agents) / len(agents),
        "max_calls": maxcalls, "cap": cap, "max_calls_share": round(maxcalls / cap, 3),
        "cap_endings": sum(sc.cap_endings for _, sc in results),
        "cross_agent_edges": sum(sc.cross_agent_edges for _, sc in results),
        "messages_delivered": sum(sc.messages_delivered for _, sc in results),
        "mutex_violations": sum(len(mutual_exclusion_violations(ep.ledger)) for ep, _ in results),
        "flags": {f: sum(sc.flags[f] for _, sc in results) for f in results[0][1].flags},
        "lock_attempt_share": round(sum(a.lock for a in agents) / len(agents), 3),
        "lock_granted_share": round(sum(a.lock_granted for a in agents) / len(agents), 3),
        "lock_effective_share": (round(sum(bool(a.lock_effective) for a in agents) /
                                       sum(a.lock_effective is not None for a in agents), 3)
                                 if any(a.lock_effective is not None for a in agents) else None),
        "fenced_stale_basis_writes": sum(a.fenced_stale_basis for a in agents),
        "lock_waits": len(waits), "lock_waits_423": sum(1 for w in waits if not w),
        "deadlock_episodes": sum(sc.deadlock for _, sc in results),
        # Round 3: exposure (agents with a peer-caused contention signal; must be 0 in every control), the
        # cap-truncation stratum and locked writes without a read under their token
        "contention_agents": sum(a.contention_signals > 0 for a in agents),
        "contention_share": round(sum(a.contention_signals > 0 for a in agents) / len(agents), 3),
        "cap_truncated": sum(sc.cap_truncated for _, sc in results),
        "fenced_unread_basis_writes": sum(a.fenced_unread_basis for a in agents),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "validity"))
    p.add_argument("--instances", type=int, default=4)
    p.add_argument("--schedules", type=int, default=8)
    p.add_argument("--agents", default="2,4")
    p.add_argument("--tail-schedules", type=int, default=50, help="schedules per instance in the write-skew tail check")
    a = p.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    agree = collections.Counter()
    agree3 = collections.Counter()
    disagree_classes = collections.Counter()
    basis_classes = collections.Counter()
    problems: List[str] = []
    for n in [int(x) for x in a.agents.split(",")]:
        for fam in I.CONTENDED:
            for policy, spec in A.REFERENCE_POLICIES.items():
                if not A.applicable(policy, fam):
                    continue
                role = ("correct" if policy in A.CORRECT[fam] else "naive" if policy in A.NAIVE_FOR[fam]
                        else "probe" if policy in A.PROBES else None)
                if role is None:
                    continue
                for config in CONFIGS:
                    if not spec.supported_by(world_config(config).coordination):
                        continue
                    cap = call_cap(n, config)
                    cont = run_cell(policy, fam, config, n, a.instances, a.schedules)
                    ctrl = run_cell(policy, fam + I.CONTROL_SUFFIX, config, n, a.instances, a.schedules)
                    for _, sc in cont + ctrl:
                        agree[(sc.fs_nonserializable, sc.dsg_cycle)] += 1
                        agree3[(sc.fs_nonserializable, sc.dsg_cycle, sc.dsg_basis_cycle)] += 1
                        if sc.fs_nonserializable != sc.dsg_cycle:
                            disagree_classes[(policy, "fs_only" if sc.fs_nonserializable else "dsg_only",
                                              sc.primary_label or sc.outcome)] += 1
                        if sc.fs_nonserializable != sc.dsg_basis_cycle:
                            basis_classes[(policy, "fs_only" if sc.fs_nonserializable else "basis_only",
                                           sc.primary_label or sc.outcome,
                                           "compensation_exposed" if sc.flags["compensation_exposed"] else "-")] += 1
                    rc, rk = summarize(cont, cap), summarize(ctrl, cap)
                    required = not (n > 2 and fam in A.WRITE_SKEW_FAMILIES and role == "correct")
                    if role == "correct":
                        allowed = {"clean", "compensated"} if policy == "verify_and_compensate" else {"clean"}
                        ok = (set(rc["outcomes"]) <= allowed and set(rk["outcomes"]) == {"clean"} and rc["cap_endings"] == 0
                              and rk["cap_endings"] == 0 and max(rc["max_calls_share"], rk["max_calls_share"]) <= CAP_MARGIN)
                    elif role == "naive":
                        ok = rc["fail_rate"] >= NAIVE_MIN_FAIL and set(rk["outcomes"]) == {"clean"}
                    else:
                        ok = rc["outcomes"].get("failed", 0) == 0 and rk["outcomes"].get("failed", 0) == 0
                    ok = ok and rk["cross_agent_edges"] == 0 and rc["mutex_violations"] == 0 and rk["mutex_violations"] == 0
                    ok = ok and rk["contention_agents"] == 0  # Round 3 (V2b C1): no contention signal in any control
                    row = {"n": n, "family": fam, "policy": policy, "role": role, "config": config, "cap": cap,
                           "contended": rc, "control": rk, "pass": ok, "required": required}
                    rows.append(row)
                    if required and not ok:
                        problems.append(f"n={n} {fam} {policy} {config}: contended {rc['outcomes']} control {rk['outcomes']} "
                                        f"max calls {max(rc['max_calls'], rk['max_calls'])}/{cap}")
                    print(f"{'PASS' if ok else ('FAIL' if required else 'info')} n={n} {config:13s} {fam:25s} {policy:22s} "
                          f"cont {rc['outcomes']} ctrl {rk['outcomes']} maxcalls {max(rc['max_calls'], rk['max_calls'])}/{cap}",
                          flush=True)

    # tail of the write-skew protocols on a larger sample (n = 2): livelock is geometric, so report it
    tail = []
    for fam in A.WRITE_SKEW_FAMILIES:
        for policy in A.CORRECT[fam]:
            spec = A.REFERENCE_POLICIES[policy]
            for config in CONFIGS:
                if not spec.supported_by(world_config(config).coordination):
                    continue
                cap = call_cap(2, config)
                res = run_cell(policy, fam, config, 2, 8, a.tail_schedules)
                calls = sorted(max(x.turns for x in sc.agents.values()) for _, sc in res)
                tail.append({"family": fam, "policy": policy, "config": config, "episodes": len(res), "cap": cap,
                             "outcomes": dict(collections.Counter(sc.outcome for _, sc in res)),
                             "above_margin": sum(c > CAP_MARGIN * cap for c in calls),
                             "cap_endings": sum(sc.cap_endings for _, sc in res),
                             "p95": calls[int(0.95 * len(calls))], "p99": calls[int(0.99 * len(calls))], "max": calls[-1]})
                print(f"tail {fam:25s} {policy:22s} {config:13s} {tail[-1]['outcomes']} >80%: {tail[-1]['above_margin']}/"
                      f"{len(res)} caps {tail[-1]['cap_endings']} p99 {tail[-1]['p99']} max {tail[-1]['max']}/{cap}", flush=True)

    # interleavings: Study 2 scheduler vs a Study-1-like schedule (naive and rereader, contended, n = 2)
    inter: Dict[str, Any] = {}
    for label, ov in (("study2", None), ("study1_like", STUDY1_LIKE)):
        pats, movers, overlap, total = collections.Counter(), collections.Counter(), 0, 0
        fail = {}
        for policy in ("naive", "rereader"):
            f = c = 0
            for fam in I.CONTENDED:
                for ep, sc in run_cell(policy, fam, "none", 2, a.instances, a.schedules, ov):
                    c += 1
                    f += sc.outcome == "failed"
                    if policy == "naive":
                        total += 1
                        pats[sc.interleaving["pattern"]] += 1
                        movers[sc.interleaving["first_mover"]] += 1
                        overlap += sc.interleaving["reads_overlap"]
            fail[policy] = round(f / c, 3)
        inter[label] = {"episodes": total, "first_mover": dict(movers), "reads_overlap_share": round(overlap / total, 3),
                        "distinct_patterns": len(pats), "top_patterns": pats.most_common(8), "fail_rate_none": fail}
    out = {"rows": rows, "problems": problems,
           "agreement": {f"fs={k[0]} dsg={k[1]}": v for k, v in sorted(agree.items())},
           "agreement_basis": {f"fs={k[0]} dsg={k[1]} basis={k[2]}": v for k, v in sorted(agree3.items())},
           "disagreement_classes": [{"policy": k[0], "side": k[1], "class": k[2], "episodes": v}
                                    for k, v in sorted(disagree_classes.items(), key=lambda x: -x[1])],
           "basis_disagreement_classes": [{"policy": k[0], "side": k[1], "class": k[2], "exposed": k[3], "episodes": v}
                                          for k, v in sorted(basis_classes.items(), key=lambda x: -x[1])],
           "tail": tail, "tail_schedules": a.tail_schedules,
           "interleavings": inter, "instances": a.instances, "schedules": a.schedules}
    with open(os.path.join(a.out, "validity.json"), "w") as f:
        json.dump(out, f, indent=1, sort_keys=True, default=str)
    with open(os.path.join(a.out, "validity.md"), "w") as f:
        f.write(render_md(out))
    print(f"\n{len(rows)} rows; required failures: {len(problems)}")
    for pr in problems:
        print("  !!", pr)
    return 1 if problems else 0


def _oc(d: Dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(d.items()))


def render_md(out: Dict[str, Any]) -> str:
    lines = [f"# Reference policy validity table ({out['instances']} instances x {out['schedules']} schedules per cell)", "",
             "Lock columns (contended): attempted / granted share of agents, effective share of the agents that were "
             "granted a lock and committed a write; fenced writes with a stale basis; lock waits (423 after the full "
             "wait); deadlock episodes. Exposure (Round 3): share of agents with a peer-caused contention signal, "
             "contended / control (the control must be 0); cap-truncated failed episodes (contended).", "",
             "| n | family | policy | role | config | contended outcomes | control | fulfilled (cont.) | max calls / cap "
             "| lock att/gr/eff | stale-basis fenced | waits (423) | deadlocks | exposure c/k | cap-trunc | pass |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in out["rows"]:
        c, k = r["contended"], r["control"]
        mark = "yes" if r["pass"] else ("NO" if r["required"] else "n/a (not required)")
        eff = "n/a" if c["lock_effective_share"] is None else f"{c['lock_effective_share']:.2f}"
        lk = f"{c['lock_attempt_share']:.2f}/{c['lock_granted_share']:.2f}/{eff}" if c["lock_attempt_share"] else "-"
        lines.append(f"| {r['n']} | {r['family']} | {r['policy']} | {r['role']} | {r['config']} | {_oc(c['outcomes'])}"
                     f"{' (' + _oc(c['failed_labels']) + ')' if c['failed_labels'] else ''} | {_oc(k['outcomes'])} | "
                     f"{c['fulfilled_rate']:.2f} | {max(c['max_calls'], k['max_calls'])} / {r['cap']} | {lk} | "
                     f"{c['fenced_stale_basis_writes']} | {c['lock_waits']} ({c['lock_waits_423']}) | {c['deadlock_episodes']} | "
                     f"{c['contention_share']:.2f}/{k['contention_share']:.2f} | {c['cap_truncated']} | {mark} |")
    lines += ["", "## Checker agreement (all validity episodes)", "", "| | count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in out["agreement"].items()]
    lines += ["", "All-reads DSG vs fs disagreement classes (definitional; see score5):", "",
              "| policy | side | class | episodes |", "|---|---|---|---|"]
    lines += [f"| {d['policy']} | {d['side']} | {d['class']} | {d['episodes']} |" for d in out["disagreement_classes"][:30]]
    lines += ["", "### Three verdicts: fs, all-reads DSG, per-write basis DSG", "", "| | count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in out["agreement_basis"].items()]
    lines += ["", "fs vs basis-DSG disagreements:", "", "| policy | side | class | compensation_exposed | episodes |",
              "|---|---|---|---|---|"]
    lines += [f"| {d['policy']} | {d['side']} | {d['class']} | {d['exposed']} | {d['episodes']} |"
              for d in out["basis_disagreement_classes"][:30]]
    lines += ["", f"## Write-skew protocol tail (n = 2, 8 instances x {out['tail_schedules']} schedules, contended)", "",
              "| family | policy | config | outcomes | above 80 % of cap | cap endings | p95 | p99 | max / cap |",
              "|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {t['family']} | {t['policy']} | {t['config']} | {_oc(t['outcomes'])} | {t['above_margin']}/{t['episodes']} | "
              f"{t['cap_endings']} | {t['p95']} | {t['p99']} | {t['max']} / {t['cap']} |" for t in out["tail"]]
    lines += ["", "## Interleavings (naive policy, contended, n = 2, config none)", ""]
    for label, d in out["interleavings"].items():
        lines.append(f"- **{label}**: {d['episodes']} episodes; first mover {d['first_mover']}; every first read before every other agent's "
                     f"first write in {d['reads_overlap_share']:.0%}; {d['distinct_patterns']} distinct patterns; top "
                     f"{d['top_patterns'][:5]}; failure rate naive {d['fail_rate_none']['naive']}, "
                     f"rereader {d['fail_rate_none']['rereader']}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
