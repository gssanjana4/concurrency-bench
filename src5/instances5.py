"""Deterministic Study 2 task instances: 7 contended templates and their 7 matched controls.

Each template ``T`` has a matched control ``T_ctrl`` (:func:`tasks5.control_of`): every agent gets a private
copy of ``T``'s record group, with the same amounts, the same number of records and the same wording. In the
contended task every agent works in group ``g0``; in the control agent ``i`` works in group ``g_i``. Agent
``a0``'s task text is therefore *identical* in ``T`` and ``T_ctrl``; the other agents' texts differ only in
the group tag inside record names. No agent can tell from its task text whether its records are shared.

Neutral names (*peer cues*, review T2 F2): record names never contain agent ids. Peer-owned records that a
guard reads (``spend-field``, ``household-west-cedar``) are named from neutral word pools, in the contended
task and in the control alike, so the guard text has the same shape in both.

Reproducibility: instance ``(template, i)`` draws from ``random.Random(f"{SPACE}|{family}|{i}")`` (SHA-512
string seeding, independent of PYTHONHASHSEED); the control uses its family's draw, so ``T@i`` and
``T_ctrl@i`` have identical numbers. Parameters do not depend on n.

Disjoint from Study 1: a new seed space and name format (Study 1 names such as ``inventory:lamp`` or
``budget:research/spend-a0`` cannot occur). In addition the *numeric shape* (template, sorted initial values,
intent amounts) of every Study 2 instance of a numeric template differs from every Study 1 instance and from the Study 1 pilot;
:func:`build` redraws on a clash (tested against ``src4/instances_full.json``, read as data).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import tasks5 as T
from records5 import to_json_value

SPACE = "src5-study2-v1"
MAX_REDRAWS = 50
WORDINGS = 2

CONTENDED: Tuple[str, ...] = (
    "inventory_last_unit",
    "inventory_still_valid",
    "seat_same",
    "ticket_same",
    "transfer_shared_source",
    "budget_write_skew",
    "joint_account_write_skew",
)
CONTROL_SUFFIX = "_ctrl"
CONTROLS: Tuple[str, ...] = tuple(t + CONTROL_SUFFIX for t in CONTENDED)
TEMPLATES: Tuple[str, ...] = CONTENDED + CONTROLS

ITEMS = ("anvil", "lantern", "compass", "satchel", "thermos", "trowel", "abacus", "kayak", "ladle", "quiver", "sextant", "whisk")
VENUES = ("odeon", "civic-arena", "bluenote", "corn-exchange", "lyric-hall", "riverside")
CUSTOMERS = ("asha-rao", "ben-okoye", "carla-mendes", "dmitri-volkov", "eun-ji-park", "felix-braun", "gaia-russo",
             "hamid-noori", "ingrid-dahl", "joao-pinto", "keiko-mori", "lars-eide", "mina-haddad", "noah-levi",
             "oona-kerr", "priya-nair")
TICKET_PREFIXES = ("OPS", "HLP", "TKT", "ESC")
SOURCES = ("reserve", "treasury", "float", "common-fund", "holding", "sinking-fund")
DEST_PREFIXES = ("payee", "vendor", "account", "branch")
TEAMS = ("ops", "growth", "platform", "legal", "finance", "people")
FAMILIES = ("joint", "estate", "trust", "common")
GROUP_TAGS = ("north", "south", "east", "west", "central", "harbor", "valley", "ridge", "summit", "meadow")
WORDS = ("amber", "birch", "cedar", "delta", "ember", "fjord", "garnet", "heron", "indigo", "juniper")
SPEND_WORDS = ("lab", "field", "travel", "tools", "events", "print", "cloud", "hiring", "ads", "training")


def _money(x: int) -> str:
    return f"{x}.00"


class Params:
    """One instance's draws (independent of n and of the group)."""

    def __init__(self, family: str, rng: random.Random) -> None:
        self.family = family
        self.tags = rng.sample(GROUP_TAGS, 8)
        self.words = rng.sample(WORDS, 8)
        self.spend_words = rng.sample(SPEND_WORDS, 8)
        self.item = rng.choice(ITEMS)
        self.venue = rng.choice(VENUES)
        self.seat = f"{rng.randint(1, 40)}{rng.choice('ABCDEFGH')}"
        self.customers = rng.sample(CUSTOMERS, 8)
        self.ticket_prefix = rng.choice(TICKET_PREFIXES)
        self.ticket_nums = rng.sample(range(1000, 9999), 8)
        self.source = rng.choice(SOURCES)
        self.dest_prefix = rng.choice(DEST_PREFIXES)
        self.team = rng.choice(TEAMS)
        self.joint = rng.choice(FAMILIES)
        if family == "inventory_last_unit":
            self.amount = rng.randint(1, 6)  # wider than Study 1 (1-4) so instances can avoid every Study 1 shape
            self.stock = rng.randint(self.amount, 2 * self.amount - 1)  # exactly one sale fits
        elif family == "inventory_still_valid":
            self.amount = rng.randint(1, 3)
            self.slack = rng.randint(1, 6)
        elif family == "transfer_shared_source":
            self.amount = rng.randrange(40, 160, 5)
            self.balance = self.amount + rng.randrange(0, self.amount, 5)  # one transfer fits, two do not
            self.dest_start = rng.randrange(0, 100, 5)
        elif family == "budget_write_skew":
            self.amount = rng.randrange(30, 150, 5)
            self.cap = self.amount + rng.randrange(0, self.amount, 5)      # any one spend fits, no two do
        elif family == "joint_account_write_skew":
            self.balance = rng.randrange(30, 120, 5)
            self.amount = rng.randrange(self.balance + 5, 2 * self.balance + 1, 5)  # at n = 2 one fits, two do not


def _builder(family: str, p: Params, n: int, w: int, name: str) -> Callable[[str], T.Task]:
    """``tag -> contended task of this family for record group tag``."""
    ids = T.agent_ids(n)

    def build(tag: str) -> T.Task:
        if family in ("inventory_last_unit", "inventory_still_valid"):
            rec = f"inventory:{p.item}-{tag}"
            stock = p.stock if family == "inventory_last_unit" else n * p.amount + p.slack
            cat = "conflict" if family == "inventory_last_unit" else "still_valid"
            return T.Task(name, "inventory", cat, {rec: stock}, {a: T.Decrement(rec, p.amount, wording=w) for a in ids},
                          (T.non_negative(rec), T.no_oversubscription(rec), T.accounted((rec,))),
                          "shared stock", family=family)
        if family == "seat_same":
            rec = f"seat:{p.venue}-{tag}/{p.seat}"
            return T.Task(name, "seat", "conflict", {rec: None},
                          {a: T.Claim(rec, p.customers[i], wording=w) for i, a in enumerate(ids)},
                          (T.no_holder_overwrite(rec),), "same seat for different customers", family=family)
        if family == "ticket_same":
            num = p.ticket_nums[p.tags.index(tag)]
            rec = f"ticket:{p.ticket_prefix}-{num}"
            return T.Task(name, "ticket", "conflict", {rec: None}, {a: T.Claim(rec, a, wording=w) for a in ids},
                          (T.no_holder_overwrite(rec),), "same ticket claimed", family=family)
        if family == "transfer_shared_source":
            src = f"account:{p.source}-{tag}"
            dsts = {a: f"account:{p.dest_prefix}-{tag}-{p.words[i]}" for i, a in enumerate(ids)}
            records = (src,) + tuple(dsts.values())
            return T.Task(name, "account", "conflict", {src: _money(p.balance), **{d: _money(p.dest_start) for d in dsts.values()}},
                          {a: T.Transfer(src, dsts[a], _money(p.amount), wording=w) for a in ids},
                          (T.non_negative(src), T.conserved(records)), "transfers from one source", family=family)
        if family == "budget_write_skew":
            cap = f"budget:{p.team}-{tag}/cap"
            spends = {a: f"budget:{p.team}-{tag}/spend-{p.spend_words[i]}" for i, a in enumerate(ids)}
            return T.Task(name, "budget", "write_skew", {cap: _money(p.cap), **{s: "0.00" for s in spends.values()}},
                          {a: T.GuardedSpend(spends[a], tuple(s for b, s in spends.items() if b != a), cap, _money(p.amount), wording=w)
                           for a in ids},
                          (T.sum_within_cap(tuple(spends.values()), cap), T.unchanged(cap), T.accounted(tuple(spends.values()))),
                          "agents spend from a shared budget", family=family)
        if family == "joint_account_write_skew":
            accts = {a: f"account:{p.joint}-{tag}-{p.words[i]}" for i, a in enumerate(ids)}
            all_accts = tuple(accts.values())
            return T.Task(name, "account", "write_skew", {r: _money(p.balance) for r in all_accts},
                          {a: T.JointWithdraw(accts[a], tuple(r for r in all_accts if r != accts[a]), _money(p.amount), wording=w)
                           for a in ids},
                          (T.sum_at_least(all_accts, 0), T.accounted(all_accts)),
                          "withdrawals from accounts sharing an overdraft limit", family=family)
        raise ValueError(f"unknown family {family!r}")

    return build


def family_of(template: str) -> str:
    return template[: -len(CONTROL_SUFFIX)] if template.endswith(CONTROL_SUFFIX) else template


def _draw(template: str, index: int, attempt: int, n: int) -> T.Task:
    family = family_of(template)
    key = f"{SPACE}|{family}|{index}" + (f"|redraw{attempt}" if attempt else "")
    p = Params(family, random.Random(key))
    name = f"{template}@i{index}/n{n}"
    build = _builder(family, p, n, index % WORDINGS, name)
    if template.endswith(CONTROL_SUFFIX):
        return T.control_of(build, p.tags[:n] if n <= 8 else [f"{t}{k}" for k in range(n // 8 + 1) for t in p.tags][:n], name)
    return build(p.tags[0])


def shape(task: T.Task, template: str) -> str:
    """Numeric shape of an instance (template family, sorted initial values, amounts); names ignored."""
    vals = sorted(str(to_json_value(v)) for v in task.initial.values())
    amts = sorted(str(to_json_value(getattr(i, "amount", ""))) for i in task.intents.values())
    return json.dumps([family_of(template), vals, amts])


_STUDY1_SHAPES: Optional[Set[str]] = None
STUDY1_INSTANCES = os.environ.get("STUDY1_INSTANCES") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src4",
                                                                        "instances_full.json")
STUDY1_PILOT_SHAPES = {  # src4 tasks4 catalog at n = 2 (the pilot), family, sorted initial values, amounts
    json.dumps(["inventory_last_unit", ["1"], ["1", "1"]]),
    json.dumps(["inventory_still_valid", ["5"], ["1", "1"]]),
    json.dumps(["seat_same", ["None"], ["", ""]]),
    json.dumps(["ticket_same", ["None"], ["", ""]]),
    json.dumps(["transfer_shared_source", ["0.00", "0.00", "100.00"], ["60.00", "60.00"]]),
    json.dumps(["budget_write_skew", ["0.00", "0.00", "100.00"], ["60.00", "60.00"]]),
    json.dumps(["joint_account_write_skew", ["50.00", "50.00"], ["60.00", "60.00"]]),
}


def study1_shapes() -> Set[str]:
    """Numeric shapes of Study 1's full-run instances at n = 2 (from src4/instances_full.json, read as data)."""
    global _STUDY1_SHAPES
    if _STUDY1_SHAPES is None:
        out = set(STUDY1_PILOT_SHAPES)
        if os.path.exists(STUDY1_INSTANCES):
            with open(STUDY1_INSTANCES) as f:
                data = json.load(f)["instances"]
            for name, d in data.items():
                if not name.endswith("/n2"):
                    continue
                fam = name.split("@")[0]
                vals = sorted(str(v) for v in d["initial"].values())
                import re  # noqa: PLC0415
                amts = []
                for text in d["intents"].values():
                    m = re.search(r"(?:Sell|Withdraw|Reduce \S+ by|Take|Move|Transfer|Record a spend of|Add) (\d+(?:\.\d+)?)", text)
                    amts.append(m.group(1) if m else "")
                out.add(json.dumps([fam, vals, sorted(amts)]))
        _STUDY1_SHAPES = out
    return _STUDY1_SHAPES


_ATTEMPTS: Dict[Tuple[str, int], int] = {}
NAME_ONLY_FAMILIES = ("seat_same", "ticket_same")


def _accepted_attempt(template: str, index: int) -> int:
    family = family_of(template)
    if (family, index) in _ATTEMPTS:
        return _ATTEMPTS[(family, index)]
    if family in NAME_ONLY_FAMILIES:  # claim templates have no numbers: disjoint by names only (and by name pools)
        _ATTEMPTS[(family, index)] = 0
        return 0
    taken = set(study1_shapes()) | {shape(build(family, j, 2), family) for j in range(index)}
    for attempt in range(MAX_REDRAWS):
        if shape(_draw(family, index, attempt, 2), family) not in taken:
            _ATTEMPTS[(family, index)] = attempt
            return attempt
    raise RuntimeError(f"could not draw a fresh instance {index} of {family}")


def build(template: str, index: int, n: int = 2) -> T.Task:
    """Instance ``index`` of ``template`` (contended or ``*_ctrl``) for ``n`` agents."""
    if family_of(template) not in CONTENDED or template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r}; known: {list(TEMPLATES)}")
    if index < 0:
        raise ValueError("instance index must be >= 0")
    return _draw(template, index, _accepted_attempt(template, index), n)


def fingerprint(task: T.Task) -> str:
    def params(i: T.Intent) -> Dict[str, Any]:
        return {"type": type(i).__name__, **{k: to_json_value(v) for k, v in vars(i).items() if k != "wording"}}
    blob = json.dumps({"initial": to_json_value(dict(task.initial)), "intents": {a: params(i) for a, i in task.intents.items()}},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def describe_instance(task: T.Task) -> Dict[str, Any]:
    first = next(iter(task.intents.values()))
    return {"name": task.name, "category": task.category, "family": task.family, "kind": task.kind,
            "wording": getattr(first, "wording", 0), "initial": to_json_value(dict(task.initial)),
            "intents": {a: i.describe() for a, i in task.intents.items()}, "fingerprint": fingerprint(task)}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--agents", default="2,4")
    ap.add_argument("--write", required=True)
    a = ap.parse_args()
    out: Dict[str, Any] = {"space": SPACE, "k": a.k, "instances": {}}
    for n in [int(x) for x in a.agents.split(",")]:
        for t in TEMPLATES:
            for i in range(a.k):
                task = build(t, i, n)
                out["instances"][task.name] = describe_instance(task)
    with open(a.write, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"wrote {len(out['instances'])} instances to {a.write}")
