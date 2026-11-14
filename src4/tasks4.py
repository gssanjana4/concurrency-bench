"""Conflict tasks: initial records, one intent per agent, and invariants.

An :class:`Intent` is the deterministic business action an agent is asked to
perform. It names the records the action depends on (``reads``) and modifies
(``writes``) and defines :meth:`Intent.apply`, a pure function from record
values to new values, or ``None`` when the action is not valid in that state
(e.g. stock below the requested quantity). The scorer uses ``apply`` to
enumerate serial executions; scripted agents use it to decide what to write.

Task categories:

* ``conflict``    -- the intents cannot all succeed (last unit of stock, same
  seat, withdrawals exceeding the balance, same ticket).
* ``still_valid`` -- the agents touch the same records, so their operations
  conflict at the version level, but every intent remains valid in every
  serial order (stock 5, two agents each sell 1).
* ``write_skew``  -- the agents write *different* records, so per-record
  version checks never fire, yet a constraint spanning several records can
  be broken (shared budget, joint overdraft limit).
* ``control``     -- every agent works on its own records; no conflict.

Invariants are checked from the initial values, the final store values, the
ledger and the task itself; none consult agent self-reports.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from records import Ledger, action_effects, coerce_value, kind_of, normalize_value, to_json_value

CATEGORIES = ("conflict", "still_valid", "write_skew", "control")

Values = Mapping[str, Any]


def agent_ids(n: int) -> Tuple[str, ...]:
    """Canonical agent ids ``a0 .. a{n-1}`` (zero-padded for n > 10)."""
    if n < 1:
        raise ValueError("need at least one agent")
    width = len(str(n - 1))
    return tuple(f"a{i:0{width}d}" for i in range(n))


# --------------------------------------------------------------------------
# Intents
# --------------------------------------------------------------------------


class Intent:
    """Base class. Subclasses are frozen dataclasses.

    Every subclass has a ``wording`` field (0 or 1) that selects one of two
    paraphrases of :meth:`describe`. It changes the text only, never
    :meth:`apply`; 0 is the original (pilot) wording.

    Attributes (provided by subclasses):
        reads: record ids the decision depends on, in the agent's natural
            read order.
        writes: record ids the action modifies (a subset of ``reads``).
    """

    reads: Tuple[str, ...]
    writes: Tuple[str, ...]

    def apply(self, values: Values) -> Optional[Dict[str, Any]]:
        """New values for ``writes`` given current ``values``, or ``None`` if invalid."""
        raise NotImplementedError

    def describe(self) -> str:
        """One-sentence natural-language task text (for a model loop)."""
        raise NotImplementedError

    def is_valid(self, values: Values) -> bool:
        """Whether :meth:`apply` would succeed on ``values``."""
        return self.apply(values) is not None


@dataclass(frozen=True)
class Decrement(Intent):
    """Take ``amount`` from a numeric record if at least ``amount`` remains.

    Models selling units of stock (inventory) and withdrawing money (account).
    """

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

    def apply(self, values: Values) -> Optional[Dict[str, Any]]:
        current = values[self.record]
        if current < self.amount:
            return None
        return {self.record: current - self.amount}

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
    """Assign a free seat/ticket to ``holder``; invalid if someone else holds it."""

    record: str
    holder: str
    wording: int = 0

    @property
    def reads(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.record,)

    @property
    def writes(self) -> Tuple[str, ...]:  # type: ignore[override]
        return (self.record,)

    def apply(self, values: Values) -> Optional[Dict[str, Any]]:
        current = values[self.record]
        if current is not None and current != self.holder:
            return None
        return {self.record: self.holder}

    def describe(self) -> str:
        if self.wording == 1:
            return f"Give {self.record} to {self.holder}, unless someone else already holds it."
        return f"Assign {self.record} to {self.holder}, only if it is not held by anyone else."


@dataclass(frozen=True)
class Transfer(Intent):
    """Move ``amount`` from ``src`` to ``dst`` if ``src`` has at least ``amount``."""

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

    def apply(self, values: Values) -> Optional[Dict[str, Any]]:
        if values[self.src] < self.amount:
            return None
        return {self.src: values[self.src] - self.amount, self.dst: values[self.dst] + self.amount}

    def describe(self) -> str:
        amt = to_json_value(self.amount)
        if self.wording == 1:
            return f"Transfer {amt} out of {self.src} into {self.dst}, but only if {self.src} has at least {amt}."
        return f"Move {amt} from {self.src} to {self.dst}, only if {self.src} has enough."


@dataclass(frozen=True)
class GuardedSpend(Intent):
    """Add ``amount`` to the agent's own spend record if total spend stays within the cap.

    Reads the cap and every spend record; writes only ``own``. Two agents can
    each see room under the cap and each write their own record: per-record
    version checks pass, the shared cap is exceeded (write skew).
    """

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

    def apply(self, values: Values) -> Optional[Dict[str, Any]]:
        spent = values[self.own] + sum((values[r] for r in self.others), Decimal(0))
        if spent + self.amount > values[self.cap]:
            return None
        return {self.own: values[self.own] + self.amount}

    def describe(self) -> str:
        if self.wording == 1:
            return (
                f"Add {to_json_value(self.amount)} to {self.own}, provided the combined spend in "
                f"{', '.join((self.own,) + self.others)} does not go over {self.cap}."
            )
        return (
            f"Record a spend of {to_json_value(self.amount)} in {self.own}, only if total spend across "
            f"{', '.join((self.own,) + self.others)} stays within {self.cap}."
        )


@dataclass(frozen=True)
class JointWithdraw(Intent):
    """Withdraw from ``target`` if the combined balance of ``target`` and ``partners`` stays >= ``floor``.

    Individual accounts may go negative (joint overdraft); the constraint is
    on the sum. Each agent writes only its own account (write skew).
    """

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

    def apply(self, values: Values) -> Optional[Dict[str, Any]]:
        total = sum((values[r] for r in self.reads), Decimal(0))
        if total - self.amount < self.floor:
            return None
        return {self.target: values[self.target] - self.amount}

    def describe(self) -> str:
        if self.wording == 1:
            return (
                f"Take {to_json_value(self.amount)} out of {self.target}, provided {', '.join(self.reads)} "
                f"together still hold at least {to_json_value(self.floor)} afterwards."
            )
        return (
            f"Withdraw {to_json_value(self.amount)} from {self.target}, only if the combined balance of "
            f"{', '.join(self.reads)} stays at or above {to_json_value(self.floor)}."
        )


# --------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Invariant:
    """A named check returning human-readable violations (empty list: holds).

    ``check(initial, final, ledger, task)`` must depend only on its arguments.
    """

    name: str
    check: Callable[[Values, Values, Ledger, "Task"], List[str]]

    def violations(self, initial: Values, final: Values, ledger: Ledger, task: "Task") -> List[str]:
        """Run the check and prefix each violation with the invariant name."""
        return [f"{self.name}: {msg}" for msg in self.check(initial, final, ledger, task)]


def non_negative(record: str) -> Invariant:
    """Final value of ``record`` is >= 0 (stock, balance)."""

    def check(initial: Values, final: Values, ledger: Ledger, task: "Task") -> List[str]:
        return [f"{record} = {to_json_value(final[record])} < 0"] if final[record] < 0 else []

    return Invariant(f"non_negative[{record}]", check)


def no_holder_overwrite(record: str) -> Invariant:
    """No committed write replaced a non-null holder with a different value.

    Checked on the ledger, so an overwrite is caught even if the record later
    returns to its first holder.
    """

    def check(initial: Values, final: Values, ledger: Ledger, task: "Task") -> List[str]:
        return [
            f"effect #{e.seq} by {e.agent_id} replaced holder {e.old_value!r} with {e.new_value!r}"
            for e in ledger.effects_for(record_id=record)
            if e.old_value is not None and e.new_value != e.old_value
        ]

    return Invariant(f"no_holder_overwrite[{record}]", check)


def no_oversubscription(record: str) -> Invariant:
    """The amounts that agents *committed to taking* from ``record`` do not exceed its initial value.

    An agent counts as having taken its :class:`Decrement` amount if it
    committed at least one write to ``record`` that changed the value it was
    based on (:func:`records.action_effects`). This catches oversells whose
    final value looks healthy (two agents read stock 1 and both write 0),
    while a no-op write-back (read 0, write 0) is not a take: by rule, a
    write that does not change the value the agent saw is not the agent's
    committed intent.
    """

    def check(initial: Values, final: Values, ledger: Ledger, task: "Task") -> List[str]:
        writers = {e.agent_id for e in action_effects(ledger, initial) if e.record_id == record}
        taken = sum(
            (i.amount for a, i in task.intents.items() if a in writers and isinstance(i, Decrement) and i.record == record),
            coerce_value(kind_of(record), 0),
        )
        if taken > initial[record]:
            return [f"committed takes total {to_json_value(taken)} > initial {to_json_value(initial[record])}"]
        return []

    return Invariant(f"no_oversubscription[{record}]", check)


def sum_within_cap(records: Sequence[str], cap: str) -> Invariant:
    """Final sum of ``records`` <= the *initial* value of ``cap`` (shared budget).

    The cap is the task's constraint, so raising it mid-episode does not make
    overspending legal; a changed cap is reported by :func:`unchanged`.
    """
    records = tuple(records)

    def check(initial: Values, final: Values, ledger: Ledger, task: "Task") -> List[str]:
        total = sum((final[r] for r in records), Decimal(0))
        return [f"total spend {to_json_value(total)} > cap {to_json_value(initial[cap])}"] if total > initial[cap] else []

    return Invariant(f"sum_within_cap[{cap}]", check)


def unchanged(record: str) -> Invariant:
    """No agent changed ``record`` unless some intent in the task writes it (e.g. a budget cap).

    Checked on the ledger, so a change that is later reverted is still caught.
    """

    def check(initial: Values, final: Values, ledger: Ledger, task: "Task") -> List[str]:
        if any(record in i.writes for i in task.intents.values()):
            return []
        return [
            f"effect #{e.seq} by {e.agent_id} changed {record} from {to_json_value(e.old_value)} to {to_json_value(e.new_value)}"
            for e in ledger.effects_for(record_id=record)
            if normalize_value(e.new_value) != normalize_value(e.old_value)
        ]

    return Invariant(f"unchanged[{record}]", check)


def sum_at_least(records: Sequence[str], floor: Any) -> Invariant:
    """Sum of ``records`` >= ``floor`` in the final state (joint overdraft limit)."""
    records = tuple(records)
    floor = Decimal(str(floor))

    def check(initial: Values, final: Values, ledger: Ledger, task: "Task") -> List[str]:
        total = sum((final[r] for r in records), Decimal(0))
        return [f"combined balance {to_json_value(total)} < {floor}"] if total < floor else []

    return Invariant(f"sum_at_least[{'+'.join(records)}]", check)


def conserved(records: Sequence[str]) -> Invariant:
    """Sum of ``records`` is unchanged (transfers neither create nor destroy money)."""
    records = tuple(records)

    def check(initial: Values, final: Values, ledger: Ledger, task: "Task") -> List[str]:
        before = sum((initial[r] for r in records), Decimal(0))
        after = sum((final[r] for r in records), Decimal(0))
        return [f"total changed from {to_json_value(before)} to {to_json_value(after)}"] if before != after else []

    return Invariant(f"conserved[{'+'.join(records)}]", check)


# --------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """A benchmark task.

    Attributes:
        name: unique name, including the agent count (``inventory_last_unit/n2``).
        kind: record kind under test.
        category: one of :data:`CATEGORIES`.
        initial: initial record values.
        intents: agent id -> :class:`Intent`.
        invariants: business rules checked on the outcome.
        description: one-line summary.
    """

    name: str
    kind: str
    category: str
    initial: Mapping[str, Any]
    intents: Mapping[str, Intent]
    invariants: Tuple[Invariant, ...]
    description: str = ""

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
        """Agent ids in task order."""
        return tuple(self.intents)

    def restrict(self, agents: Sequence[str]) -> "Task":
        """Same task (records, invariants) with only ``agents``' intents, for paired runs."""
        unknown = [a for a in agents if a not in self.intents]
        if unknown:
            raise ValueError(f"unknown agents {unknown}")
        return replace(self, intents={a: self.intents[a] for a in agents})

    def serially_valid_for_all(self) -> bool:
        """Whether every intent succeeds when all are run serially in task order."""
        values = dict(self.initial)
        for intent in self.intents.values():
            new = intent.apply(values)
            if new is None:
                return False
            values.update(new)
        return True


# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------


def inventory_last_unit(n: int = 2) -> Task:
    """Stock 1; every agent tries to sell 1. Only one sale is valid."""
    ids, rec = agent_ids(n), "inventory:widget"
    return Task(
        f"inventory_last_unit/n{n}", "inventory", "conflict", {rec: 1},
        {a: Decrement(rec, 1) for a in ids},
        (non_negative(rec), no_oversubscription(rec)),
        "last unit of stock",
    )


def inventory_still_valid(n: int = 2) -> Task:
    """Stock ``max(5, n)``; every agent sells 1. Conflicts occur, all sales are valid."""
    ids, rec = agent_ids(n), "inventory:widget"
    return Task(
        f"inventory_still_valid/n{n}", "inventory", "still_valid", {rec: max(5, n)},
        {a: Decrement(rec, 1) for a in ids},
        (non_negative(rec), no_oversubscription(rec)),
        "shared stock with room for every sale",
    )


def inventory_control(n: int = 2) -> Task:
    """Each agent sells 1 unit of its own item (stock 1 each)."""
    ids = agent_ids(n)
    recs = {a: f"inventory:item-{a}" for a in ids}
    return Task(
        f"inventory_control/n{n}", "inventory", "control", {r: 1 for r in recs.values()},
        {a: Decrement(recs[a], 1) for a in ids},
        tuple(inv for r in recs.values() for inv in (non_negative(r), no_oversubscription(r))),
        "disjoint items",
    )


def seat_same(n: int = 2) -> Task:
    """One free seat; each agent books it for a different customer."""
    ids, rec = agent_ids(n), "seat:concert-1/12A"
    return Task(
        f"seat_same/n{n}", "seat", "conflict", {rec: None},
        {a: Claim(rec, f"customer-{a}") for a in ids},
        (no_holder_overwrite(rec),),
        "same seat for different customers",
    )


def seat_control(n: int = 2) -> Task:
    """Each agent books its own seat."""
    ids = agent_ids(n)
    recs = {a: f"seat:concert-1/row-{a}" for a in ids}
    return Task(
        f"seat_control/n{n}", "seat", "control", {r: None for r in recs.values()},
        {a: Claim(recs[a], f"customer-{a}") for a in ids},
        tuple(no_holder_overwrite(r) for r in recs.values()),
        "disjoint seats",
    )


def ticket_same(n: int = 2) -> Task:
    """One unassigned support ticket; each agent claims it for itself."""
    ids, rec = agent_ids(n), "ticket:T-100"
    return Task(
        f"ticket_same/n{n}", "ticket", "conflict", {rec: None},
        {a: Claim(rec, a) for a in ids},
        (no_holder_overwrite(rec),),
        "same ticket claimed",
    )


def ticket_control(n: int = 2) -> Task:
    """Each agent claims its own ticket."""
    ids = agent_ids(n)
    recs = {a: f"ticket:T-{200 + i}" for i, a in enumerate(ids)}
    return Task(
        f"ticket_control/n{n}", "ticket", "control", {r: None for r in recs.values()},
        {a: Claim(recs[a], a) for a in ids},
        tuple(no_holder_overwrite(r) for r in recs.values()),
        "disjoint tickets",
    )


def account_overdraw(n: int = 2) -> Task:
    """Balance 100.00; each agent withdraws 60.00 (sum exceeds the balance)."""
    ids, rec = agent_ids(n), "account:acct-1"
    return Task(
        f"account_overdraw/n{n}", "account", "conflict", {rec: "100.00"},
        {a: Decrement(rec, "60.00") for a in ids},
        (non_negative(rec), no_oversubscription(rec)),
        "withdrawals whose sum exceeds the balance",
    )


def account_still_valid(n: int = 2) -> Task:
    """Balance ``100.00 * n``; each agent withdraws 30.00 (all valid)."""
    ids, rec = agent_ids(n), "account:acct-1"
    return Task(
        f"account_still_valid/n{n}", "account", "still_valid", {rec: Decimal("100.00") * n},
        {a: Decrement(rec, "30.00") for a in ids},
        (non_negative(rec), no_oversubscription(rec)),
        "shared balance with room for every withdrawal",
    )


def transfer_shared_source(n: int = 2) -> Task:
    """Source 100.00; each agent moves 60.00 from it to its own account."""
    ids, src = agent_ids(n), "account:pool"
    dsts = {a: f"account:dest-{a}" for a in ids}
    records = (src,) + tuple(dsts.values())
    return Task(
        f"transfer_shared_source/n{n}", "account", "conflict", {src: "100.00", **{d: "0.00" for d in dsts.values()}},
        {a: Transfer(src, dsts[a], "60.00") for a in ids},
        (non_negative(src), conserved(records)),
        "transfers from one source whose sum exceeds its balance",
    )


def transfer_opposite(n: int = 2) -> Task:
    """Agents move 30.00 around a ring of accounts (a0: acct-0 -> acct-1, a1: acct-1 -> acct-0 for n=2).

    Every transfer is valid in every order; with locks taken in read order
    (not sorted) the agents can deadlock.
    """
    ids = agent_ids(n)
    accts = [f"account:ring-{i}" for i in range(max(n, 2))]
    intents = {a: Transfer(accts[i], accts[(i + 1) % len(accts)], "30.00") for i, a in enumerate(ids)}
    return Task(
        f"transfer_opposite/n{n}", "account", "still_valid", {r: "100.00" for r in accts},
        intents,
        tuple(non_negative(r) for r in accts) + (conserved(accts),),
        "transfers in opposite directions; all valid",
    )


def budget_write_skew(n: int = 2) -> Task:
    """Shared cap 100.00, per-agent spend records at 0; each agent spends 60.00."""
    ids, cap = agent_ids(n), "budget:team/cap"
    spends = {a: f"budget:team/spend-{a}" for a in ids}
    return Task(
        f"budget_write_skew/n{n}", "budget", "write_skew", {cap: "100.00", **{s: "0.00" for s in spends.values()}},
        {a: GuardedSpend(spends[a], tuple(s for b, s in spends.items() if b != a), cap, "60.00") for a in ids},
        (sum_within_cap(tuple(spends.values()), cap), unchanged(cap)),
        "two agents each spend from a shared budget",
    )


def budget_control(n: int = 2) -> Task:
    """Like :func:`budget_write_skew` but the cap (100.00 * n) fits every spend."""
    ids, cap = agent_ids(n), "budget:team/cap"
    spends = {a: f"budget:team/spend-{a}" for a in ids}
    return Task(
        f"budget_control/n{n}", "budget", "control", {cap: Decimal("100.00") * n, **{s: "0.00" for s in spends.values()}},
        {a: GuardedSpend(spends[a], tuple(s for b, s in spends.items() if b != a), cap, "60.00") for a in ids},
        (sum_within_cap(tuple(spends.values()), cap), unchanged(cap)),
        "shared budget large enough for every spend",
    )


def joint_account_write_skew(n: int = 2) -> Task:
    """``n`` joint accounts at 50.00 each (combined floor 0); agent i withdraws 60.00 from account i."""
    ids = agent_ids(n)
    accts = {a: f"account:joint-{a}" for a in ids}
    all_accts = tuple(accts.values())
    return Task(
        f"joint_account_write_skew/n{n}", "account", "write_skew", {r: "50.00" for r in all_accts},
        {a: JointWithdraw(accts[a], tuple(r for r in all_accts if r != accts[a]), "60.00") for a in ids},
        (sum_at_least(all_accts, 0),),
        "withdrawals from different accounts sharing an overdraft limit",
    )


CATALOG: Dict[str, Callable[[int], Task]] = {
    f.__name__: f
    for f in (
        inventory_last_unit,
        inventory_still_valid,
        inventory_control,
        seat_same,
        seat_control,
        ticket_same,
        ticket_control,
        account_overdraw,
        account_still_valid,
        transfer_shared_source,
        transfer_opposite,
        budget_write_skew,
        budget_control,
        joint_account_write_skew,
    )
}


def all_tasks(n: int = 2) -> List[Task]:
    """Every catalog task instantiated for ``n`` agents."""
    return [factory(n) for factory in CATALOG.values()]
