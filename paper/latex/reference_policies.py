#!/usr/bin/env python3
"""POST HOC reference floor/ceiling: the frozen scripted agents under the registered schedule (no model calls).

    python3 reference_policies.py --analysis DIR

Not pre-registered and not confirmatory. Runs the scripted reference agents of the frozen ``src4/agents4.py``
(``REFERENCE_POLICIES``) through the frozen scheduler, world and scorer, on the registered phase-one task set:
the contended templates (``analyze4.CONTENDED_TEMPLATES``) x instances ``analyze4.N2_INSTANCES`` x seeds
``analyze4.N2_SEEDS``, n = 2, aware sentence off, with the registered schedule read from the frozen ``run4.py``
defaults (read-to-write gap, start jitter, stall rounds, max rounds) and the frozen turn cap
(``model_agent4.DEFAULT_TURN_CAP``). Each policy runs under every config whose tools it needs. Every agent in
an episode runs the same policy.

Purpose (review R1 W2): show which registered outcomes an agent policy can move under this schedule and scorer.
If no scripted policy that runs under ``none`` is ever serializable there, H1 is a manipulation check of the
schedule and scorer, not a finding about models. Under ``cas_available`` the naive writer still overwrites
stale data, so H4a can fail in principle.

Added after the 2026-11-03 reviews (POST HOC): ``seed_invariance`` (does each policy give the same verdict and label
under both registered seeds on every instance?) and ``promoter`` (a promotion policy written here, NOT frozen code, in two
orders, on the write-skew templates under cas_available at n = 2 and n = 8).

Writes only DIR/reference_policies.json. Imports frozen code read-only; FREEZE verified first.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict

from pipeline_common import SRC4, require_freeze

sys.dont_write_bytecode = True
sys.path.insert(0, SRC4)
import agents4  # noqa: E402  (frozen)
import analyze4 as A  # noqa: E402
import instances4  # noqa: E402
from scheduler import ScheduleConfig, run_episode  # noqa: E402
from score4 import score_episode  # noqa: E402
from world4 import PRESET_NAMES, world_config  # noqa: E402

OUT_NAME = "reference_policies.json"
PROTECTED = {"confirmatory.json", "confirmatory.md", "numbers.json", "tables.md", "provenance.json"}
LABEL = "POST HOC reference policies (scripted agents from frozen src4/agents4.py; no model calls; not confirmatory)"
CATEGORY = {t: ("single_record" if t in A.SINGLE_RECORD_TEMPLATES else "write_skew" if t in A.WRITE_SKEW_TEMPLATES
                else "transfer") for t in A.CONTENDED_TEMPLATES}


def registered_schedule():
    """Schedule defaults of the frozen run4.py and the frozen turn cap (as the model runs used them)."""
    txt = open(os.path.join(SRC4, "run4.py")).read()
    get = lambda flag: int(re.search(rf'"--{flag}", type=int, default=(\d+)', txt).group(1))  # noqa: E731
    tc = int(re.search(r"^DEFAULT_TURN_CAP = (\d+)", open(os.path.join(SRC4, "model_agent4.py")).read(), re.M).group(1))
    return {"read_write_gap": get("gap"), "start_jitter": get("jitter"), "stall_rounds": get("stall-rounds"),
            "max_rounds": get("max-rounds"), "turn_cap": tc}


def run(n_agents=2):
    sched_kw = registered_schedule()
    cells = defaultdict(lambda: defaultdict(int))
    verdicts = {}
    for pname, spec in agents4.REFERENCE_POLICIES.items():
        for cfg in PRESET_NAMES:
            wc = world_config(cfg)
            if not spec.supported_by(wc.coordination):
                continue
            for t in A.CONTENDED_TEMPLATES:
                for i in A.N2_INSTANCES:
                    task = instances4.build(t, i, n_agents)
                    for s in A.N2_SEEDS:
                        ep = run_episode(task, spec, wc, ScheduleConfig(seed=s, **sched_kw))
                        sc = score_episode(ep)
                        verdicts[(pname, cfg, t, i, s)] = (bool(sc.non_serializable), sc.primary_label)
                        for scope in ("all", CATEGORY[t]):
                            c = cells[(pname, cfg, scope)]
                            c["episodes"] += 1
                            c["non_serializable"] += int(sc.non_serializable)
                            c[sc.primary_label or "serializable"] += 1
                            c["invariant_violation"] += int(bool(sc.invariant_violation))
                            c["agents"] += len(sc.agents)
                            c["fulfilled"] += sum(bool(a.fulfilled) for a in sc.agents.values())
    rows = []
    for (p, c, scope), v in cells.items():
        rows.append(OrderedDict([("policy", p), ("config", c), ("scope", scope)] +
                                [(k, v.get(k, 0)) for k in ("episodes", "non_serializable", "stale_overwrite", "partial_action",
                                                            "write_skew", "serializable", "invariant_violation", "agents",
                                                            "fulfilled")]))
    rows.sort(key=lambda r: (list(agents4.REFERENCE_POLICIES).index(r["policy"]), PRESET_NAMES.index(r["config"]), r["scope"]))
    seeds = list(A.N2_SEEDS)
    inv = []
    for pname, cfg in sorted({(k[0], k[1]) for k in verdicts}, key=lambda x: (list(agents4.REFERENCE_POLICIES).index(x[0]), x[1])):
        same = n = 0
        for t in A.CONTENDED_TEMPLATES:
            for i in A.N2_INSTANCES:
                v = [verdicts.get((pname, cfg, t, i, s)) for s in seeds]
                if None in v:
                    continue
                n += 1
                same += len(set(v)) == 1
        inv.append({"policy": pname, "config": cfg, "same": same, "instances": n})
    return {"label": LABEL, "schedule": sched_kw, "n_agents": n_agents, "templates": list(A.CONTENDED_TEMPLATES),
            "instances": list(A.N2_INSTANCES), "seeds": seeds, "policies": list(agents4.REFERENCE_POLICIES),
            "rows": rows, "seed_invariance": inv, "promoter": promoter(sched_kw)}


# ------------------------------------------------------------------ POST HOC scripted promoter (reviews T1 section 7, T4 M1)
def _promoter(order):
    """Promotion under per-record conditional writes, written here (NOT in the frozen agents4.py): read every record of
    the intent, then write back each record it reads but does not change under its read version (a no-op conditional
    write) and its own record. ``promote_first`` sends the write-backs before the own write and restarts from the
    reads after any rejection (at most 10 attempts); ``own_first`` sends the own write first and stops after any
    rejection (no compensation)."""
    from agents4 import _read, _update

    def pol(ctx):
        it = ctx.intent
        for _ in range(10):
            got = yield from _read(it.reads)
            if got is None:
                return "read failed"
            vals, vers = got
            new = it.apply(vals)
            if new is None:
                return "declined"
            own = it.writes[0]
            seq = [(r, vals[r]) for r in it.reads if r not in it.writes] + [(own, new[own])]
            if order == "own_first":
                seq = seq[-1:] + seq[:-1]
            ok = True
            for rid, v in seq:
                resp = yield _update(rid, v, vers[rid])
                if not resp.get("ok"):
                    ok = False
                    break
            if ok:
                return "done"
            if order == "own_first":
                return "stopped"
        return "gave up"
    from scheduler import AgentSpec
    return AgentSpec("promoter_" + order, pol, frozenset({"versions", "conditional_writes"}))


def promoter(sched_kw):
    """The two promoter variants on the write-skew templates under cas_available, aware off: n=2 on the registered
    phase-one instances and seeds, and n=8 on the phase-three instances (seed 0)."""
    out = []
    wc = world_config("cas_available")
    for order in ("promote_first", "own_first"):
        spec = _promoter(order)
        for n, insts, seeds in ((2, A.N2_INSTANCES, A.N2_SEEDS), (8, A.SCALE_INSTANCES, A.SCALE_SEEDS)):
            for t in A.WRITE_SKEW_TEMPLATES:
                c = defaultdict(int)
                for i in insts:
                    task = instances4.build(t, i, n)
                    for s in seeds:
                        sc = score_episode(run_episode(task, spec, wc, ScheduleConfig(seed=s, **sched_kw)))
                        c["episodes"] += 1
                        c["non_serializable"] += int(sc.non_serializable)
                        c["write_skew"] += int(sc.primary_label == "write_skew")
                        c["agents"] += len(sc.agents)
                        c["fulfilled"] += sum(bool(a.fulfilled) for a in sc.agents.values())
                        c["turn_cap"] += sum(a.end_reason == "turn_cap" for a in sc.agents.values())
                out.append(OrderedDict([("order", order), ("n", n), ("template", t)] + sorted(c.items())))
    return {"label": "POST HOC scripted promoter (defined in latex/reference_policies.py after the 2026-11-03 reviews; "
                     "not frozen code; no model calls)", "rows": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis", required=True)
    a = ap.parse_args(argv)
    require_freeze()
    data = run()
    dst = os.path.join(a.analysis, OUT_NAME)
    assert os.path.basename(dst) not in PROTECTED
    with open(dst, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    allr = [r for r in data["rows"] if r["scope"] == "all"]
    print(f"reference policies (POST HOC): {len(allr)} policy x config cells, "
          f"{sum(r['episodes'] for r in allr)} scripted episodes; wrote {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
