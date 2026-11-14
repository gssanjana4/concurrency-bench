"""Ground-truth scoring of Study 2 episodes (src5).

Inputs: the ledger (committed effects, call log, agent ends, scheduler flags), the final store and the task.
No agent self-report, no LLM judge. Derived from src4/score4.py; every change answers review T1 (sec. 1-5).

What the verdicts are -- and are not
------------------------------------
The API has no multi-call transactions; every call auto-commits. Each agent's whole session is treated as one
transaction with no begin, commit or abort point. Two verdicts are computed, and they measure different things:

``fs_nonserializable`` -- *specification-level final-state serializability over agent sessions* (renamed from
    Study 1's ``non_serializable``; it is NOT Adya/Berenson serializability of the executed history). Let ``A`` be
    the agents with a value-changing write that did not roll it back (``committed``; rolled-back agents are treated
    as aborted, see ``compensated``). The outcome is fs-serializable iff some order of ``A`` in which each
    ``intent.apply`` succeeds from the initial state ends in the final store. It ignores the executed reads.

``dsg_cycle`` -- an *Adya-style direct serialization graph* over the executed history. Nodes: every agent session
    with a successful read or a committed write. Versions: every committed write installs a version (the store's
    order). Reads: **every** successful ``get_record`` (``read_version`` from the server log), not only the last
    one before a write (Study 1's "effective read" filter is gone). Edges between distinct sessions: ww
    ``inst(x,v) -> inst(x,v+1)``; wr ``inst(x,v) -> reader of (x,v)``; rw ``reader of (x,v) -> inst(x,v+1)``. Blind
    writes add no read. ``dsg_cycle`` is True iff the graph has a cycle; ``dsg_g1c`` iff a cycle exists on ww/wr
    edges alone; ``dsg_cycle_committed`` is the same test on the subgraph induced by ``committed``.
    ``dsg_basis_cycle`` (*V2*, review V1 non-blocking 1) is the per-write *basis* DSG: each committed write
    depends on its writer's latest successful read, before that write, of each record of its intent's reads;
    rolled-back sessions are aborted (their reads dropped; their versions stay). It removes the definitional
    disagreements (reads of attempts that got a 409, a rereader's dead first read) and is reported next to the
    all-reads and committed-only variants.
    Deviations from Adya, by construction of the API: every write (also intermediate and no-op ones) is an
    installed version; sessions never abort, so the reads of a retried attempt (after a 409) and post-write
    verification reads stay in the transaction. Hence correct retry and verify-and-compensate protocols are
    usually *cyclic* while fs-serializable. Agreement between the verdicts is reported, not assumed
    (README "Checker agreement", produced by ``validity5.py``). Neither direction is implied: an fs failure
    can be acyclic (a half transfer: an atomicity failure has no cycle), and ``clean`` (a specification-level
    outcome) can sit on a cyclic committed history.

Non-exclusive flags (episode level; Study 1's single primary label hid co-occurring failures)
    ``missing_leg``        atomicity: an agent that committed part of a multi-record intent (some written record
                           has none of its actions) and did not roll back. The API has no multi-record atomicity,
                           so every transfer is a hand-built saga.
    ``compensated``        some agent rolled back: on every record it changed, its last write restored the value
                           its first change was based on (``tasks5.rolled_back_agents``). Episodes whose only
                           failure is a rollback are reported as ``compensated``, not as a partial action.
    ``compensated_after_violation``  compensated and the constraint was violated at some point (broken, repaired).
    ``compensation_exposed`` another session read a version that a rolled-back agent later undid itself
                           (G1a-shaped read of an aborted write).
    ``guard_violation``    an agent's write equals its intent's unguarded effect on the state it acted on, while
                           its guard was false there (it ignored its own condition, e.g. sold from stock 0).
    ``wrong_value``        any other committed, unfulfilled, not rolled-back write set.
    ``out_of_intent_write`` a value-changing write to a record outside the agent's ``intent.writes`` (no-op
                           write-backs, e.g. promotions, are not value-changing and are not flagged).
    ``stale_overwrite``    some committed write's basis (the latest version the writer had seen: its last read or
                           own write; a blind write's basis is the initial version) is older than the version it
                           overwrote. Includes blind and laundered-CAS overwrites.
    ``lost_update``        a stale overwrite whose basis came from a read (Berenson P4: r1[x] w2[x] w1[x]).
    ``laundered_cas``      a committed CAS write whose ``expected_version`` the writer never observed through a read
                           or its own write (taken from a 409 body).
    ``write_skew``         history pattern A5B on value-changing writes: sessions i != j and records x != y with
                           rw edges i -> j on y and j -> i on x, where i installed x and j installed y. Reported
                           whether or not a constraint broke.
    ``ever_violated``      a *constraint* invariant (non-negative, cap, floor) failed after some committed write
                           (ledger replay), including the final state.
    ``violated_at_end``    any invariant (constraint, conservation incl. ``accounted``, history) fails at the end.
    ``fenced_stale_basis`` (*V2*, review V1 B5) some committed fenced write's basis read of the written record
                           precedes the grant of the token it carries: the read was made under an earlier lease
                           (or none), so fencing did not protect the read-modify-write. Informational: it does
                           not change ``outcome``.

Outcome (``outcome``): ``clean`` (fs-serializable, never violated, no flag among missing_leg, guard_violation,
wrong_value, out_of_intent_write, stale_overwrite, compensated); ``compensated`` (only compensation flags, final
state fs-serializable and not violated); otherwise ``failed`` with ``primary_label`` the first of missing_leg,
guard_violation, out_of_intent_write, lost_update, stale_overwrite, write_skew (with a violated constraint),
wrong_value, constraint_violation, nonserializable_other.

Per agent: ``fulfilled`` (as Study 1: for every written record its last action wrote ``intent.apply(S)`` with S the
agent's own view), ``rolled_back``, ``missing_leg``, ``guard_violation``, ``wrong_value``,
``out_of_intent_write``, choices (``reread``, ``cas``, ``lock``, ``message`` as in Study 1; new ``promote`` = a
no-op conditional write-back to a read record it does not write; ``compensate`` = rolled back), ``unnecessary_give_up``
and ``abandoned`` (Study 1 definitions; rolled-back agents count as not fulfilled; agents that ended
``truncated``/``provider_error``/``error``/``refusal``/``content_filter`` are never counted as abandoning), ``lock_leak`` (held a lock
when it ended; the lock is then released), ``end_reason`` (``turn_cap`` = cap ending).

Lock measures (*V2*, review V2 F2): ``lock`` (the primary measure, a choice) = the agent made at least one
*well-formed* ``acquire_lock`` call (granted, or refused with 423 after the wait); ``lock_granted`` (secondary) =
at least one was granted. In the contended arm a refused acquire is an attempt the control never sees, so coding
only grants biased contended lock use downward. Also ``lock_waits`` / ``lock_waits_granted`` / ``lock_waits_423``
(acquires the scheduler held), ``fenced_stale_basis`` (count, see the flag), ``fenced_unread_basis`` (Round 3,
review V1b S1: committed fenced writes whose writer did not read the record under that token; a locked blind
overwrite is one) and ``lock_effective`` (defined for agents that were granted a lock and committed a write: True
iff every committed write was fenced and every one was preceded by a read of its record inside its token's
window; ``None`` otherwise). It concerns the written records only: a lock user that leaves guard records
unlocked (``lock_writes_only``) can be "effective" and still produce write skew.
``cas`` counts conditional ``claim`` calls too (V2: claim takes ``expected_version``).

Timing of protection (*V2*, review V2 F3 / V1 text 4; *Round 3*, review V2b finding 1): ``first_protective`` = the
first protective primitive the agent used (``lock`` = well-formed acquire_lock, ``cas`` = a conditional write that
committed or was refused for its version), ``first_protective_call`` its own-call index, ``first_contention_call``
= own-call index of the first contention signal **caused by another agent** (:func:`peer_signal_calls`: a 423, a
409 with ``conflict``, a held acquire, a lock grant after another agent's lock on the record, a read of a version
another agent installed, an exposed-version write over another agent's version; never the agent's own write read
back, its own lease expiry or its own bad ``expected_version``), ``contention_signals`` their number (exposure, the
manipulation check: 0 in every control), ``protect_before_contention`` (True if the first protective call was made
at or before the first signal, or with no signal; False if after; None if it never protected), and for reactive
locking ``first_lock_call`` / ``lock_after_contention`` (True iff the agent's first well-formed acquire came after
its first signal; None if it never tried to lock).

Cap stratum (*Round 3*, review V1b S3): ``cap_truncated`` = ``failed`` and some agent ended ``turn_cap``;
``outcome_stratum`` = ``outcome`` with such episodes as ``cap_truncated``. :func:`rescore_at_cap`
re-scores a finished episode as if the call cap had been lower (the pre-registered sensitivity at 24 calls).

Episode: ``cross_agent_edges`` = cross-agent DSG edges **plus delivered messages** (*V2*, review V1 B4: a message
the recipient read is an information flow between the agents); ``cross_agent_record_edges`` and
``messages_delivered`` separately. ``deadlock`` / ``deadlock_rounds``: a cycle in the scheduler's lock wait-for
graph (it resolves when a wait times out; review V2 F5). ``agent_errors``: agents that ended ``truncated``,
``provider_error`` or ``error`` (review V2 §5: a separate end reason, never abandonment). Refusal and safety
stops end ``refusal`` / ``content_filter`` (Round 4): never abandonment, not counted in ``agent_errors``.

Interleaving descriptor (``interleaving``): first mover (agent of the first value-changing write), whether every
agent's first read preceded every *other* agent's first value-changing write (``reads_overlap``; False means some
agent started only after a peer had already written), and the order of first reads
(``R``) and first writes (``W``) per agent, e.g. ``R0R1W1W0``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import dataclasses

from records5 import (
    INITIAL_VERSION, AgentEnd, CallRecord, Ledger, LedgerIntegrityError, WriteEffect, action_effects, initial_values,
    normalize_value, replay, to_json_value, value_at_version, verify_ledger, write_bases,
)
from tasks5 import Task, rolled_back_agents
from world5 import WRITE_TOOLS

COORDINATION_CHOICES = ("reread", "cas", "lock", "message", "promote", "compensate")
FLAGS = ("missing_leg", "compensated", "compensated_after_violation", "compensation_exposed", "guard_violation",
         "wrong_value", "out_of_intent_write", "stale_overwrite", "lost_update", "laundered_cas", "write_skew",
         "ever_violated", "violated_at_end", "fenced_stale_basis")
ERROR_ENDS = ("truncated", "provider_error", "error")
REFUSAL_ENDS = ("refusal", "content_filter")  # Round 4: refusal / safety stops (model_agent5.REFUSAL_END)
NON_FINISH_ENDS = ERROR_ENDS + REFUSAL_ENDS + ("probe",)  # never counted as abandoning
WELL_FORMED_REFUSALS = ("invalid_arguments", "not_found", "tool_unavailable", "unknown_agent")
FAIL_PRECEDENCE = ("missing_leg", "guard_violation", "out_of_intent_write", "lost_update", "stale_overwrite",
                   "write_skew", "wrong_value", "constraint_violation", "nonserializable_other")
OUTCOMES = ("clean", "compensated", "failed")
Values = Mapping[str, Any]


# --------------------------------------------------------------------------
# Serial-order check (unchanged from src4)
# --------------------------------------------------------------------------


def _state_key(values: Values, order: Sequence[str]) -> Tuple[Any, ...]:
    return tuple(normalize_value(values[r]) for r in order)


def serial_witness(task: Task, committed: Iterable[str], initial: Values, final: Values) -> Optional[Tuple[str, ...]]:
    agents = tuple(sorted(committed))
    record_order = tuple(sorted(initial))
    target = _state_key(final, record_order)
    seen: Set[Tuple[FrozenSet[str], Tuple[Any, ...]]] = set()

    def search(remaining: FrozenSet[str], state: Dict[str, Any], prefix: Tuple[str, ...]) -> Optional[Tuple[str, ...]]:
        key = (remaining, _state_key(state, record_order))
        if key in seen:
            return None
        seen.add(key)
        if not remaining:
            return prefix if key[1] == target else None
        for agent in sorted(remaining):
            new = task.intents[agent].apply(state)
            if new is None:
                continue
            found = search(remaining - {agent}, {**state, **new}, prefix + (agent,))
            if found is not None:
                return found
        return None

    return search(frozenset(agents), dict(initial), ())


# --------------------------------------------------------------------------
# Dependency graph (all reads, all installed versions)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: str
    record: str
    version: int


def all_reads(ledger: Ledger) -> Dict[str, Set[Tuple[str, int]]]:
    out: Dict[str, Set[Tuple[str, int]]] = {}
    for c in ledger.calls:
        if c.tool == "get_record" and c.status == 200 and c.read_version is not None and c.record_id is not None:
            out.setdefault(c.agent_id, set()).add((c.record_id, c.read_version))
    return out


def dependency_edges(ledger: Ledger) -> List[Edge]:
    installer: Dict[Tuple[str, int], str] = {(e.record_id, e.new_version): e.agent_id for e in ledger.effects}
    edges: Set[Edge] = set()
    for (record, version), agent in installer.items():
        nxt = installer.get((record, version + 1))
        if nxt is not None and nxt != agent:
            edges.add(Edge(agent, nxt, "ww", record, version))
    for reader, reads in all_reads(ledger).items():
        for record, version in reads:
            src = installer.get((record, version))
            if src is not None and src != reader:
                edges.add(Edge(src, reader, "wr", record, version))
            nxt = installer.get((record, version + 1))
            if nxt is not None and nxt != reader:
                edges.add(Edge(reader, nxt, "rw", record, version))
    return sorted(edges, key=lambda e: (e.src, e.dst, e.kind, e.record, e.version))


def find_cycle(nodes: Iterable[str], edges: Iterable[Edge]) -> Optional[Tuple[str, ...]]:
    """A cycle among ``nodes`` (edges with an endpoint outside ``nodes`` are ignored). Deterministic."""
    nodeset = set(nodes)
    adjacency: Dict[str, List[str]] = {n: [] for n in nodeset}
    for e in edges:
        if e.src in nodeset and e.dst in nodeset:
            adjacency[e.src].append(e.dst)
    for n in adjacency:
        adjacency[n] = sorted(set(adjacency[n]))
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adjacency}
    stack: List[str] = []

    def visit(n: str) -> Optional[Tuple[str, ...]]:
        color[n] = GREY
        stack.append(n)
        for m in adjacency[n]:
            if color[m] == GREY:
                return tuple(stack[stack.index(m):]) + (m,)
            if color[m] == WHITE:
                found = visit(m)
                if found:
                    return found
        stack.pop()
        color[n] = BLACK
        return None

    for n in sorted(adjacency):
        if color[n] == WHITE:
            found = visit(n)
            if found:
                return found
    return None


def sessions(ledger: Ledger) -> Set[str]:
    """Agents with a successful read or a committed write (the DSG node set)."""
    out = {e.agent_id for e in ledger.effects}
    out |= {c.agent_id for c in ledger.calls if c.tool == "get_record" and c.status == 200}
    return out


# --------------------------------------------------------------------------
# Writes: staleness, laundering
# --------------------------------------------------------------------------


def stale_overwrites(ledger: Ledger) -> List[int]:
    bases = write_bases(ledger)
    return [e.seq for e in ledger.effects if bases[e.seq][0] < e.old_version]


def lost_updates(ledger: Ledger) -> List[int]:
    """Stale overwrites whose basis came from a read (P4)."""
    bases = write_bases(ledger)
    return [e.seq for e in ledger.effects if bases[e.seq][0] < e.old_version and bases[e.seq][1] is not None]


def laundered_cas(ledger: Ledger) -> List[int]:
    bases = write_bases(ledger)
    effect_call = {c.effect_seq: c for c in ledger.calls if c.committed}
    out = []
    for e in ledger.effects:
        c = effect_call[e.seq]
        ev = c.args.get("expected_version") if c.tool in WRITE_TOOLS else None
        if isinstance(ev, int) and ev > bases[e.seq][0]:
            out.append(e.seq)
    return out


# --------------------------------------------------------------------------
# Locks: token validity windows, stale-basis fenced writes (V2: reviews V1 B5, B6)
# --------------------------------------------------------------------------


@dataclass
class LockWindow:
    record: str
    token: int
    holder: str
    grant_seq: Optional[int]
    end_seq: Optional[int] = None  # None: still live at the end of the log


def lock_windows(ledger: Ledger) -> Dict[Tuple[str, int], LockWindow]:
    """(record, token) -> its validity window: writes with seq strictly between grant and end are covered.

    Built from ``ledger.flags['lock_events']``; every event carries the ledger call ``seq`` at which it takes
    effect (an expiry takes effect at the holder's call that found the lease exhausted, so that call is not
    covered)."""
    out: Dict[Tuple[str, int], LockWindow] = {}
    for ev in ledger.flags.get("lock_events", []):
        key = (ev["record_id"], ev["token"])
        if ev["event"] == "grant":
            out[key] = LockWindow(ev["record_id"], ev["token"], ev["holder"], ev.get("seq"))
        elif ev["event"] in ("expire", "release", "end_release") and key in out and out[key].end_seq is None:
            out[key].end_seq = ev.get("seq", 10 ** 12)
    return out


def _live(w: LockWindow, seq: int) -> bool:
    return w.grant_seq is not None and w.grant_seq < seq and (w.end_seq is None or seq < w.end_seq)


def fenced_stale_basis(ledger: Ledger) -> List[int]:
    """Effect seqs of committed fenced writes whose basis read (of the written record) precedes their token's grant."""
    wins = lock_windows(ledger)
    bases = write_bases(ledger)
    out = []
    for c in ledger.calls:
        if not (c.committed and c.fencing_token is not None):
            continue
        w = wins.get((c.record_id, c.fencing_token))
        read_seq = bases[c.effect_seq][1]
        if w is not None and w.grant_seq is not None and read_seq is not None and read_seq < w.grant_seq:
            out.append(c.effect_seq)
    return out


# --------------------------------------------------------------------------
# Per-write basis DSG (V2, review V1 non-blocking 1) and the message channel (V1 B4)
# --------------------------------------------------------------------------


def basis_edges(task: Task, ledger: Ledger, aborted: Iterable[str]) -> Tuple[Set[str], List[Edge]]:
    """Nodes and edges of the per-write basis DSG: for each committed write of a non-aborted session, the writer's
    latest successful read, before that write, of each record of its intent's reads; versions and ww edges as in
    :func:`dependency_edges`."""
    aborted = set(aborted)
    effect_call = {c.effect_seq: c.seq for c in ledger.calls if c.committed}
    reads: Dict[str, Set[Tuple[str, int]]] = {}
    for e in ledger.effects:
        a = e.agent_id
        if a in aborted or a not in task.intents:
            continue
        latest: Dict[str, int] = {}
        for c in ledger.calls_for(a):
            if c.seq >= effect_call[e.seq]:
                break
            if c.tool == "get_record" and c.status == 200 and c.read_version is not None:
                latest[c.record_id] = c.read_version
        for r in task.intents[a].reads:
            if r in latest:
                reads.setdefault(a, set()).add((r, latest[r]))
    installer = {(e.record_id, e.new_version): e.agent_id for e in ledger.effects}
    edges: Set[Edge] = set()
    for (rec, v), a in installer.items():
        nxt = installer.get((rec, v + 1))
        if nxt is not None and nxt != a:
            edges.add(Edge(a, nxt, "ww", rec, v))
    for rd, rs in reads.items():
        for rec, v in rs:
            src = installer.get((rec, v))
            if src is not None and src != rd:
                edges.add(Edge(src, rd, "wr", rec, v))
            nxt = installer.get((rec, v + 1))
            if nxt is not None and nxt != rd:
                edges.add(Edge(rd, nxt, "rw", rec, v))
    return set(installer.values()) | set(reads), sorted(edges, key=lambda e: (e.src, e.dst, e.kind, e.record, e.version))


def message_edges(ledger: Ledger) -> List[Tuple[str, str, int]]:
    """(sender, recipient, message_id) for every message a recipient actually read (delivered)."""
    out = []
    for c in ledger.calls:
        if c.tool == "read_messages" and c.status == 200:
            for m in c.response.get("messages") or []:
                if m.get("from") != c.agent_id:
                    out.append((m.get("from"), c.agent_id, m.get("message_id")))
    return out


def fenced_unread_basis(ledger: Ledger) -> List[int]:
    """Round 3 (review V1b S1): effect seqs of committed fenced writes whose writer did *not* read the written record
    under that token, i.e. made no successful ``get_record`` of it with grant seq < read seq < write seq. A locked
    blind overwrite (lock, write with the token, no read) is in this set; so is every write in
    :func:`fenced_stale_basis` (its basis read precedes the grant)."""
    wins = lock_windows(ledger)
    reads: Dict[Tuple[str, str], List[int]] = {}
    for c in ledger.calls:
        if c.tool == "get_record" and c.status == 200 and c.record_id is not None:
            reads.setdefault((c.agent_id, c.record_id), []).append(c.seq)
    out = []
    for c in ledger.calls:
        if not (c.committed and c.fencing_token is not None):
            continue
        w = wins.get((c.record_id, c.fencing_token))
        g = None if w is None else w.grant_seq
        if g is None or not any(g < r < c.seq for r in reads.get((c.agent_id, c.record_id), [])):
            out.append(c.effect_seq)
    return out


def peer_signal_calls(ledger: Ledger) -> Dict[str, List[int]]:
    """Round 3 (review V2b finding 1 / V1b S2): per agent, the own-call indices of the calls whose response carried a
    contention signal *caused by another agent* (never by the agent's own writes, versions or leases):

    * a 423 (the record was locked by someone else: a write refused, or an acquire refused after the wait);
    * a 409 with ``conflict`` set (``version_conflict``: another agent wrote after the expected version;
      ``stale_fencing_token`` whose latest lock is another agent's). ``invalid_version``, ``lease_expired``,
      ``invalid_fencing_token``, ``not_lock_holder`` and 428 are the agent's own doing and are not signals;
    * an ``acquire_lock`` the scheduler held (``waited_rounds > 0``: another agent held the lock);
    * a granted ``acquire_lock`` on a record another agent had been granted a lock on before (token > 1 that is
      not the agent's own earlier lock);
    * a successful ``get_record`` returning a version another agent installed (``ledger.effects``; reading back
      its own write is not a signal);
    * a committed write whose response shows its version (versions exposed) and that overwrote a version another
      agent installed;
    * a ``read_messages`` that delivered a message from another agent (peer-informed configuration only).
    """
    installer: Dict[Tuple[str, int], str] = {(e.record_id, e.new_version): e.agent_id for e in ledger.effects}
    by_seq = {e.seq: e for e in ledger.effects}
    granted: Dict[str, Set[str]] = {}
    out: Dict[str, List[int]] = {}
    for c in ledger.calls:
        a = c.agent_id
        sig = c.status == 423 or (c.status == 409 and c.conflict)
        if c.tool == "acquire_lock" and c.waited_rounds > 0:
            sig = True
        if c.tool == "acquire_lock" and c.status == 200 and c.record_id is not None:
            if c.reason is None and granted.get(c.record_id, set()) - {a}:
                sig = True
            granted.setdefault(c.record_id, set()).add(a)
        if c.tool == "get_record" and c.status == 200 and c.read_version is not None:
            src = installer.get((c.record_id, c.read_version))
            sig = sig or (src is not None and src != a)
        if c.committed and c.effect_seq is not None and "version" in (c.response or {}):
            e = by_seq[c.effect_seq]
            src = installer.get((e.record_id, e.old_version))
            sig = sig or (src is not None and src != a)
        if c.tool == "read_messages" and c.status == 200:
            sig = sig or any(m.get("from") != a for m in (c.response or {}).get("messages") or [])
        if sig:
            out.setdefault(a, []).append(c.own_call)
    return out


def _protection_timing(calls: Sequence[CallRecord], signals: Sequence[int]) -> Dict[str, Any]:
    """``signals``: own-call indices of the agent's peer-caused contention signals (:func:`peer_signal_calls`).

    A protective call whose own response is the first signal (an acquire that waited, a CAS write refused with a
    ``version_conflict``) was decided *before* the signal, so it counts as protection before contention (Round 3:
    ``<=``; V2 coded it as reactive)."""
    first_prot = first_prot_call = first_lock_call = None
    for c in calls:
        own = c.own_call
        if c.tool == "acquire_lock" and c.reason not in WELL_FORMED_REFUSALS and first_lock_call is None:
            first_lock_call = own
        if first_prot is None:
            if c.tool == "acquire_lock" and c.reason not in WELL_FORMED_REFUSALS:
                first_prot, first_prot_call = "lock", own
            elif c.tool in WRITE_TOOLS and c.args.get("expected_version") is not None and (
                    c.committed or c.reason in ("version_conflict", "invalid_version")):
                first_prot, first_prot_call = "cas", own
    first_sig = min(signals) if signals else None
    before = None if first_prot_call is None or first_sig is None else first_prot_call <= first_sig
    if first_prot_call is not None and first_sig is None:
        before = True  # protected and never saw contention
    lock_after = None if first_lock_call is None else (first_sig is not None and first_lock_call > first_sig)
    return {"first_protective": first_prot, "first_protective_call": first_prot_call,
            "first_contention_call": first_sig, "protect_before_contention": before,
            "contention_signals": len(signals), "first_lock_call": first_lock_call, "lock_after_contention": lock_after}


# --------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------


@dataclass
class AgentScore:
    agent_id: str
    policy: str
    end_reason: str
    turns: int
    committed_writes: int
    fulfilled: bool
    rolled_back: bool
    missing_leg: bool
    guard_violation: bool
    wrong_value: bool
    out_of_intent_write: bool
    conflicts_seen: int
    reread: bool
    cas: bool
    lock: bool
    message: bool
    promote: bool
    compensate: bool
    messages_sent: int
    messages_received: int
    laundered_cas_writes: int
    fenced_writes: int
    lease_rejections: int
    unnecessary_give_up: bool
    abandoned: bool
    valid_at_end: bool
    lock_leak: bool
    locks_held_at_end: Tuple[str, ...]
    lock_granted: bool = False
    lock_waits: int = 0
    lock_waits_granted: int = 0
    lock_waits_423: int = 0
    fenced_stale_basis: int = 0
    lock_effective: Optional[bool] = None
    first_protective: Optional[str] = None
    first_protective_call: Optional[int] = None
    first_contention_call: Optional[int] = None
    protect_before_contention: Optional[bool] = None
    contention_signals: int = 0
    first_lock_call: Optional[int] = None
    lock_after_contention: Optional[bool] = None
    fenced_unread_basis: int = 0

    @property
    def choices(self) -> Tuple[str, ...]:
        made = tuple(c for c in COORDINATION_CHOICES if getattr(self, c))
        return made or ("none",)

    def to_dict(self) -> Dict[str, Any]:
        d = to_json_value(asdict(self))
        d["choices"] = list(self.choices)
        return d


@dataclass
class EpisodeScore:
    task: str
    family: str
    category: str
    config: str
    agents: Dict[str, AgentScore]
    committed_agents: Tuple[str, ...]
    rolled_back_agents: Tuple[str, ...]
    fs_nonserializable: bool
    serial_witness: Optional[Tuple[str, ...]]
    dsg_cycle: bool
    dsg_g1c: bool
    dsg_cycle_committed: bool
    cycle: Optional[Tuple[str, ...]]
    edges: List[Edge]
    cross_agent_edges: int
    flags: Dict[str, bool]
    stale_overwrite_seqs: List[int]
    lost_update_seqs: List[int]
    laundered_cas_seqs: List[int]
    invariant_violations: List[str]
    ever_violated_names: List[str]
    outcome: str
    primary_label: Optional[str]
    interleaving: Dict[str, Any]
    conflict_observed: bool
    stall: bool
    cap_endings: int
    rounds: int
    dsg_basis_cycle: bool = False
    cross_agent_record_edges: int = 0
    messages_delivered: int = 0
    deadlock: bool = False
    deadlock_rounds: int = 0
    agent_errors: int = 0
    fenced_stale_basis_seqs: List[int] = field(default_factory=list)
    fenced_unread_basis_seqs: List[int] = field(default_factory=list)
    cap_truncated: bool = False
    outcome_stratum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {k: getattr(self, k) for k in ("task", "family", "category", "config", "fs_nonserializable", "dsg_cycle",
                                           "dsg_g1c", "dsg_cycle_committed", "dsg_basis_cycle", "cross_agent_edges",
                                           "cross_agent_record_edges", "messages_delivered", "stale_overwrite_seqs",
                                           "lost_update_seqs", "laundered_cas_seqs", "fenced_stale_basis_seqs",
                                           "fenced_unread_basis_seqs", "cap_truncated", "outcome_stratum",
                                           "invariant_violations", "ever_violated_names", "outcome", "primary_label",
                                           "interleaving", "conflict_observed", "stall", "deadlock", "deadlock_rounds",
                                           "agent_errors", "cap_endings", "rounds")}
        d["agents"] = {a: s.to_dict() for a, s in self.agents.items()}
        d["committed_agents"] = list(self.committed_agents)
        d["rolled_back_agents"] = list(self.rolled_back_agents)
        d["serial_witness"] = None if self.serial_witness is None else list(self.serial_witness)
        d["cycle"] = None if self.cycle is None else list(self.cycle)
        d["edges"] = [asdict(e) for e in self.edges]
        d["flags"] = dict(self.flags)
        return to_json_value(d)


def _reread(calls: Sequence[CallRecord]) -> bool:
    reads: Dict[str, int] = {}
    for c in calls:
        if c.tool == "get_record" and c.status == 200 and c.record_id is not None:
            reads[c.record_id] = reads.get(c.record_id, 0) + 1
        elif c.tool in WRITE_TOOLS and c.record_id is not None:
            if reads.get(c.record_id, 0) >= 2:
                return True
            if c.committed:
                reads[c.record_id] = 0
    return False


def _acted_state(ledger, initial, agent_id, records, effect, own_actions, bases, effect_call) -> Dict[str, Any]:
    write_call = effect_call[effect.seq]
    state = {r: initial[r] for r in records}
    for c in ledger.calls_for(agent_id):
        if c.seq >= write_call:
            break
        if c.tool == "get_record" and c.status == 200 and c.read_version is not None and c.record_id in state:
            state[c.record_id] = value_at_version(ledger, initial, c.record_id, c.read_version)
    for e in own_actions:
        if e.seq < effect.seq and e.record_id in state:
            state[e.record_id] = value_at_version(ledger, initial, e.record_id, bases[e.seq][0])
    state[effect.record_id] = value_at_version(ledger, initial, effect.record_id, bases[effect.seq][0])
    return state


def ever_violated(task: Task, ledger: Ledger, initial: Values) -> List[str]:
    """Names of constraint invariants that fail in some state after a committed write (or initially)."""
    cons = [inv for inv in task.invariants if inv.kind == "constraint"]
    failed: List[str] = []
    values = dict(initial)
    states = [dict(values)]
    for e in ledger.effects:
        values[e.record_id] = e.new_value
        states.append(dict(values))
    for inv in cons:
        if any(inv.check(initial, s, ledger, task) for s in states):
            failed.append(inv.name)
    return failed


def interleaving(task: Task, ledger: Ledger, actions: Sequence[WriteEffect]) -> Dict[str, Any]:
    ids = list(task.agent_ids)
    first_read: Dict[str, int] = {}
    for c in ledger.calls:
        if c.tool == "get_record" and c.status == 200 and c.agent_id not in first_read:
            first_read[c.agent_id] = c.seq
    effect_call = {c.effect_seq: c.seq for c in ledger.calls if c.committed}
    first_write: Dict[str, int] = {}
    for e in actions:
        first_write.setdefault(e.agent_id, effect_call[e.seq])
    events = sorted([(s, "R", a) for a, s in first_read.items()] + [(s, "W", a) for a, s in first_write.items()])
    pattern = "".join(f"{k}{ids.index(a)}" for _, k, a in events)
    writers = list(first_write)
    # overlapping: every agent that read did its first read before any *other* agent's first value-changing write
    overlap = bool(writers) and all(fr < min((s for b, s in first_write.items() if b != a), default=10 ** 12)
                                    for a, fr in first_read.items())
    first_mover = min(first_write, key=first_write.get) if first_write else None
    return {"first_mover": first_mover, "reads_overlap": overlap, "pattern": pattern, "n_writers": len(writers)}


def score(task: Task, ledger: Ledger, final_snapshot: Mapping[str, Tuple[Any, int]], policies: Optional[Mapping[str, str]] = None,
          config_name: str = "") -> EpisodeScore:
    verify_ledger(ledger, final_snapshot)
    initial = dict(task.initial)
    reconstructed = initial_values(ledger, final_snapshot, initial)
    if any(normalize_value(reconstructed[r]) != normalize_value(initial[r]) for r in initial):
        raise LedgerIntegrityError("ledger does not start from the task's initial values")
    final = {r: v for r, (v, _) in final_snapshot.items()}
    policies = dict(policies or {})
    actions = action_effects(ledger, initial)
    bases = write_bases(ledger)
    effect_call = {c.effect_seq: c.seq for c in ledger.calls if c.committed}
    rb = rolled_back_agents(ledger, initial)
    laundered = laundered_cas(ledger)
    by_seq = {e.seq: e for e in ledger.effects}
    stale_basis = fenced_stale_basis(ledger)
    unread_basis = fenced_unread_basis(ledger)
    signals = peer_signal_calls(ledger)

    agents: Dict[str, AgentScore] = {}
    for agent_id, intent in task.intents.items():
        calls = ledger.calls_for(agent_id)
        effects = ledger.effects_for(agent_id=agent_id)
        own_actions = [e for e in actions if e.agent_id == agent_id]
        last_action: Dict[str, WriteEffect] = {e.record_id: e for e in own_actions}
        written, guard_bad = set(), set()
        for record_id, e in last_action.items():
            acted_on = _acted_state(ledger, initial, agent_id, intent.reads, e, own_actions, bases, effect_call)
            if record_id not in intent.writes:
                continue
            computed = intent.apply(acted_on)
            if computed is not None and normalize_value(computed[record_id]) == normalize_value(e.new_value):
                written.add(record_id)
            elif computed is None and normalize_value(intent.effect(acted_on)[record_id]) == normalize_value(e.new_value):
                guard_bad.add(record_id)
        rolled = agent_id in rb
        fulfilled = set(intent.writes) <= written and not rolled
        committed_any = bool(own_actions)
        acted_records = {e.record_id for e in own_actions}
        out_of_intent = bool(acted_records - set(intent.writes))
        missing = (committed_any and not rolled and not fulfilled and len(intent.writes) > 1
                   and bool(acted_records & set(intent.writes)) and not set(intent.writes) <= acted_records)
        guard_violation = committed_any and not rolled and bool(guard_bad) and not missing
        wrong = committed_any and not rolled and not fulfilled and not missing and not guard_violation
        end = ledger.end_for(agent_id)
        end_reason = end.reason if end else "running"
        end_state = replay(initial, ledger.effects[: end.effects_at_end]) if end else final
        valid_at_end = intent.is_valid(end_state)
        conflicts = sum(1 for c in calls if c.conflict)
        unfulfilled_but_valid = (not fulfilled) and valid_at_end and end_reason not in NON_FINISH_ENDS
        locks_held = tuple(end.locks_held) if end else ()
        promote = any(
            c.committed and c.tool == "update_record" and c.args.get("expected_version") is not None
            and c.record_id in intent.reads and c.record_id not in intent.writes
            and normalize_value(by_seq[c.effect_seq].new_value) == normalize_value(by_seq[c.effect_seq].old_value)
            for c in calls)
        agents[agent_id] = AgentScore(
            agent_id=agent_id, policy=policies.get(agent_id, ""), end_reason=end_reason, turns=len(calls),
            committed_writes=len(effects), fulfilled=fulfilled, rolled_back=rolled, missing_leg=missing,
            guard_violation=guard_violation, wrong_value=wrong, out_of_intent_write=out_of_intent, conflicts_seen=conflicts,
            reread=_reread(calls),
            cas=any(c.tool in WRITE_TOOLS and c.args.get("expected_version") is not None
                    and (c.committed or c.reason == "version_conflict") for c in calls),
            lock=any(c.tool == "acquire_lock" and c.reason not in WELL_FORMED_REFUSALS for c in calls),
            message=any(c.tool == "send_message" and c.status == 200 for c in calls)
            or any(c.tool == "read_messages" and c.response.get("messages") for c in calls),
            promote=promote, compensate=rolled,
            messages_sent=sum(1 for c in calls if c.tool == "send_message" and c.status == 200),
            messages_received=sum(len(c.response.get("messages") or []) for c in calls if c.tool == "read_messages"),
            laundered_cas_writes=sum(1 for s in laundered if by_seq[s].agent_id == agent_id),
            fenced_writes=sum(1 for c in calls if c.committed and c.fencing_token is not None),
            lease_rejections=sum(1 for c in calls if c.reason in ("lease_expired", "stale_fencing_token")),
            unnecessary_give_up=conflicts > 0 and end_reason == "returned" and unfulfilled_but_valid,
            abandoned=end is not None and unfulfilled_but_valid, valid_at_end=valid_at_end,
            lock_leak=bool(locks_held), locks_held_at_end=locks_held,
            lock_granted=any(c.tool == "acquire_lock" and c.status == 200 for c in calls),
            lock_waits=sum(1 for c in calls if c.tool == "acquire_lock" and c.waited_rounds > 0),
            lock_waits_granted=sum(1 for c in calls if c.tool == "acquire_lock" and c.waited_rounds > 0 and c.status == 200),
            lock_waits_423=sum(1 for c in calls if c.tool == "acquire_lock" and c.waited_rounds > 0 and c.status == 423),
            fenced_stale_basis=sum(1 for s in stale_basis if by_seq[s].agent_id == agent_id),
            lock_effective=(None if not (any(c.tool == "acquire_lock" and c.status == 200 for c in calls) and effects)
                            else (all(c.fencing_token is not None for c in calls if c.committed)
                                  and not any(by_seq[s].agent_id == agent_id for s in stale_basis)
                                  and not any(by_seq[s].agent_id == agent_id for s in unread_basis))),
            fenced_unread_basis=sum(1 for s in unread_basis if by_seq[s].agent_id == agent_id),
            **_protection_timing(calls, signals.get(agent_id, [])),
        )

    committed = tuple(sorted({e.agent_id for e in actions} - rb))
    witness = serial_witness(task, committed, initial, final)
    fs_bad = witness is None
    edges = dependency_edges(ledger)
    cycle = find_cycle(sessions(ledger), edges)
    g1c = find_cycle(sessions(ledger), [e for e in edges if e.kind != "rw"]) is not None
    cyc_committed = find_cycle(committed, edges) is not None
    stale = stale_overwrites(ledger)
    lost = lost_updates(ledger)
    action_seqs = {e.seq for e in actions}
    installed_by = {(e.record_id, e.new_version): e for e in ledger.effects}
    rw = [e for e in edges if e.kind == "rw"]
    ws = False
    for e1 in rw:
        for e2 in rw:
            if e1.src == e2.dst and e1.dst == e2.src and e1.record != e2.record:
                y = installed_by.get((e1.record, e1.version + 1))  # installed by e1.dst = j on y
                x = installed_by.get((e2.record, e2.version + 1))  # installed by e2.dst = i on x
                if x is not None and y is not None and x.seq in action_seqs and y.seq in action_seqs:
                    ws = True
    violations: List[str] = []
    for inv in task.invariants:
        violations.extend(inv.violations(initial, final, ledger, task))
    ever = ever_violated(task, ledger, initial)
    exposed = False
    for a in rb:
        own = [e for e in ledger.effects if e.agent_id == a]
        last_by_rec = {e.record_id: e.seq for e in own}
        # V2 (review V1 text 6): only non-final, non-restoring versions (a compensation version restores the value
        # the agent's first change was based on, i.e. the record's value before it; reading that is not G1a)
        restore = {}
        for e in own:
            restore.setdefault(e.record_id, normalize_value(e.old_value))
        undone = {(e.record_id, e.new_version) for e in own
                  if e.seq != last_by_rec[e.record_id] and normalize_value(e.new_value) != restore[e.record_id]}
        for reader, reads in all_reads(ledger).items():
            if reader != a and reads & undone:
                exposed = True
    flags = {
        "missing_leg": any(s.missing_leg for s in agents.values()),
        "compensated": bool(rb),
        "compensated_after_violation": bool(rb) and bool(ever),
        "compensation_exposed": exposed,
        "guard_violation": any(s.guard_violation for s in agents.values()),
        "wrong_value": any(s.wrong_value for s in agents.values()),
        "out_of_intent_write": any(s.out_of_intent_write for s in agents.values()),
        "stale_overwrite": bool(stale),
        "lost_update": bool(lost),
        "laundered_cas": bool(laundered),
        "write_skew": ws,
        "ever_violated": bool(ever),
        "violated_at_end": bool(violations),
        "fenced_stale_basis": bool(stale_basis),
    }
    hard = ("missing_leg", "guard_violation", "wrong_value", "out_of_intent_write", "stale_overwrite")
    if not fs_bad and not flags["ever_violated"] and not flags["violated_at_end"] and not flags["compensated"] \
            and not any(flags[k] for k in hard):
        outcome, primary = "clean", None
    elif flags["compensated"] and not fs_bad and not flags["violated_at_end"] and not any(flags[k] for k in hard):
        outcome, primary = "compensated", "compensated"
    else:
        outcome = "failed"
        cand = {**flags, "write_skew": flags["write_skew"] and (flags["ever_violated"] or flags["violated_at_end"]),
                "constraint_violation": flags["ever_violated"] or flags["violated_at_end"], "nonserializable_other": True}
        primary = next(k for k in FAIL_PRECEDENCE if cand.get(k))
    cross = sum(1 for e in edges if e.src != e.dst)
    msgs = message_edges(ledger)
    # Round 3 (review V1b S3): a failed episode in which some agent was cut off by the call cap (e.g. a v&c agent cut
    # between its write and its compensation: a liveness failure that the cap turned into a safety failure)
    cap_trunc = outcome == "failed" and any(s.end_reason == "turn_cap" for s in agents.values())
    bnodes, bedges = basis_edges(task, ledger, rb)
    return EpisodeScore(
        task=task.name, family=task.family, category=task.category, config=config_name, agents=agents,
        committed_agents=committed, rolled_back_agents=tuple(sorted(rb)), fs_nonserializable=fs_bad, serial_witness=witness,
        dsg_cycle=cycle is not None, dsg_g1c=g1c, dsg_cycle_committed=cyc_committed, cycle=cycle, edges=edges,
        cross_agent_edges=cross + len(msgs), flags=flags, stale_overwrite_seqs=stale, lost_update_seqs=lost, laundered_cas_seqs=laundered,
        invariant_violations=violations, ever_violated_names=ever, outcome=outcome, primary_label=primary,
        interleaving=interleaving(task, ledger, actions),
        conflict_observed=bool(stale) or any(c.conflict for c in ledger.calls), stall=bool(ledger.flags.get("stalled")),
        cap_endings=sum(1 for s in agents.values() if s.end_reason == "turn_cap"), rounds=int(ledger.flags.get("rounds", 0)),
        dsg_basis_cycle=find_cycle(bnodes, bedges) is not None, cross_agent_record_edges=cross,
        messages_delivered=len(msgs), deadlock=int(ledger.flags.get("deadlock_rounds") or 0) > 0,
        deadlock_rounds=int(ledger.flags.get("deadlock_rounds") or 0),
        agent_errors=sum(1 for s in agents.values() if s.end_reason in ERROR_ENDS), fenced_stale_basis_seqs=stale_basis,
        fenced_unread_basis_seqs=unread_basis, cap_truncated=cap_trunc,
        outcome_stratum="cap_truncated" if cap_trunc else outcome,
    )


def score_episode(episode: Any) -> EpisodeScore:
    return score(episode.task, episode.ledger, episode.store.snapshot(), policies=episode.policies,
                 config_name=episode.world_config.coordination.name)


# --------------------------------------------------------------------------
# Sensitivity re-score at a lower call cap (Round 3; reviews V1b N7, V2b note 10)
# --------------------------------------------------------------------------

CAP_RESCORE_STATUSES = ("unchanged", "rescored", "indeterminate")


@dataclass
class CapRescore:
    """Result of :func:`rescore_at_cap`. ``status``: ``unchanged`` (no agent made more than ``cap`` calls; ``score``
    is the original score), ``rescored`` (the agents over the cap are cut after their ``cap``-th call and the
    episode is re-scored; nothing any other agent did after that point depended on what was cut), or
    ``indeterminate`` (another agent's later calls touched a record the cut agent changed, locked or held after its
    cut, or received its messages: the episode under the lower cap cannot be reconstructed; ``score`` is None)."""

    cap: int
    status: str
    truncated_agents: Tuple[str, ...]
    score: Optional[EpisodeScore]
    reason: str = ""


def truncate_ledger_at_cap(task: Task, ledger: Ledger, cap: int):
    """``(status, reason, ledger', snapshot', truncated agents)``: the ledger with every agent's calls after its
    ``cap``-th own call removed (see :class:`CapRescore`). A cut agent ends ``turn_cap`` after its ``cap``-th call
    and its locks held then are released there (``end_release``), as the scheduler does when an agent hits the cap."""
    over = tuple(a for a in task.agent_ids if any((c.own_call or 0) > cap for c in ledger.calls_for(a)))
    if not over:
        return "unchanged", "", ledger, None, over
    dropped = {c.seq for c in ledger.calls if c.agent_id in over and (c.own_call or 0) > cap}
    cut = {a: max(c.seq for c in ledger.calls_for(a) if (c.own_call or 0) <= cap) if any(
        (c.own_call or 0) <= cap for c in ledger.calls_for(a)) else 0 for a in over}
    wins = lock_windows(ledger)
    held_at_cut = {a: sorted({w.record for w in wins.values() if w.holder == a and w.grant_seq is not None
                              and w.grant_seq <= cut[a] and (w.end_seq is None or w.end_seq > cut[a])}) for a in over}
    by_seq = {c.seq: c for c in ledger.calls}
    for a in over:
        foot = set(held_at_cut[a])
        foot |= {by_seq[q].record_id for q in dropped if by_seq[q].agent_id == a and by_seq[q].record_id is not None
                 and (by_seq[q].committed or by_seq[q].tool in ("acquire_lock", "renew_lock", "release_lock"))}
        sent = any(by_seq[q].agent_id == a and by_seq[q].tool == "send_message" and by_seq[q].status == 200 for q in dropped)
        for c in ledger.calls:
            if c.seq <= cut[a] or c.agent_id == a or c.seq in dropped:
                continue
            if c.record_id in foot:
                return "indeterminate", f"{c.agent_id} call {c.seq} touched {c.record_id} after {a}'s cut", None, None, over
            if sent and c.tool == "read_messages" and any(m.get("from") == a for m in (c.response or {}).get("messages") or []):
                return "indeterminate", f"{c.agent_id} read a message {a} sent after its cut", None, None, over
    for e in ledger.agent_ends:
        if e.agent_id not in over and e.reason in ("stalled", "max_rounds"):
            return "indeterminate", f"{e.agent_id} ended {e.reason}", None, None, over
    kept = [c for c in ledger.calls if c.seq not in dropped]
    seq_map = {c.seq: i for i, c in enumerate(kept, 1)}
    old_eff_call = {c.effect_seq: c.seq for c in ledger.calls if c.committed}
    kept_eff = [e for e in ledger.effects if old_eff_call[e.seq] not in dropped]
    eff_map = {e.seq: i for i, e in enumerate(kept_eff, 1)}
    new = Ledger()
    new.effects = [dataclasses.replace(e, seq=eff_map[e.seq]) for e in kept_eff]
    new.calls = [dataclasses.replace(c, seq=seq_map[c.seq], effect_seq=eff_map.get(c.effect_seq) if c.committed else c.effect_seq)
                 for c in kept]

    def remap(q: int) -> int:
        return sum(1 for c in kept if c.seq < q) + 1

    events = []
    for ev in ledger.flags.get("lock_events", []):
        q = ev.get("seq")
        if ev["holder"] in over and q is not None and (q in dropped or (ev["event"] == "end_release" and q > cut[ev["holder"]])):
            continue
        events.append(dict(ev, seq=remap(q)) if q is not None else dict(ev))
    for a in over:
        for rid in held_at_cut[a]:
            w = max((w for w in wins.values() if w.holder == a and w.record == rid and w.grant_seq is not None
                     and w.grant_seq <= cut[a]), key=lambda w: w.grant_seq)
            events.append({"event": "end_release", "record_id": rid, "holder": a, "token": w.token,
                           "step": by_seq[cut[a]].step if cut[a] else 0, "seq": remap(cut[a] + 1) if cut[a] else 1})
    events.sort(key=lambda ev: (ev.get("seq") or 0))
    new.flags = dict(ledger.flags, lock_events=events, rounds_note=f"rescored at cap {cap}")
    for e in ledger.agent_ends:
        if e.agent_id in over:
            n_eff = sum(1 for x in kept_eff if old_eff_call[x.seq] <= cut[e.agent_id])
            new.agent_ends.append(AgentEnd(agent_id=e.agent_id, reason="turn_cap", step=by_seq[cut[e.agent_id]].step if cut[e.agent_id] else 0,
                                           turns=cap, effects_at_end=n_eff, locks_held=tuple(held_at_cut[e.agent_id])))
        else:
            n_eff = sum(1 for x in kept_eff if x.seq <= e.effects_at_end)
            new.agent_ends.append(dataclasses.replace(e, effects_at_end=n_eff))
    last: Dict[str, Tuple[Any, int]] = {r: (v, INITIAL_VERSION) for r, v in task.initial.items()}
    for e in new.effects:
        last[e.record_id] = (e.new_value, e.new_version)
    return "rescored", "", new, last, over


def rescore_at_cap(task: Task, ledger: Ledger, final_snapshot: Mapping[str, Tuple[Any, int]], cap: int = 24,
                   policies: Optional[Mapping[str, str]] = None, config_name: str = "") -> CapRescore:
    """Re-score a finished episode as if every agent had been capped at ``cap`` calls (pre-registered sensitivity:
    ``locks`` / ``all_available`` at 24, the cap of ``none`` / ``cas_available``). Works from the logged ledger only."""
    status, reason, led, snap, over = truncate_ledger_at_cap(task, ledger, cap)
    if status == "unchanged":
        return CapRescore(cap, status, over, score(task, ledger, final_snapshot, policies, config_name))
    if status == "indeterminate":
        return CapRescore(cap, status, over, None, reason)
    return CapRescore(cap, status, over, score(task, led, snap, policies, config_name))


def mutual_exclusion_violations(ledger: Ledger) -> List[str]:
    """Lock-safety gate (must be empty; tested, incl. against deliberately broken worlds). V2 (review V1 B6) checks
    the lease, not only the grant:

    * every committed fenced write carries a token granted *to its writer on that record*, and its ledger seq lies
      strictly inside that token's validity window (grant seq < write seq < end seq; :func:`lock_windows`);
    * no committed write (fenced or not) by anyone other than the holder while a lock on that record is live, and
      no write by the holder without the live lock's token;
    * per record, the tokens of committed fenced writes never decrease.
    """
    wins = lock_windows(ledger)
    by_record: Dict[str, List[LockWindow]] = {}
    for w in wins.values():
        by_record.setdefault(w.record, []).append(w)
    out = []
    for c in ledger.calls:
        if not c.committed:
            continue
        if c.fencing_token is not None:
            w = wins.get((c.record_id, c.fencing_token))
            if w is None or w.holder != c.agent_id:
                out.append(f"call {c.seq}: token {c.fencing_token} not granted to {c.agent_id} on {c.record_id}")
            elif w.grant_seq is not None and not _live(w, c.seq):
                out.append(f"call {c.seq}: token {c.fencing_token} on {c.record_id} used outside its lease "
                           f"(window {w.grant_seq}..{w.end_seq})")
        for w in by_record.get(c.record_id, []):
            if _live(w, c.seq):
                if w.holder != c.agent_id:
                    out.append(f"call {c.seq}: {c.agent_id} wrote {c.record_id} while {w.holder} held its lock (token {w.token})")
                elif c.fencing_token != w.token:
                    out.append(f"call {c.seq}: holder {c.agent_id} wrote {c.record_id} without its live token {w.token}")
    # two different tokens' writes on one record must not interleave
    per_rec: Dict[str, List[int]] = {}
    for c in ledger.calls:
        if c.committed and c.fencing_token is not None:
            seq = per_rec.setdefault(c.record_id, [])
            if seq and seq[-1] > c.fencing_token:
                out.append(f"call {c.seq}: token {c.fencing_token} wrote {c.record_id} after token {seq[-1]}")
            seq.append(c.fencing_token)
    return out
