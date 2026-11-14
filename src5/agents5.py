"""Scripted reference policies (Study 2): correct protocols and naive ones (the built-in manipulation check).

Correct protocols (must end ``clean``, or ``compensated`` for verify-and-compensate, on contended tasks, and
``clean`` on controls, within the call cap):

==========================  ===========================================================================
``cas_retry``               read, decide, conditional write; on 409 re-read and re-decide. A transfer
                            debits first, then credits with a re-read delta loop (Study 1's careful_cas).
                            Correct for single-record intents and transfers; **naive** for write skew.
``promote_before_write``    read every record of the guard; conditionally write back (no-op, "promote")
                            every read record in sorted order (its own record included, so every agent
                            contends on the same first record); then the conditional own write. Any
                            409 -> back off, restart. Correct for write skew (OCC with read-set
                            validation); promotion *must* precede the own write.
``verify_and_compensate``   write, re-read the guard, and if the constraint is broken put the old value
                            back (a saga), back off and retry. Works without versions (``none``).
``lock_protected``          lock every record of the guard in sorted order, read, decide, write with the
                            fencing token (renewing a lease that is about to run out), release.
==========================  ===========================================================================

``cas_claim`` (V2)          seat/ticket with the ``claim`` tool: read, ``claim`` with ``expected_version``;
                            on 409 re-read and re-decide (declines once someone else holds it).

Naive policies (must fail on contended tasks, never on controls): ``naive`` (read, decide, blind write),
``rereader`` (re-reads after thinking, then blind write), ``promote_after_write`` (own write first),
``lock_writes_only`` (locks only the records it writes), and (V2):

* ``naive_claim`` (review V1 B1): read, then ``claim`` with no version and no lock -- what Study 1 models did on
  99 % of seat/ticket writes. Must fail in every configuration now that ``claim`` is a plain overwrite.
* ``reacquire_no_reread`` (review V1 B5, L1): locks with lease 1, reads, makes one innocent call, its fenced
  write gets 409 (lease ended); it re-acquires (new token) and writes the value computed under the old lease.
  Every committed write is fenced and in-lease, yet updates are lost: fencing makes writes exclusive, not
  read-modify-write.
* ``lease_then_tokenless`` (review V1 B5, L2): locks with lease 1, reads, makes 4 innocent calls (the lease runs
  out), then writes with no token on the now unlocked record.

Probes (must never produce a failed outcome): ``lock_short_lease`` (lease 1, so its fenced writes come after its
lease ended and are rejected) and ``lock_no_fence`` (holds the lock but writes without the token; rejected
with 428). Both are *rejection* probes: they show the server refuses the misuse, and they never write
(fulfilment 0), so they say nothing about data safety beyond that. ``lock_own_first`` (review V2 F5, L3) is a
deadlock diagnostic: hold-and-wait, own record first; two such agents deadlock on write-skew tasks, which the
scheduler records (``deadlock_rounds``); it resolves when a wait times out (423).

Back-off (V2, review V1 B2): after a failed attempt a policy makes ``k`` back-off reads,
``k = U{0..1} + (5 + 2 * attempt if rank is odd else 0)``, the uniform part drawn by
``random.Random(f"{schedule seed}|{agent id}|backoff|{attempt}")`` and rank = the number in the agent id. The V1 rule
(``1 + (rank % 3) * (attempt + 1)``) was too weak once every call is followed by think time: verify-and-compensate
livelocked symmetrically (write, verify, undo, in step) and hit the call cap. Purely random back-offs
(``U{1..2+a}``, ``U{0..4}``, ``{0,4}``, exponential) still left 1-5 % of write-skew episodes above 80 % of the cap
(``src5_verify`` notes in CHANGES_V2.md); the rank offset separates the two agents' retries by about five calls,
the random part keeps the schedule from fixing who retries when. ``verify_and_compensate`` re-reads, during its
back-off, the guard records it saw change and declines as soon as those fresh values (and its own original value)
make its guard false, so the agent that backs off stops as soon as the other's retry lands.
"""

from __future__ import annotations

import hashlib
import random
from decimal import Decimal
from typing import Any, Dict, Generator, List, Optional, Tuple

from records5 import HOLDER_KINDS, coerce_value, kind_of, normalize_value, to_json_value
from scheduler5 import AgentContext, AgentGen, AgentSpec, ToolCall
from tasks5 import Claim, Decrement, GuardedSpend, JointWithdraw, Transfer
from world5 import CAS_REQUIRED

Values = Dict[str, Any]
Versions = Dict[str, Optional[int]]
MAX_ATTEMPTS = 6


def _read(records) -> Generator[ToolCall, Dict[str, Any], Optional[Tuple[Values, Versions]]]:
    values: Values = {}
    versions: Versions = {}
    for rid in records:
        resp = yield ToolCall("get_record", {"record_id": rid})
        if not resp.get("ok"):
            return None
        values[rid] = coerce_value(kind_of(rid), resp["value"])
        versions[rid] = resp.get("version")
    return values, versions


def _update(rid: str, value: Any, expected_version: Optional[int] = None, token: Optional[int] = None) -> ToolCall:
    args: Dict[str, Any] = {"record_id": rid, "value": to_json_value(value)}
    if expected_version is not None:
        args["expected_version"] = expected_version
    if token is not None:
        args["fencing_token"] = token
    return ToolCall("update_record", args)


def _h(agent_id: str) -> int:
    return int(hashlib.sha256(agent_id.encode()).hexdigest()[:8], 16)


def _rank(agent_id: str) -> int:
    digits = "".join(ch for ch in agent_id if ch.isdigit())
    return int(digits) if digits else _h(agent_id) % 8


BACKOFF_JITTER = 1
BACKOFF_OFFSET = 5


def backoff_reads(ctx: AgentContext, attempt: int) -> int:
    """Randomized back-off length (see module docstring), seeded by the episode's schedule seed, agent and attempt."""
    rng = random.Random(f"{ctx.seed}|{ctx.agent_id}|backoff|{attempt}")
    offset = (BACKOFF_OFFSET + 2 * attempt) if _rank(ctx.agent_id) % 2 else 0
    return rng.randint(0, BACKOFF_JITTER) + offset


def _backoff(ctx: AgentContext, attempt: int):
    """Randomized back-off: ``backoff_reads`` re-reads of the first record."""
    rid = ctx.intent.reads[0]
    for _ in range(backoff_reads(ctx, attempt)):
        yield ToolCall("get_record", {"record_id": rid})


def _required(ctx: AgentContext, versions: Versions, rid: str) -> Optional[int]:
    return versions.get(rid) if ctx.coordination.conditional_writes == CAS_REQUIRED else None


def constraint_holds(intent, values: Values) -> bool:
    """The cross-record constraint the guard protects, on the state *after* the agent's own write."""
    if isinstance(intent, GuardedSpend):
        return values[intent.own] + sum((values[r] for r in intent.others), Decimal(0)) <= values[intent.cap]
    if isinstance(intent, JointWithdraw):
        return sum((values[r] for r in intent.reads), Decimal(0)) >= intent.floor
    if isinstance(intent, (Decrement, Transfer)):
        rec = intent.record if isinstance(intent, Decrement) else intent.src
        return values[rec] >= 0
    return True


# --------------------------------------------------------------------------
# Naive
# --------------------------------------------------------------------------


def _naive(ctx: AgentContext) -> AgentGen:
    got = yield from _read(ctx.intent.reads)
    if got is None:
        return "stopped: read failed"
    values, versions = got
    new = ctx.intent.apply(values)
    if new is None:
        return "declined"
    for rid in ctx.intent.writes:
        resp = yield _update(rid, new[rid], _required(ctx, versions, rid))
        if not resp.get("ok"):
            return f"stopped: write {resp.get('status')}"
    return "done"


def _rereader(ctx: AgentContext) -> AgentGen:
    got = yield from _read(ctx.intent.reads)
    if got is None or ctx.intent.apply(got[0]) is None:
        return "declined"
    got = yield from _read(ctx.intent.reads)
    if got is None:
        return "stopped: read failed"
    values, versions = got
    new = ctx.intent.apply(values)
    if new is None:
        return "declined after re-read"
    for rid in ctx.intent.writes:
        resp = yield _update(rid, new[rid], _required(ctx, versions, rid))
        if not resp.get("ok"):
            return f"stopped: write {resp.get('status')}"
    return "done"


# --------------------------------------------------------------------------
# CAS retry (Study 1 careful_cas, bounded)
# --------------------------------------------------------------------------


def _cas_retry(ctx: AgentContext) -> AgentGen:
    intent = ctx.intent
    for attempt in range(MAX_ATTEMPTS * 2):
        got = yield from _read(intent.reads)
        if got is None:
            return "stopped: read failed"
        values, versions = got
        new = intent.apply(values)
        if new is None:
            return "declined"
        first = intent.writes[0]
        resp = yield _update(first, new[first], versions[first])
        if resp.get("ok"):
            break
        if resp.get("status") != 409:
            return f"stopped: write {resp.get('status')}"
    else:
        return "gave up"
    for rid in intent.writes[1:]:
        if kind_of(rid) in HOLDER_KINDS:
            raise ValueError("multi-record holder intents are not supported")
        delta = new[rid] - values[rid]
        current, version = values[rid], versions[rid]
        for _ in range(MAX_ATTEMPTS * 2):
            resp = yield _update(rid, current + delta, version)
            if resp.get("ok"):
                break
            if resp.get("status") != 409:
                return f"stopped after partial commit: write {resp.get('status')}"
            got = yield from _read((rid,))
            if got is None:
                return "stopped after partial commit"
            current, version = got[0][rid], got[1][rid]
        else:
            return "gave up after partial commit"
    return "done"


# --------------------------------------------------------------------------
# Promotion
# --------------------------------------------------------------------------


def _promote(ctx: AgentContext, before: bool) -> AgentGen:
    """``before``: no-op conditional write-back of every guard record in sorted order (the own record included,
    so all agents contend on the same first record), then the conditional own write. ``before=False``
    (naive): own write first, then the write-backs."""
    intent = ctx.intent
    if len(intent.writes) != 1:
        raise ValueError("promotion policy supports single-write intents")
    own = intent.writes[0]
    for attempt in range(MAX_ATTEMPTS):
        got = yield from _read(intent.reads)
        if got is None:
            return "stopped: read failed"
        values, versions = got
        new = intent.apply(values)
        if new is None:
            return "declined"
        if before:
            seq = [(r, values[r]) for r in sorted(intent.reads)] + [(own, new[own])]
        else:
            seq = [(own, new[own])] + [(r, values[r]) for r in sorted(intent.reads) if r != own]
        ok, own_done = True, False
        for rid, v in seq:
            resp = yield _update(rid, v, versions[rid])
            if not resp.get("ok"):
                ok = False
                break
            versions[rid] = resp.get("version")
            if rid == own and v == new[own]:
                own_done = True
        if ok or own_done:
            return "done" if ok else "done (own write committed, promotion failed)"
        yield from _backoff(ctx, attempt)
    return "gave up"


# --------------------------------------------------------------------------
# Verify and compensate
# --------------------------------------------------------------------------


def _verify_compensate(ctx: AgentContext) -> AgentGen:
    intent = ctx.intent
    if len(intent.writes) != 1:
        raise ValueError("verify-and-compensate supports single-write intents")
    own = intent.writes[0]
    cas = ctx.coordination.conditional_writes != "off"
    for attempt in range(MAX_ATTEMPTS):
        got = yield from _read(intent.reads)
        if got is None:
            return "stopped: read failed"
        values, versions = got
        new = intent.apply(values)
        if new is None:
            return "declined"
        resp = yield _update(own, new[own], versions[own] if cas else _required(ctx, versions, own))
        if not resp.get("ok"):
            if resp.get("status") == 409:
                yield from _backoff(ctx, attempt)
                continue
            return f"stopped: write {resp.get('status')}"
        my_version = resp.get("version")
        others = tuple(r for r in intent.reads if r != own)  # only this agent writes its own record
        check = yield from _read(others)
        if check is None:
            return "stopped: verification read failed"
        if constraint_holds(intent, {**check[0], own: new[own]}):
            return "done"
        back = yield _update(own, values[own], my_version if cas else None)
        if not back.get("ok"):
            return f"stopped: compensation write {back.get('status')}"
        # back-off: re-read the guard records seen to change; decline once fresh values make the guard false
        changed = [r for r in others if normalize_value(check[0][r]) != normalize_value(values[r])] or list(others)
        fresh: Values = {}
        for j in range(backoff_reads(ctx, attempt)):
            rid = changed[j % len(changed)]
            r = yield ToolCall("get_record", {"record_id": rid})
            if not r.get("ok"):
                return "stopped: read failed"
            fresh[rid] = coerce_value(kind_of(rid), r["value"])
            if all(c in fresh for c in changed) and intent.apply({**values, **fresh}) is None:
                return "declined after compensation"
    return "gave up"


# --------------------------------------------------------------------------
# Locks
# --------------------------------------------------------------------------


def _locking(ctx: AgentContext, targets: List[str], lease: Optional[int] = None, fence: bool = True) -> AgentGen:
    intent = ctx.intent
    need = 3 * len(set(intent.reads) | set(intent.writes)) + 4
    lease = lease or min(20, need)
    for attempt in range(MAX_ATTEMPTS):
        held: Dict[str, int] = {}
        left: Dict[str, int] = {}
        failed = False
        for rid in targets:
            tries = 0
            while True:
                resp = yield ToolCall("acquire_lock", {"record_id": rid, "lease_calls": lease})
                for r in left:
                    left[r] -= 1
                if resp.get("ok"):
                    held[rid] = resp["fencing_token"]
                    left[rid] = resp["lease_remaining"]
                    break
                tries += 1
                if resp.get("status") != 423 or tries >= 4:
                    failed = True
                    break
            if failed:
                break
        if failed:
            for rid in reversed(list(held)):
                yield ToolCall("release_lock", {"record_id": rid})
            yield from _backoff(ctx, attempt)
            continue
        got = yield from _read(intent.reads)
        for r in left:
            left[r] -= len(intent.reads)
        if got is None:
            return "stopped: read failed"
        values, versions = got
        new = intent.apply(values)
        result = "declined"
        if new is not None:
            result = "done"
            for rid in intent.writes:
                if rid in left and left[rid] < 2:
                    resp = yield ToolCall("renew_lock", {"record_id": rid, "lease_calls": lease})
                    for r in left:
                        left[r] -= 1
                    if resp.get("ok"):
                        left[rid] = resp["lease_remaining"]
                tok = held.get(rid) if fence else None
                resp = yield _update(rid, new[rid], _required(ctx, versions, rid), tok)
                for r in left:
                    left[r] -= 1
                if not resp.get("ok"):
                    result = f"stopped: write {resp.get('status')}"
                    break
        for rid in reversed(list(held)):
            yield ToolCall("release_lock", {"record_id": rid})
        return result
    return "gave up"


def _lock_protected(ctx: AgentContext) -> AgentGen:
    return (yield from _locking(ctx, sorted(set(ctx.intent.reads))))


def _lock_writes_only(ctx: AgentContext) -> AgentGen:
    return (yield from _locking(ctx, sorted(set(ctx.intent.writes))))


def _lock_short_lease(ctx: AgentContext) -> AgentGen:
    return (yield from _locking(ctx, sorted(set(ctx.intent.reads)), lease=1))


def _lock_no_fence(ctx: AgentContext) -> AgentGen:
    return (yield from _locking(ctx, sorted(set(ctx.intent.reads)), fence=False))


def _holder_of(ctx: AgentContext) -> str:
    return getattr(ctx.intent, "holder", ctx.agent_id)


def _naive_claim(ctx: AgentContext) -> AgentGen:
    """Read, then ``claim`` (no version, no lock); declines if the read shows another holder."""
    rid = ctx.intent.writes[0]
    got = yield from _read((rid,))
    if got is None:
        return "stopped: read failed"
    if ctx.intent.apply(got[0]) is None:
        return "declined"
    args: Dict[str, Any] = {"record_id": rid, "holder": _holder_of(ctx)}
    if ctx.coordination.conditional_writes == CAS_REQUIRED:
        args["expected_version"] = got[1][rid]
    resp = yield ToolCall("claim", args)
    return "done" if resp.get("ok") else f"stopped: claim {resp.get('status')}"


def _cas_claim(ctx: AgentContext) -> AgentGen:
    """Read, ``claim`` with ``expected_version``; on 409 re-read and re-decide."""
    rid = ctx.intent.writes[0]
    for _ in range(MAX_ATTEMPTS * 2):
        got = yield from _read((rid,))
        if got is None:
            return "stopped: read failed"
        if ctx.intent.apply(got[0]) is None:
            return "declined"
        resp = yield ToolCall("claim", {"record_id": rid, "holder": _holder_of(ctx), "expected_version": got[1][rid]})
        if resp.get("ok"):
            return "done"
        if resp.get("status") != 409:
            return f"stopped: claim {resp.get('status')}"
    return "gave up"


def _acquire_all(targets, lease: int):
    """Acquire every target (blocking acquire); ``None`` if one is refused, else {record: token}."""
    held: Dict[str, int] = {}
    for rid in targets:
        resp = yield ToolCall("acquire_lock", {"record_id": rid, "lease_calls": lease})
        if not resp.get("ok"):
            for r in reversed(list(held)):
                yield ToolCall("release_lock", {"record_id": r})
            return None
        held[rid] = resp["fencing_token"]
    return held


def _reacquire_no_reread(ctx: AgentContext) -> AgentGen:
    """Lease 1, read, one innocent call, fenced write -> 409 (lease ended); re-acquire, write the OLD value."""
    intent = ctx.intent
    targets = sorted(set(intent.reads))
    held = yield from _acquire_all(targets, 1)
    if held is None:
        return "stopped: lock refused"
    got = yield from _read(intent.reads)
    if got is None:
        return "stopped: read failed"
    values, versions = got
    new = intent.apply(values)
    if new is None:
        return "declined"
    yield ToolCall("list_effects", {})  # an innocent call: the lease has run out by now
    first = intent.writes[0]
    resp = yield _update(first, new[first], _required(ctx, versions, first), held.get(first))
    if not resp.get("ok"):
        held = yield from _acquire_all(targets, 20)  # new tokens; the values computed above are NOT re-read
        if held is None:
            return "stopped: lock refused on re-acquire"
        resp = yield _update(first, new[first], _required(ctx, versions, first), held.get(first))
    for rid in intent.writes[1:]:
        if resp.get("ok"):
            resp = yield _update(rid, new[rid], _required(ctx, versions, rid), held.get(rid))
    for rid in reversed(targets):
        yield ToolCall("release_lock", {"record_id": rid})
    return "done" if resp.get("ok") else f"stopped: write {resp.get('status')}"


TOKENLESS_IDLE_CALLS = 4


def _lease_then_tokenless(ctx: AgentContext) -> AgentGen:
    """Lease 1, read, let the lease run out (``TOKENLESS_IDLE_CALLS`` innocent calls, as in review V1 L2), then write
    without a token (the record is unlocked by then)."""
    intent = ctx.intent
    held = yield from _acquire_all(sorted(set(intent.reads)), 1)
    if held is None:
        return "stopped: lock refused"
    got = yield from _read(intent.reads)
    if got is None:
        return "stopped: read failed"
    values, versions = got
    new = intent.apply(values)
    if new is None:
        return "declined"
    for _ in range(TOKENLESS_IDLE_CALLS):
        yield ToolCall("list_effects", {})
    for rid in intent.writes:
        resp = yield _update(rid, new[rid], _required(ctx, versions, rid))
        if not resp.get("ok"):
            return f"stopped: write {resp.get('status')}"
    return "done"


def _lock_own_first(ctx: AgentContext) -> AgentGen:
    """Deadlock diagnostic (V2 F5 / V1 L3): hold-and-wait, own written record first, then the other guard records
    in sorted order, retrying a refused acquire while holding what it has; fenced write; release."""
    intent = ctx.intent
    order = list(intent.writes) + [r for r in sorted(intent.reads) if r not in intent.writes]
    tok: Dict[str, int] = {}
    for rid in order:
        for _ in range(4):
            resp = yield ToolCall("acquire_lock", {"record_id": rid, "lease_calls": 8})
            if resp.get("ok"):
                tok[rid] = resp["fencing_token"]
                break
        else:
            for r in reversed(list(tok)):
                yield ToolCall("release_lock", {"record_id": r})
            return "gave up"
    got = yield from _read(intent.reads)
    result = "stopped: read failed"
    if got is not None:
        values, versions = got
        new = intent.apply(values)
        result = "declined"
        if new is not None:
            result = "done"
            for rid in intent.writes:
                resp = yield _update(rid, new[rid], _required(ctx, versions, rid), tok.get(rid))
                if not resp.get("ok"):
                    result = f"stopped: write {resp.get('status')}"
                    break
    for r in reversed(list(tok)):
        yield ToolCall("release_lock", {"record_id": r})
    return result


# --------------------------------------------------------------------------
# Specs
# --------------------------------------------------------------------------

CAS = frozenset({"versions", "conditional_writes"})
LOCKS = frozenset({"locks"})

NAIVE = AgentSpec("naive", _naive)
REREADER = AgentSpec("rereader", _rereader)
CAS_RETRY = AgentSpec("cas_retry", _cas_retry, CAS)
PROMOTE_BEFORE = AgentSpec("promote_before_write", lambda c: _promote(c, True), CAS)
PROMOTE_AFTER = AgentSpec("promote_after_write", lambda c: _promote(c, False), CAS)
VERIFY_COMPENSATE = AgentSpec("verify_and_compensate", _verify_compensate)
LOCK_PROTECTED = AgentSpec("lock_protected", _lock_protected, LOCKS)
LOCK_WRITES_ONLY = AgentSpec("lock_writes_only", _lock_writes_only, LOCKS)
LOCK_SHORT_LEASE = AgentSpec("lock_short_lease", _lock_short_lease, LOCKS)
LOCK_NO_FENCE = AgentSpec("lock_no_fence", _lock_no_fence, LOCKS)
NAIVE_CLAIM = AgentSpec("naive_claim", _naive_claim)
CAS_CLAIM = AgentSpec("cas_claim", _cas_claim, CAS)
REACQUIRE_NO_REREAD = AgentSpec("reacquire_no_reread", _reacquire_no_reread, LOCKS)
LEASE_THEN_TOKENLESS = AgentSpec("lease_then_tokenless", _lease_then_tokenless, LOCKS)
LOCK_OWN_FIRST = AgentSpec("lock_own_first", _lock_own_first, LOCKS)

REFERENCE_POLICIES: Dict[str, AgentSpec] = {s.name: s for s in (
    NAIVE, REREADER, CAS_RETRY, PROMOTE_BEFORE, PROMOTE_AFTER, VERIFY_COMPENSATE, LOCK_PROTECTED, LOCK_WRITES_ONLY,
    LOCK_SHORT_LEASE, LOCK_NO_FENCE, NAIVE_CLAIM, CAS_CLAIM, REACQUIRE_NO_REREAD, LEASE_THEN_TOKENLESS, LOCK_OWN_FIRST)}

SINGLE_WRITE_ONLY = {"promote_before_write", "promote_after_write", "verify_and_compensate"}
CLAIM_ONLY = {"naive_claim", "cas_claim"}
CLAIM_FAMILIES = ("seat_same", "ticket_same")
WRITE_SKEW_FAMILIES = ("budget_write_skew", "joint_account_write_skew")

# family -> policies that are correct protocols there (expected outcome clean, or compensated for v&c)
CORRECT: Dict[str, Tuple[str, ...]] = {
    "inventory_last_unit": ("cas_retry", "lock_protected"),
    "inventory_still_valid": ("cas_retry", "lock_protected"),
    "seat_same": ("cas_retry", "cas_claim", "lock_protected"),
    "ticket_same": ("cas_retry", "cas_claim", "lock_protected"),
    "transfer_shared_source": ("cas_retry", "lock_protected"),
    "budget_write_skew": ("promote_before_write", "verify_and_compensate", "lock_protected"),
    "joint_account_write_skew": ("promote_before_write", "verify_and_compensate", "lock_protected"),
}
# family -> naive policies (expected to fail on the contended task, never on its control)
_LOCK_NAIVE = ("reacquire_no_reread", "lease_then_tokenless")  # V1 B5: fenced but not read-modify-write safe
NAIVE_FOR: Dict[str, Tuple[str, ...]] = {
    "inventory_last_unit": ("naive", "rereader") + _LOCK_NAIVE,
    "inventory_still_valid": ("naive", "rereader") + _LOCK_NAIVE,
    "seat_same": ("naive", "rereader", "naive_claim") + _LOCK_NAIVE,
    "ticket_same": ("naive", "rereader", "naive_claim") + _LOCK_NAIVE,
    "transfer_shared_source": ("naive", "rereader") + _LOCK_NAIVE,
    "budget_write_skew": ("naive", "rereader", "cas_retry", "promote_after_write", "lock_writes_only") + _LOCK_NAIVE,
    "joint_account_write_skew": ("naive", "rereader", "cas_retry", "promote_after_write", "lock_writes_only") + _LOCK_NAIVE,
}
# must never produce a failed outcome: two rejection probes (fencing refuses the misuse) and the deadlock diagnostic
PROBES = ("lock_short_lease", "lock_no_fence", "lock_own_first")


def applicable(policy: str, family: str) -> bool:
    if policy in SINGLE_WRITE_ONLY and family not in WRITE_SKEW_FAMILIES:
        return False
    if policy in CLAIM_ONLY and family not in CLAIM_FAMILIES:
        return False
    return True
