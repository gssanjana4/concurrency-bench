"""Deterministic Study 3 task instances: 8 contended templates and their 8 matched controls (src6).

Derived from src5/instances5.py (Study 2). Study 3 changes (registration PREREGISTRATION_STUDY3.md, "Templates"):

* **Distinct amounts.** In every numeric family except ``transfer_same_amount`` the two agents get different
  amounts (``big`` and ``small``, at least one unit apart), each of which fits the shared quantity alone while both
  together do not. Study 2 gave both agents the same amount, so after the peer's write the record held exactly the
  value the agent's own write would have produced (the "end-state matching" behind its half-done transfers and
  false success reports). With distinct amounts the post-peer value never equals the agent's own target.
  Which agent gets ``big`` alternates over instances (``big_first``): a0 in instances 0, 3, 4, 7; a1 in 1, 2, 5, 6.
* **``transfer_same_amount``** (8th family): the Study 2 transfer rule (both agents move the same amount), on new
  draws, kept for the amount contrast (pre-specified descriptive S3-D1).
* New seed space ``src6-study3-v1``; every numeric shape (family, sorted initial values, sorted amounts) differs
  from every Study 1 and Study 2 instance (``prior_shapes.json``, built from the frozen src4 and src5 files by
  ``tools/make_prior_shapes.py``) and from the earlier instances of the same family.
* Study 3 runs n = 2 (the distinct-amount rule "each fits alone, both do not" is stated for two agents); for larger
  n, used only by harness tests, the two amounts alternate over agents.

Unchanged from Study 2: each template ``T`` has a matched control ``T_ctrl`` (:func:`tasks6.control_of`): every
agent gets a private copy of ``T``'s record group, with the same amounts and wording, so a0's task text is
identical in ``T`` and ``T_ctrl`` and a1's differs only in the group tag. Record names never contain agent ids;
peer-owned guard records are named from neutral pools in both arms. Instance ``(template, i)`` draws from
``random.Random(f"{SPACE}|{family}|{i}")`` (redraw suffix on a clash); the control uses its family's draw.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import tasks6 as T
from records6 import to_json_value

SPACE = "src6-study2-v1"
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
    "transfer_same_amount",
)
DISTINCT_FAMILIES: Tuple[str, ...] = ("inventory_last_unit", "inventory_still_valid", "transfer_shared_source",
                                      "budget_write_skew", "joint_account_write_skew")
SAME_AMOUNT_FAMILIES: Tuple[str, ...] = ("transfer_same_amount",)
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
            self.big = rng.randint(2, 8)
            self.small = rng.randint(1, self.big - 1)
            self.stock = rng.randint(self.big, self.big + self.small - 1)  # each sale fits alone, both do not
        elif family == "inventory_still_valid":
            self.big = rng.randint(2, 4)
            self.small = rng.randint(1, self.big - 1)
            self.slack = rng.randint(1, 6)  # both sales fit
        elif family == "transfer_shared_source":
            self.big = rng.randrange(45, 160, 5)
            self.small = rng.randrange(40, self.big, 5)
            self.balance = self.big + rng.randrange(0, self.small, 5)  # each transfer fits alone, both do not
            self.dest_start = rng.randrange(0, 100, 5)
        elif family == "transfer_same_amount":  # Study 2 rule: both agents move the same amount
            self.amount = rng.randrange(40, 160, 5)
            self.big = self.small = self.amount
            self.balance = self.amount + rng.randrange(0, self.amount, 5)  # one transfer fits, two do not
            self.dest_start = rng.randrange(0, 100, 5)
        elif family == "budget_write_skew":
            self.big = rng.randrange(35, 150, 5)
            self.small = rng.randrange(30, self.big, 5)
            self.cap = self.big + rng.randrange(0, self.small, 5)  # any one spend fits, both do not
        elif family == "joint_account_write_skew":
            self.balance = rng.randrange(30, 120, 5)
            self.small = rng.randrange(self.balance + 5, 2 * self.balance, 5)
            self.big = rng.randrange(self.small + 5, 2 * self.balance + 1, 5)  # each fits alone, both do not


def big_first(index: int) -> bool:
    """Whether a0 gets the larger amount in instance ``index`` (4 of the 8 instances, 2 per wording)."""
    return (index // 2 + index) % 2 == 0


def amounts(p: Params, index: int, ids: Tuple[str, ...]) -> Dict[str, Any]:
    """Per-agent amount of a numeric family: (a0, a1) = (big, small) or (small, big). Study 3 runs n = 2 only; for
    larger n (harness tests) the two amounts alternate, so any two agents still exceed the shared quantity."""
    order = (p.big, p.small) if big_first(index) else (p.small, p.big)
    return {a: order[k % 2] for k, a in enumerate(ids)}


def _builder(family: str, p: Params, n: int, w: int, name: str, index: int = 0) -> Callable[[str], T.Task]:
    """``tag -> contended task of this family for record group tag``."""
    ids = T.agent_ids(n)
    amt = amounts(p, index, ids) if hasattr(p, "big") else {}

    def build(tag: str) -> T.Task:
        if family in ("inventory_last_unit", "inventory_still_valid"):
            rec = f"inventory:{p.item}-{tag}"
            stock = p.stock if family == "inventory_last_unit" else sum(amt.values()) + p.slack
            cat = "conflict" if family == "inventory_last_unit" else "still_valid"
            return T.Task(name, "inventory", cat, {rec: stock}, {a: T.Decrement(rec, amt[a], wording=w) for a in ids},
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
        if family in ("transfer_shared_source", "transfer_same_amount"):
            src = f"account:{p.source}-{tag}"
            dsts = {a: f"account:{p.dest_prefix}-{tag}-{p.words[i]}" for i, a in enumerate(ids)}
            records = (src,) + tuple(dsts.values())
            return T.Task(name, "account", "conflict", {src: _money(p.balance), **{d: _money(p.dest_start) for d in dsts.values()}},
                          {a: T.Transfer(src, dsts[a], _money(amt[a]), wording=w) for a in ids},
                          (T.non_negative(src), T.conserved(records)), "transfers from one source", family=family)
        if family == "budget_write_skew":
            cap = f"budget:{p.team}-{tag}/cap"
            spends = {a: f"budget:{p.team}-{tag}/spend-{p.spend_words[i]}" for i, a in enumerate(ids)}
            return T.Task(name, "budget", "write_skew", {cap: _money(p.cap), **{s: "0.00" for s in spends.values()}},
                          {a: T.GuardedSpend(spends[a], tuple(s for b, s in spends.items() if b != a), cap, _money(amt[a]), wording=w)
                           for a in ids},
                          (T.sum_within_cap(tuple(spends.values()), cap), T.unchanged(cap), T.accounted(tuple(spends.values()))),
                          "agents spend from a shared budget", family=family)
        if family == "joint_account_write_skew":
            accts = {a: f"account:{p.joint}-{tag}-{p.words[i]}" for i, a in enumerate(ids)}
            all_accts = tuple(accts.values())
            return T.Task(name, "account", "write_skew", {r: _money(p.balance) for r in all_accts},
                          {a: T.JointWithdraw(accts[a], tuple(r for r in all_accts if r != accts[a]), _money(amt[a]), wording=w)
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
    build = _builder(family, p, n, index % WORDINGS, name, index)
    if template.endswith(CONTROL_SUFFIX):
        return T.control_of(build, p.tags[:n] if n <= 8 else [f"{t}{k}" for k in range(n // 8 + 1) for t in p.tags][:n], name)
    return build(p.tags[0])


def shape(task: T.Task, template: str) -> str:
    """Numeric shape of an instance (template family, sorted initial values, amounts); names ignored."""
    vals = sorted(str(to_json_value(v)) for v in task.initial.values())
    amts = sorted(str(to_json_value(getattr(i, "amount", ""))) for i in task.intents.values())
    return json.dumps([family_of(template), vals, amts])


PRIOR_SHAPES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prior_shapes.json")
_PRIOR: Optional[Set[str]] = None


def prior_shapes() -> Set[str]:
    """Numeric shapes of every Study 1 and Study 2 instance at n = 2 (``prior_shapes.json``, frozen data)."""
    global _PRIOR
    if _PRIOR is None:
        with open(PRIOR_SHAPES_FILE) as f:
            d = json.load(f)
        _PRIOR = set(d["study1"]) | set(d["study2"])
    return _PRIOR


def _family_key(family: str) -> str:
    """Study 1/2 shapes of the transfer family are compared with both Study 3 transfer families."""
    return "transfer_shared_source" if family == "transfer_same_amount" else family


_ATTEMPTS: Dict[Tuple[str, int], int] = {}
NAME_ONLY_FAMILIES = ("seat_same", "ticket_same")


def _accepted_attempt(template: str, index: int) -> int:
    family = family_of(template)
    if (family, index) in _ATTEMPTS:
        return _ATTEMPTS[(family, index)]
    if family in NAME_ONLY_FAMILIES:  # claim templates have no numbers: disjoint by names only (and by name pools)
        _ATTEMPTS[(family, index)] = 0
        return 0
    fk = _family_key(family)  # the two transfer families cannot clash with each other (equal vs distinct amounts)
    rekey = lambda sh: sh.replace(f'"{family}"', f'"{fk}"', 1)  # noqa: E731
    taken = set(prior_shapes()) | {rekey(shape(build(family, j, 2), family)) for j in range(index)}
    for attempt in range(MAX_REDRAWS):
        cand = rekey(shape(_draw(family, index, attempt, 2), family))
        if cand not in taken:
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
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--agents", default="2")
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
