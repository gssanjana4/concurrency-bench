"""Deterministic task instances for the full (confirmatory) runs.

Each of the eight registered templates (:data:`TEMPLATES`) yields ``K``
parameterized instances (default :data:`DEFAULT_K` = 4). An instance changes
record names (item, seat, ticket, account, budget team), holder names,
quantities, amounts and cap values, and the wording of the agent instruction
(``Intent.wording``: instance ``i`` uses paraphrase ``i % 2``, so K = 4 gives
two instances per paraphrase). It keeps the template's intent types,
invariants and category: the numeric draws are constrained so that the
property defining the template holds at every agent count (e.g. in
``inventory_last_unit`` exactly one sale fits; in ``budget_write_skew`` any
one spend fits and no two do).

Reproducibility: instance ``(template, i)`` is drawn from
``random.Random(f"{FULL_SPACE}|{template}|{i}")`` (string seeding is SHA-512
based, independent of ``PYTHONHASHSEED``). Parameters do not depend on the
agent count, so instance ``i`` at n = 4 or 8 is the n = 2 instance with more
agents (records and amounts scale with n exactly as in the template).

Disjointness from the pilot: the pilot used the canonical catalog task of
each template (:mod:`tasks4`, original wording, instance id ``pilot``). Full
instances come from a different seed space and a name pool that excludes
every pilot record name, and :func:`build` additionally redraws any instance
whose fingerprint equals the pilot's or an earlier instance's (tested).

    python3 instances4.py --write instances_full.json   # instance file for FREEZE.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from decimal import Decimal
from typing import Any, Callable, Dict, List, Tuple

import tasks4 as T
from records import to_json_value

FULL_SPACE = "src4-full-v1"
PILOT_INSTANCE = "pilot"
DEFAULT_K = 4
WORDINGS = 2
MAX_REDRAWS = 50

TEMPLATES: Tuple[str, ...] = (
    "inventory_last_unit",
    "inventory_still_valid",
    "seat_same",
    "ticket_same",
    "transfer_shared_source",
    "budget_write_skew",
    "joint_account_write_skew",
    "budget_control",
)

# Name pools: none contains a pilot name (widget, concert-1/12A, T-100, pool, dest-, team, joint-).
ITEMS = ("lamp", "kettle", "drill", "backpack", "monitor", "blender", "tent", "helmet", "scarf", "router", "easel", "toaster")
VENUES = ("opera-house", "arena-7", "jazz-club", "city-hall", "stadium-north", "theatre-royal")
CUSTOMERS = ("alice-ng", "bruno-silva", "chen-wei", "dara-okafor", "elena-ruiz", "farid-khan", "greta-holm", "hiro-sato",
             "ines-costa", "jonas-berg", "kemi-adeyemi", "liam-walsh", "maya-patel", "nikos-pappas", "olga-ivanova", "pedro-lima")
TICKET_PREFIXES = ("INC", "SUP", "REQ", "BUG")
SOURCES = ("ops-reserve", "payroll-float", "vendor-float", "savings-main", "club-fund", "escrow-main")
DEST_PREFIXES = ("payout", "wallet", "branch", "sub")
TEAMS = ("marketing", "research", "design", "support", "facilities", "sales")
FAMILIES = ("household", "partners", "family-trust", "shared")


def _money(x: int) -> str:
    return f"{x}.00"


def _inventory_last_unit(rng: random.Random, n: int, w: int, name: str) -> T.Task:
    ids, rec = T.agent_ids(n), f"inventory:{rng.choice(ITEMS)}"
    amount = rng.randint(1, 4)
    stock = rng.randint(amount, 2 * amount - 1)  # exactly one sale fits
    return T.Task(name, "inventory", "conflict", {rec: stock}, {a: T.Decrement(rec, amount, wording=w) for a in ids},
                  (T.non_negative(rec), T.no_oversubscription(rec)), "only one sale fits the stock")


def _inventory_still_valid(rng: random.Random, n: int, w: int, name: str) -> T.Task:
    ids, rec = T.agent_ids(n), f"inventory:{rng.choice(ITEMS)}"
    amount = rng.randint(1, 3)
    slack = rng.randint(1, 4)
    return T.Task(name, "inventory", "still_valid", {rec: n * amount + slack}, {a: T.Decrement(rec, amount, wording=w) for a in ids},
                  (T.non_negative(rec), T.no_oversubscription(rec)), "shared stock with room for every sale")


def _seat_same(rng: random.Random, n: int, w: int, name: str) -> T.Task:
    ids = T.agent_ids(n)
    rec = f"seat:{rng.choice(VENUES)}/{rng.randint(1, 40)}{rng.choice('ABCDEFGH')}"
    holders = rng.sample(CUSTOMERS, 8)  # fixed draw size: holders of a0..a{n-1} do not depend on n
    return T.Task(name, "seat", "conflict", {rec: None}, {a: T.Claim(rec, holders[i], wording=w) for i, a in enumerate(ids)},
                  (T.no_holder_overwrite(rec),), "same seat for different customers")


def _ticket_same(rng: random.Random, n: int, w: int, name: str) -> T.Task:
    ids = T.agent_ids(n)
    rec = f"ticket:{rng.choice(TICKET_PREFIXES)}-{rng.randint(1000, 9999)}"
    return T.Task(name, "ticket", "conflict", {rec: None}, {a: T.Claim(rec, a, wording=w) for a in ids},
                  (T.no_holder_overwrite(rec),), "same ticket claimed")


def _transfer_shared_source(rng: random.Random, n: int, w: int, name: str) -> T.Task:
    ids, src = T.agent_ids(n), f"account:{rng.choice(SOURCES)}"
    prefix = rng.choice(DEST_PREFIXES)
    amount = rng.randrange(40, 160, 5)
    balance = amount + rng.randrange(0, amount, 5)  # one transfer fits, two do not
    dest_start = rng.randrange(0, 100, 5)
    dsts = {a: f"account:{prefix}-{a}" for a in ids}
    records = (src,) + tuple(dsts.values())
    return T.Task(name, "account", "conflict", {src: _money(balance), **{d: _money(dest_start) for d in dsts.values()}},
                  {a: T.Transfer(src, dsts[a], _money(amount), wording=w) for a in ids},
                  (T.non_negative(src), T.conserved(records)), "transfers from one source whose sum exceeds its balance")


def _budget(rng: random.Random, n: int, w: int, name: str, control: bool) -> T.Task:
    ids, team = T.agent_ids(n), rng.choice(TEAMS)
    cap = f"budget:{team}/cap"
    spends = {a: f"budget:{team}/spend-{a}" for a in ids}
    amount = rng.randrange(30, 150, 5)
    if control:
        cap_value = n * (amount + rng.randrange(0, 100, 5))  # every spend fits
        category, desc = "control", "shared budget large enough for every spend"
    else:
        cap_value = amount + rng.randrange(0, amount, 5)  # any one spend fits, no two do
        category, desc = "write_skew", "agents each spend from a shared budget"
    return T.Task(name, "budget", category, {cap: _money(cap_value), **{s: "0.00" for s in spends.values()}},
                  {a: T.GuardedSpend(spends[a], tuple(s for b, s in spends.items() if b != a), cap, _money(amount), wording=w) for a in ids},
                  (T.sum_within_cap(tuple(spends.values()), cap), T.unchanged(cap)), desc)


def _joint_account_write_skew(rng: random.Random, n: int, w: int, name: str) -> T.Task:
    ids, family = T.agent_ids(n), rng.choice(FAMILIES)
    accts = {a: f"account:{family}-{a}" for a in ids}
    all_accts = tuple(accts.values())
    balance = rng.randrange(30, 120, 5)
    amount = rng.randrange(balance + 5, 2 * balance + 1, 5)  # at n = 2: one withdrawal fits, two do not
    return T.Task(name, "account", "write_skew", {r: _money(balance) for r in all_accts},
                  {a: T.JointWithdraw(accts[a], tuple(r for r in all_accts if r != accts[a]), _money(amount), wording=w) for a in ids},
                  (T.sum_at_least(all_accts, 0),), "withdrawals from different accounts sharing an overdraft limit")


GENERATORS: Dict[str, Callable[[random.Random, int, int, str], T.Task]] = {
    "inventory_last_unit": _inventory_last_unit,
    "inventory_still_valid": _inventory_still_valid,
    "seat_same": _seat_same,
    "ticket_same": _ticket_same,
    "transfer_shared_source": _transfer_shared_source,
    "budget_write_skew": lambda rng, n, w, name: _budget(rng, n, w, name, control=False),
    "joint_account_write_skew": _joint_account_write_skew,
    "budget_control": lambda rng, n, w, name: _budget(rng, n, w, name, control=True),
}


def _intent_params(intent: T.Intent) -> Dict[str, Any]:
    d = {k: to_json_value(v) for k, v in vars(intent).items() if k != "wording"}
    return {"type": type(intent).__name__, **d}


def fingerprint(task: T.Task) -> str:
    """SHA-256 of a task's semantics: initial values and intent parameters (wording and name excluded)."""
    blob = json.dumps({"initial": to_json_value(dict(task.initial)),
                       "intents": {a: _intent_params(i) for a, i in task.intents.items()}}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def pilot_task(template: str, n: int) -> T.Task:
    """The canonical catalog task the pilot ran (instance ``pilot``)."""
    return T.CATALOG[template](n)


def _draw(template: str, index: int, attempt: int, n: int) -> T.Task:
    key = f"{FULL_SPACE}|{template}|{index}" + (f"|redraw{attempt}" if attempt else "")
    return GENERATORS[template](random.Random(key), n, index % WORDINGS, f"{template}@i{index}/n{n}")


def build(template: str, index: int, n: int = 2) -> T.Task:
    """Full-run instance ``index`` (0-based) of ``template`` for ``n`` agents.

    Deterministic. Redraws (with a suffixed key) only if the draw coincides,
    at n = 2, with the pilot task or with an earlier instance of the
    template; the accepted attempt number is a pure function of
    ``(template, index)``, so the n = 4/8 instance matches the n = 2 one.
    """
    if template not in GENERATORS:
        raise ValueError(f"unknown template {template!r}; known: {list(GENERATORS)}")
    if index < 0:
        raise ValueError("instance index must be >= 0")
    attempt = _accepted_attempt(template, index)
    return _draw(template, index, attempt, n)


_ATTEMPTS: Dict[Tuple[str, int], int] = {}


def _accepted_attempt(template: str, index: int) -> int:
    if (template, index) in _ATTEMPTS:
        return _ATTEMPTS[(template, index)]
    taken = {fingerprint(pilot_task(template, 2))} | {fingerprint(build(template, j, 2)) for j in range(index)}
    for attempt in range(MAX_REDRAWS):
        if fingerprint(_draw(template, index, attempt, 2)) not in taken:
            _ATTEMPTS[(template, index)] = attempt
            return attempt
    raise RuntimeError(f"could not draw a fresh instance {index} of {template}")


def instances(template: str, k: int = DEFAULT_K, n: int = 2) -> List[T.Task]:
    """Instances ``0 .. k-1`` of ``template``."""
    return [build(template, i, n) for i in range(k)]


def describe_instance(task: T.Task) -> Dict[str, Any]:
    """JSON summary of an instance (for the instance file and transcripts)."""
    first = next(iter(task.intents.values()))
    return {"name": task.name, "category": task.category, "kind": task.kind, "wording": getattr(first, "wording", 0),
            "initial": to_json_value(dict(task.initial)), "intents": {a: i.describe() for a, i in task.intents.items()},
            "fingerprint": fingerprint(task)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--k", type=int, default=DEFAULT_K)
    p.add_argument("--agents", default="2,4,8")
    p.add_argument("--write", required=True, help="output JSON path")
    a = p.parse_args()
    out = {"space": FULL_SPACE, "k": a.k, "instances": {}}
    for n in [int(x) for x in a.agents.split(",")]:
        for t in TEMPLATES:
            for task in instances(t, a.k, n):
                out["instances"][task.name] = describe_instance(task)
    with open(a.write, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"wrote {len(out['instances'])} instances to {a.write}")


if __name__ == "__main__":
    main()
