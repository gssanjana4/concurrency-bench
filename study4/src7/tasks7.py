"""Intents, invariants and task construction (Study 2 harness, src6).

Derived from src4/tasks4.py. Changes:

* Every intent has :meth:`Intent.effect` (the unguarded action: what the agent
  writes if it ignores its guard) and :attr:`Intent.net_delta` (its net change
  of the conserved quantity), used by the guard-violation label and the
  accounting invariant.
* V2 (review V2 F5): multi-record guard texts list their records in sorted order for every agent.
* Wording (*peer cues*, review T2 F2): the claim intents no longer say "held by
  anyone else" / "someone else"; they say "only if it has no holder yet" /
  "only if it is still unassigned". Record names are drawn by
  :mod:`instances7` from neutral pools (no agent ids in record names, unlike
  Study 1's ``spend-a1``, ``partners-a1``, ``dest-a0``).
* Invariants carry a ``kind``: ``constraint`` (a function of record values only;
  checked after *every* committed write for the ever-violated flag),
  ``conservation`` (final state only; transiently broken between the legs of
  any multi-record write) and ``history`` (checked on the ledger).
* New ``accounted`` conservation invariant (review T1 3d, CEX-2): the net
  change of the conserved records equals the sum of ``net_delta`` over the
  agents that committed (have a value-changing write) and did not roll back.
  It catches money or stock created or destroyed by out-of-intent writes,
  double applications and lost updates.
* :func:`control_of`: a *matched uncontended control* -- every agent gets its
  own private copy of the contended record group (same structure, same
  amounts, same wording; only the group tag in record names differs), so no
  two agents share any record (zero cross-agent dependency edges, tested).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from records7 import Ledger, action_effects, coerce_value, kind_of, normalize_value, to_json_value, value_at_version, write_bases

CATEGORIES = ("conflict", "still_valid", "write_skew", "control")
Values = Mapping[str, Any]


def agent_ids(n: int) -> Tuple[str, ...]:
    if n < 1:
        raise ValueError("need at least one agent")
    width = len(str(n - 1))
    return tuple(f"a{i:0{width}d}" for i in range(n))


# --------------------------------------------------------------------------
# Intents
# --------------------------------------------------------------------------


class Intent:
    reads: Tuple[str, ...]
    writes: Tuple[str, ...]
    net_delta: Any = Decimal(0)

    def apply(self, values: Values) -> Optional[Dict[str, Any]]:
        """New values for ``writes`` if the guard holds on ``values``, else ``None``."""
        return self.effect(values) if self.guard(values) else None

    def guard(self, values: Values) -> bool:
        raise NotImplementedError

    def effect(self, values: Values) -> Dict[str, Any]:
        """New values for ``writes`` ignoring the guard."""
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError

    def is_valid(self, values: Values) -> bool:
        return self.guard(values)

    @property
    def conserved_records(self) -> Tuple[str, ...]:
        """Records whose total is the quantity ``net_delta`` refers to (empty: not accounted)."""
        return ()


@dataclass(frozen=True)
class Decrement(Intent):
    record: str
    amount: Any
    wording: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", coerce_value(kind_of(self.record), self.amount))
        if self.amount <= 0:
            raise ValueError("amount must be positive")

    @property
    def reads(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.record,)

    @property
    def writes(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.record,)

    @property
    def net_delta(self) -> Any:  # type: ignore[override]
        return -self.amount

    @property
    def conserved_records(self) -> Tuple[str, ...]:
        return (self.record,)

    def guard(self, values: Values) -> bool:
        return values[self.record] >= self.amount

    def effect(self, values: Values) -> Dict[str, Any]:
        return {self.record: values[self.record] - self.amount}

    def describe(self) -> str:
        amt = to_json_value(self.amount)
        if self.wording == 1:
            if kind_of(self.record) == "inventory":
                return f"Reduce {self.record} by {amt} to record a sale, but only if at least {amt} is in stock."
            return f"Take {amt} out of {self.record}, but only if its balance covers it."
        verb = "Sell" if kind_of(self.record) == "inventory" else "Withdraw"
        return f"{verb} {amt} from {self.record}, only if enough remains."


@dataclass(frozen=True)
class Claim(Intent):
    record: str
    holder: str
    wording: int = 0

    @property
    def reads(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.record,)

    @property
    def writes(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.record,)

    def guard(self, values: Values) -> bool:
        current = values[self.record]
        return current is None or current == self.holder

    def effect(self, values: Values) -> Dict[str, Any]:
        return {self.record: self.holder}

    def describe(self) -> str:
        if self.wording == 1:
            return f"Give {self.record} to {self.holder}, but only if it is still unassigned."
        return f"Assign {self.record} to {self.holder}, only if it has no holder yet."


@dataclass(frozen=True)
class Transfer(Intent):
    src: str
    dst: str
    amount: Any
    wording: int = 0

    def __post_init__(self) -> None:
        if self.src == self.dst:
            raise ValueError("src and dst must differ")
        object.__setattr__(self, "amount", coerce_value(kind_of(self.src), self.amount))

    @property
    def reads(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.src, self.dst)

    @property
    def writes(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.src, self.dst)

    @property
    def net_delta(self) -> Any:  # type: ignore[override]
        return Decimal("0.00")

    @property
    def conserved_records(self) -> Tuple[str, ...]:
        return (self.src, self.dst)

    def guard(self, values: Values) -> bool:
        return values[self.src] >= self.amount

    def effect(self, values: Values) -> Dict[str, Any]:
        return {self.src: values[self.src] - self.amount, self.dst: values[self.dst] + self.amount}

    def describe(self) -> str:
        amt = to_json_value(self.amount)
        if self.wording == 1:
            return f"Transfer {amt} out of {self.src} into {self.dst}, but only if {self.src} has at least {amt}."
        return f"Move {amt} from {self.src} to {self.dst}, only if {self.src} has enough."


@dataclass(frozen=True)
class GuardedSpend(Intent):
    own: str
    others: Tuple[str, ...]
    cap: str
    amount: Any
    wording: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "others", tuple(self.others))
        object.__setattr__(self, "amount", coerce_value(kind_of(self.own), self.amount))

    @property
    def reads(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.cap, self.own) + self.others

    @property
    def writes(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.own,)

    @property
    def net_delta(self) -> Any:  # type: ignore[override]
        return self.amount

    @property
    def conserved_records(self) -> Tuple[str, ...]:
        return (self.own,) + self.others

    def guard(self, values: Values) -> bool:
        spent = values[self.own] + sum((values[r] for r in self.others), Decimal(0))
        return spent + self.amount <= values[self.cap]

    def effect(self, values: Values) -> Dict[str, Any]:
        return {self.own: values[self.own] + self.amount}

    def describe(self) -> str:
        # V2 (review V2 F5): guard records in one canonical (sorted) order for every agent, so agents that lock in
        # text order lock in the same order (Study 2 v1 listed own record first: opposite orders, deadlock)
        recs = ", ".join(sorted((self.own,) + self.others))
        if self.wording == 1:
            return (f"Add {to_json_value(self.amount)} to {self.own}, provided the combined spend in "
                    f"{recs} does not go over {self.cap}.")
        return (f"Record a spend of {to_json_value(self.amount)} in {self.own}, only if total spend across "
                f"{recs} stays within {self.cap}.")


@dataclass(frozen=True)
class JointWithdraw(Intent):
    target: str
    partners: Tuple[str, ...]
    amount: Any
    floor: Any = Decimal("0.00")
    wording: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "partners", tuple(self.partners))
        kind = kind_of(self.target)
        object.__setattr__(self, "amount", coerce_value(kind, self.amount))
        object.__setattr__(self, "floor", coerce_value(kind, self.floor))

    @property
    def reads(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.target,) + self.partners

    @property
    def writes(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.target,)

    @property
    def net_delta(self) -> Any:  # type: ignore[override]
        return -self.amount

    @property
    def conserved_records(self) -> Tuple[str, ...]:
        return self.reads

    def guard(self, values: Values) -> bool:
        return sum((values[r] for r in self.reads), Decimal(0)) - self.amount >= self.floor

    def effect(self, values: Values) -> Dict[str, Any]:
        return {self.target: values[self.target] - self.amount}

    def describe(self) -> str:
        recs = ", ".join(sorted(self.reads))  # V2 (V2 F5): canonical order for every agent
        if self.wording == 1:
            return (f"Take {to_json_value(self.amount)} out of {self.target}, provided {recs} "
                    f"together still hold at least {to_json_value(self.floor)} afterwards.")
        return (f"Withdraw {to_json_value(self.amount)} from {self.target}, only if the combined balance of "
                f"{recs} stays at or above {to_json_value(self.floor)}.")


# --------------------------------------------------------------------------
# Rolled-back (compensated) agents
# --------------------------------------------------------------------------


def rolled_back_agents(ledger: Ledger, initial: Values, effects_upto: Optional[int] = None) -> Set[str]:
    """Agents that committed a value-changing write and later put back, on every record they changed,
    the value their first change was based on (a saga compensation). Judged on the first ``effects_upto``
    effects (default all)."""
    acts = action_effects(ledger, initial)
    if effects_upto is not None:
        acts = [e for e in acts if e.seq <= effects_upto]
    bases = write_bases(ledger)
    first: Dict[Tuple[str, str], Any] = {}
    for e in acts:
        first.setdefault((e.agent_id, e.record_id), value_at_version(ledger, initial, e.record_id, bases[e.seq][0]))
    last: Dict[Tuple[str, str], Any] = {}
    for e in ledger.effects:
        if effects_upto is not None and e.seq > effects_upto:
            break
        if (e.agent_id, e.record_id) in first:
            last[(e.agent_id, e.record_id)] = e.new_value
    out: Set[str] = set()
    for agent in {a for a, _ in first}:
        keys = [k for k in first if k[0] == agent]
        if all(normalize_value(last[k]) == normalize_value(first[k]) for k in keys):
            out.add(agent)
    return out


# --------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Invariant:
    """``check(initial, values, ledger, task) -> [violations]``; ``kind`` in constraint / conservation / history."""

    name: str
    check: Callable[[Values, Values, Ledger, "Task"], List[str]]
    kind: str = "constraint"

    def violations(self, initial: Values, final: Values, ledger: Ledger, task: "Task") -> List[str]:
        return [f"{self.name}: {msg}" for msg in self.check(initial, final, ledger, task)]


def non_negative(record: str) -> Invariant:
    def check(initial, final, ledger, task):
        return [f"{record} = {to_json_value(final[record])} < 0"] if final[record] < 0 else []
    return Invariant(f"non_negative[{record}]", check, "constraint")


def no_holder_overwrite(record: str) -> Invariant:
    def check(initial, final, ledger, task):
        return [f"effect #{e.seq} by {e.agent_id} replaced holder {e.old_value!r} with {e.new_value!r}"
                for e in ledger.effects_for(record_id=record) if e.old_value is not None and e.new_value != e.old_value]
    return Invariant(f"no_holder_overwrite[{record}]", check, "history")


def no_oversubscription(record: str) -> Invariant:
    def check(initial, final, ledger, task):
        rb = rolled_back_agents(ledger, initial)
        writers = {e.agent_id for e in action_effects(ledger, initial) if e.record_id == record} - rb
        taken = sum((i.amount for a, i in task.intents.items() if a in writers and isinstance(i, Decrement) and i.record == record),
                    coerce_value(kind_of(record), 0))
        if taken > initial[record]:
            return [f"committed takes total {to_json_value(taken)} > initial {to_json_value(initial[record])}"]
        return []
    return Invariant(f"no_oversubscription[{record}]", check, "history")


def sum_within_cap(records: Sequence[str], cap: str) -> Invariant:
    records = tuple(records)

    def check(initial, final, ledger, task):
        total = sum((final[r] for r in records), Decimal(0))
        return [f"total spend {to_json_value(total)} > cap {to_json_value(initial[cap])}"] if total > initial[cap] else []
    return Invariant(f"sum_within_cap[{cap}]", check, "constraint")


def unchanged(record: str) -> Invariant:
    def check(initial, final, ledger, task):
        if any(record in i.writes for i in task.intents.values()):
            return []
        return [f"effect #{e.seq} by {e.agent_id} changed {record} from {to_json_value(e.old_value)} to {to_json_value(e.new_value)}"
                for e in ledger.effects_for(record_id=record) if normalize_value(e.new_value) != normalize_value(e.old_value)]
    return Invariant(f"unchanged[{record}]", check, "history")


def sum_at_least(records: Sequence[str], floor: Any) -> Invariant:
    records = tuple(records)
    floor = Decimal(str(floor))

    def check(initial, final, ledger, task):
        total = sum((final[r] for r in records), Decimal(0))
        return [f"combined balance {to_json_value(total)} < {floor}"] if total < floor else []
    return Invariant(f"sum_at_least[{'+'.join(records)}]", check, "constraint")


def conserved(records: Sequence[str]) -> Invariant:
    records = tuple(records)

    def check(initial, final, ledger, task):
        before = sum((initial[r] for r in records), Decimal(0))
        after = sum((final[r] for r in records), Decimal(0))
        return [f"total changed from {to_json_value(before)} to {to_json_value(after)}"] if before != after else []
    return Invariant(f"conserved[{'+'.join(records)}]", check, "conservation")


def accounted(records: Sequence[str]) -> Invariant:
    """Net change of ``records`` == sum of ``net_delta`` over agents that committed and did not roll back."""
    records = tuple(records)

    def check(initial, final, ledger, task):
        rb = rolled_back_agents(ledger, initial)
        committed = {e.agent_id for e in action_effects(ledger, initial)} - rb
        expected = sum((i.net_delta for a, i in task.intents.items()
                        if a in committed and set(i.conserved_records) <= set(records) and i.conserved_records), Decimal(0))
        actual = sum((Decimal(final[r]) - Decimal(initial[r]) for r in records), Decimal(0))
        if actual != expected:
            return [f"net change {actual} != committed intents' {expected}"]
        return []
    return Invariant(f"accounted[{'+'.join(records)}]", check, "conservation")


# --------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """A benchmark task. ``family`` is the contended template this task belongs to (a control shares it)."""

    name: str
    kind: str
    category: str
    initial: Mapping[str, Any]
    intents: Mapping[str, Intent]
    invariants: Tuple[Invariant, ...]
    description: str = ""
    family: str = ""

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown category {self.category!r}")
        initial = {rid: coerce_value(kind_of(rid), v) for rid, v in self.initial.items()}
        object.__setattr__(self, "initial", initial)
        object.__setattr__(self, "intents", dict(self.intents))
        object.__setattr__(self, "invariants", tuple(self.invariants))
        for agent, intent in self.intents.items():
            missing = [r for r in intent.reads if r not in initial]
            if missing:
                raise ValueError(f"intent of {agent} references unknown records {missing}")
            if not set(intent.writes) <= set(intent.reads):
                raise ValueError(f"intent of {agent} writes records it does not read")

    @property
    def agent_ids(self) -> Tuple[str, ...]:
        return tuple(self.intents)

    @property
    def is_control(self) -> bool:
        return self.category == "control"

    def restrict(self, agents: Sequence[str]) -> "Task":
        unknown = [a for a in agents if a not in self.intents]
        if unknown:
            raise ValueError(f"unknown agents {unknown}")
        return replace(self, intents={a: self.intents[a] for a in agents})

    def shared_records(self) -> Set[str]:
        """Records read by more than one agent's intent (empty for a control)."""
        seen: Dict[str, int] = {}
        for i in self.intents.values():
            for r in set(i.reads) | set(i.writes):
                seen[r] = seen.get(r, 0) + 1
        return {r for r, c in seen.items() if c > 1}


def control_of(builder: Callable[[str], Task], groups: Sequence[str], name: str) -> Task:
    """Matched uncontended control: agent ``i`` gets the whole record group ``builder(groups[i])`` to itself.

    ``builder(tag)`` must return the contended task for record group ``tag`` (records named with the tag).
    The control keeps, for agent ``i``, its intent in group ``i`` and all records and invariants of group ``i``;
    other agents' intents in that group are dropped, so their records there stay static.
    """
    parts = [builder(g) for g in groups]
    base = parts[0]
    ids = base.agent_ids
    if len(groups) < len(ids):
        raise ValueError("need one group per agent")
    initial: Dict[str, Any] = {}
    intents: Dict[str, Intent] = {}
    invariants: List[Invariant] = []
    for i, a in enumerate(ids):
        part = parts[i]
        overlap = set(initial) & set(part.initial)
        if overlap:
            raise ValueError(f"control groups share records {sorted(overlap)}")
        initial.update(part.initial)
        intents[a] = part.intents[a]
        invariants.extend(part.invariants)
    return Task(name, base.kind, "control", initial, intents, tuple(invariants),
                f"matched control of {base.name}: private copy of the record group per agent", family=base.family)
