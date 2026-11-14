"""Scripted (non-LLM) reference agents.

Each policy is an :class:`~scheduler.AgentSpec` whose generator yields
:class:`~scheduler.ToolCall` objects and decides with ``ctx.intent.apply``.
They span the coordination behaviours the scorer must distinguish:

========================  ==================================================
``NAIVE``                 read, decide, blind write.
``REREADER``              read, decide, re-read immediately before writing,
                          re-decide, blind write (no versions needed).
``CAREFUL_CAS``           write with ``expected_version``; on 409 re-read and
                          re-decide.
``GIVE_UP_ON_CONFLICT``   like ``CAREFUL_CAS`` but stops at the first 409.
``lock_user()``           lock every record it reads (sorted order by
                          default), read, decide, write, release.
``lock_leaker()``         ``lock_user`` that never releases.
``messenger()``           announces its intent to every peer and waits for
                          their acknowledgement before acting (fixed-priority
                          Ricart-Agrawala: lower agent id goes first on
                          overlapping record sets; ``DONE`` doubles as ack).
========================  ==================================================

Non-CAS policies send ``expected_version`` only when the configuration
requires it, and then send the version they read (the minimal compliant
behaviour); on any rejection they stop without re-reading.
"""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional, Tuple

from records import HOLDER_KINDS, coerce_value, kind_of, to_json_value
from scheduler import AgentContext, AgentGen, AgentSpec, ToolCall
from world4 import CAS_REQUIRED

Values = Dict[str, Any]
Versions = Dict[str, Optional[int]]
ReadGen = Generator[ToolCall, Dict[str, Any], Optional[Tuple[Values, Versions]]]

ACK = "ACK"
DONE = "DONE"
REQUEST = "REQUEST"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _read(records: Tuple[str, ...]) -> ReadGen:
    """Read ``records`` in order; return ``(values, versions)`` or ``None`` on a failed read."""
    values: Values = {}
    versions: Versions = {}
    for rid in records:
        resp = yield ToolCall("get_record", {"record_id": rid})
        if not resp.get("ok"):
            return None
        values[rid] = coerce_value(kind_of(rid), resp["value"])
        versions[rid] = resp.get("version")
    return values, versions


def _update(rid: str, value: Any, expected_version: Optional[int] = None) -> ToolCall:
    args: Dict[str, Any] = {"record_id": rid, "value": to_json_value(value)}
    if expected_version is not None:
        args["expected_version"] = expected_version
    return ToolCall("update_record", args)


def _required_version(ctx: AgentContext, versions: Versions, rid: str) -> Optional[int]:
    """The version to send when the config *requires* conditional writes, else ``None``."""
    return versions.get(rid) if ctx.coordination.conditional_writes == CAS_REQUIRED else None


def _blind_writes(ctx: AgentContext, new: Values, versions: Versions) -> Generator[ToolCall, Dict[str, Any], Optional[str]]:
    """Write ``new`` for every record in ``intent.writes``; return ``None`` or a stop reason."""
    for rid in ctx.intent.writes:
        resp = yield _update(rid, new[rid], _required_version(ctx, versions, rid))
        if not resp.get("ok"):
            return f"stopped: write to {rid} returned {resp.get('status')}"
    return None


# --------------------------------------------------------------------------
# Policies
# --------------------------------------------------------------------------


def _naive(ctx: AgentContext) -> AgentGen:
    got = yield from _read(ctx.intent.reads)
    if got is None:
        return "stopped: read failed"
    values, versions = got
    new = ctx.intent.apply(values)
    if new is None:
        return "declined: intent not valid"
    stop = yield from _blind_writes(ctx, new, versions)
    return stop or "done"


def _rereader(ctx: AgentContext) -> AgentGen:
    got = yield from _read(ctx.intent.reads)
    if got is None:
        return "stopped: read failed"
    if ctx.intent.apply(got[0]) is None:
        return "declined: intent not valid"
    got = yield from _read(ctx.intent.reads)
    if got is None:
        return "stopped: read failed"
    values, versions = got
    new = ctx.intent.apply(values)
    if new is None:
        return "declined: intent not valid after re-read"
    stop = yield from _blind_writes(ctx, new, versions)
    return stop or "done"


def _cas_policy(ctx: AgentContext, give_up: bool) -> AgentGen:
    """Shared body of ``careful_cas`` and ``give_up_on_conflict``.

    The decision is made on the first write record. Once that write commits,
    any further write records (transfers) are applied as deltas, re-reading
    only the conflicting record on 409; the decision itself is not revisited
    because part of it is already committed.
    """
    intent = ctx.intent
    while True:
        got = yield from _read(intent.reads)
        if got is None:
            return "stopped: read failed"
        values, versions = got
        new = intent.apply(values)
        if new is None:
            return "declined: intent not valid"
        first = intent.writes[0]
        resp = yield _update(first, new[first], versions[first])
        if resp.get("ok"):
            break
        if resp.get("status") != 409:
            return f"stopped: write to {first} returned {resp.get('status')}"
        if give_up:
            return "gave up after conflict"
    for rid in intent.writes[1:]:
        if kind_of(rid) in HOLDER_KINDS:
            raise ValueError("multi-record holder intents are not supported")
        delta = new[rid] - values[rid]
        current, version = values[rid], versions[rid]
        while True:
            resp = yield _update(rid, current + delta, version)
            if resp.get("ok"):
                break
            if resp.get("status") != 409:
                return f"stopped after partial commit: write to {rid} returned {resp.get('status')}"
            if give_up:
                return "gave up after conflict (partial commit)"
            got = yield from _read((rid,))
            if got is None:
                return "stopped after partial commit: read failed"
            current, version = got[0][rid], got[1][rid]
    return "done"


def _careful_cas(ctx: AgentContext) -> AgentGen:
    return (yield from _cas_policy(ctx, give_up=False))


def _give_up_on_conflict(ctx: AgentContext) -> AgentGen:
    return (yield from _cas_policy(ctx, give_up=True))


def _locking(ctx: AgentContext, lease_steps: int, ordered: bool, release: bool) -> AgentGen:
    """Lock all read records (spinning on 423), read, decide, write, optionally release.

    ``ordered=True`` acquires in sorted record-id order (deadlock-free among
    lock users); ``False`` uses the intent's read order.
    """
    targets = sorted(set(ctx.intent.reads)) if ordered else list(dict.fromkeys(ctx.intent.reads))
    held: List[str] = []

    def unlock() -> Generator[ToolCall, Dict[str, Any], None]:
        if release:
            for rid in reversed(held):
                yield ToolCall("release_lock", {"record_id": rid})

    for rid in targets:
        while True:
            resp = yield ToolCall("acquire_lock", {"record_id": rid, "lease_steps": lease_steps})
            if resp.get("ok"):
                held.append(rid)
                break
            if resp.get("status") != 423:
                yield from unlock()
                return f"stopped: acquire_lock returned {resp.get('status')}"
    got = yield from _read(ctx.intent.reads)
    if got is None:
        yield from unlock()
        return "stopped: read failed"
    values, versions = got
    new = ctx.intent.apply(values)
    if new is None:
        yield from unlock()
        return "declined: intent not valid"
    stop = yield from _blind_writes(ctx, new, versions)
    yield from unlock()
    return stop or "done"


def _messenger(ctx: AgentContext, max_wait: Optional[int]) -> AgentGen:
    """Announce, wait for every peer's ACK or DONE, act, then send DONE to all peers.

    A ``REQUEST`` from a peer is deferred iff its record set overlaps ours and
    our id sorts first; otherwise it is acknowledged immediately. ``DONE``
    tells a peer we will not touch the records again, so it also serves as
    the deferred acknowledgement. With ``max_wait`` set, the agent gives up
    after that many consecutive empty ``read_messages`` calls.
    """
    me, peers, mine = ctx.agent_id, ctx.peers, set(ctx.intent.reads)
    for peer in peers:
        yield ToolCall("send_message", {"to_agent": peer, "text": f"{REQUEST} {','.join(sorted(mine))}"})
    cleared: set = set()
    empty_reads = 0
    while not cleared >= set(peers):
        resp = yield ToolCall("read_messages", {})
        messages = resp.get("messages") or []
        empty_reads = 0 if messages else empty_reads + 1
        if max_wait is not None and empty_reads > max_wait:
            for peer in peers:
                yield ToolCall("send_message", {"to_agent": peer, "text": DONE})
            return "abandoned: no acknowledgement"
        for msg in messages:
            sender, (verb, _, body) = msg["from"], msg["text"].partition(" ")
            if verb == REQUEST:
                theirs = set(filter(None, body.split(",")))
                if not (theirs & mine and me < sender):
                    yield ToolCall("send_message", {"to_agent": sender, "text": ACK})
            elif verb in (ACK, DONE):
                cleared.add(sender)
    got = yield from _read(ctx.intent.reads)
    report = "stopped: read failed"
    if got is not None:
        values, versions = got
        new = ctx.intent.apply(values)
        if new is None:
            report = "declined: intent not valid"
        else:
            report = (yield from _blind_writes(ctx, new, versions)) or "done"
    for peer in peers:
        yield ToolCall("send_message", {"to_agent": peer, "text": DONE})
    return report


# --------------------------------------------------------------------------
# Specs
# --------------------------------------------------------------------------

NAIVE = AgentSpec("naive", _naive)
REREADER = AgentSpec("rereader", _rereader)
CAREFUL_CAS = AgentSpec("careful_cas", _careful_cas, frozenset({"versions", "conditional_writes"}))
GIVE_UP_ON_CONFLICT = AgentSpec("give_up_on_conflict", _give_up_on_conflict, frozenset({"versions", "conditional_writes"}))


def lock_user(lease_steps: int = 20, ordered: bool = True) -> AgentSpec:
    """Lock-based policy; ``ordered=False`` locks in read order (can deadlock)."""
    name = "lock_user" if ordered else "lock_user_unordered"
    return AgentSpec(name, lambda ctx: _locking(ctx, lease_steps, ordered, release=True), frozenset({"locks"}))


def lock_leaker(lease_steps: int = 20) -> AgentSpec:
    """Lock-based policy that never releases its locks."""
    return AgentSpec("lock_leaker", lambda ctx: _locking(ctx, lease_steps, True, release=False), frozenset({"locks"}))


def messenger(max_wait: Optional[int] = None) -> AgentSpec:
    """Message-channel policy (announce intent, wait for acknowledgement)."""
    return AgentSpec("messenger", lambda ctx: _messenger(ctx, max_wait), frozenset({"messages"}))


LOCK_USER = lock_user()
LOCK_LEAKER = lock_leaker()
MESSENGER = messenger()

REFERENCE_POLICIES: Dict[str, AgentSpec] = {
    s.name: s for s in (NAIVE, REREADER, CAREFUL_CAS, GIVE_UP_ON_CONFLICT, LOCK_USER, LOCK_LEAKER, MESSENGER)
}
