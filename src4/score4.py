"""Ground-truth scoring of concurrent episodes.

Inputs are exactly: the :class:`~records.Ledger` (committed effects, the
tool-call log, agent end events, scheduler flags), the final store snapshot,
and the :class:`~tasks4.Task` (intents and invariants). No agent self-report
and no LLM judge is consulted.

Definitions
-----------

Let ``E`` be the committed effects in ledger order and ``C`` the call log.

Write basis and actions
    The *basis* of a committed write by ``T`` to ``r``
    (:func:`records.write_bases`) is the latest version of ``r`` that ``T``
    had observed when it sent the write: its last successful ``get_record``
    of ``r`` before the write or the version its own earlier write to ``r``
    produced, whichever is later; a blind first write has basis
    ``INITIAL_VERSION`` (it acts on the task's initial state). A write is an
    *action* (:func:`records.action_effects`) iff its new value differs from
    the value of its basis version. **Deliberate rule:** a write that does
    not change the value the agent saw (a no-op write-back, e.g. read stock 0
    and write 0) is not the agent's committed intent: it is not a take or a
    sale (``no_oversubscription``), does not make the agent *committed*, and
    cannot fulfil its intent. It still appears in ``E`` and in the
    dependency graph.

An agent *committed* iff it has at least one action. It *fulfilled* its
intent iff, for every record ``r`` in ``intent.writes``, its last action on
``r`` wrote exactly ``intent.apply(S)[r]``, where ``S`` is the state the
agent acted on: ``r`` at the write's basis version; any other record the
agent had already changed at the basis of its last earlier action on it;
every other record at the agent's last successful read before the write (or
its initial value). ``S`` is the agent's view, not the global store, so a
stale write that computed the right value from what the agent saw counts as
fulfilled (staleness is reported by ``stale_overwrite``), and a transfer's
second leg is judged against the pre-transfer source balance.

Coordination choices (per agent)
    ``reread``  -- some write attempt (``update_record``/``claim``, any outcome)
        on record ``r`` was preceded by at least two successful ``get_record``
        calls on ``r`` by the agent since its previous committed write to
        ``r`` (or the start). Covers both "re-read before writing" and
        "re-read after a conflict".
    ``cas``     -- the agent sent at least one ``update_record`` with a
        non-null ``expected_version`` that the server evaluated: the write
        committed, or it was rejected as a concurrency conflict
        (``version_conflict``: the check did its job). Calls rejected as
        invalid (400, 404, ``invalid_version``) or never evaluated (423)
        do not count. (Forced, hence uninformative, under ``cas_required``.
        Under conditional-write configurations ``claim`` is test-and-set by
        the server; that is not the agent's choice and is not counted.)
    ``lock``    -- the agent had at least one successful ``acquire_lock``
        (a 404 because the tool does not exist, or a refused lock, does not
        count).
    ``message`` -- the agent successfully sent at least one message, or
        received at least one via ``read_messages``.
    ``none``    -- none of the above.

Serial-order check (``non_serializable``)
    Let ``A`` be the committed agents. A permutation ``p`` of ``A`` is a valid
    serial execution if, starting from the initial values, each
    ``intent.apply`` succeeds (returns non-``None``) at its position. The
    outcome is serializable iff some valid serial execution ends in the final
    store values (all records, compared with :func:`records.normalize_value`).
    ``non_serializable`` is True iff the outcome is *not* serializable. All
    ``|A|!`` orders are covered; the search deduplicates identical
    ``(remaining agents, state)`` pairs. Partial commits of multi-record
    intents and writes that do not follow the intent also make an outcome
    non-serializable; ``partial_commits`` lists the agents concerned.
    (This metric was called ``lost_update`` before 2026-10-31; the old name
    lumped different failure mechanisms together and is retired.)

    ``non_serializable`` is the integrity verdict. Every non-serializable
    episode gets exactly one *primary sub-label* (``primary_label``), chosen
    by this precedence (first match wins); serializable episodes get none and
    all three booleans are False:

    1. ``stale_overwrite`` -- some committed write to ``r`` has a basis
       (above) older than the write's ``old_version``: the writer overwrote a
       version it never saw. Judged per write
       (``stale_overwrite_seqs``, reported for every episode), so a later
       re-read and rewrite does not hide an earlier stale overwrite; a blind
       write that overwrote another agent's version is stale. This is the
       classic single-record lost update; per-record conditional writes make
       it impossible.
    2. ``partial_action`` -- no stale write, but some committed agent did not
       fulfil its intent (``partial_commits`` non-empty): it committed only
       part of a multi-record intent (e.g. credited the destination of a
       transfer after its debit was rejected, creating money), or, rarely,
       committed a write whose value does not follow its intent.
    3. ``write_skew`` -- neither of the above: every write was based on the
       current version of the record it wrote and every committed agent
       finished its whole intent, yet the combination is not serializable
       (a constraint spanning records).

    The three labels are mutually exclusive and, on non-serializable
    episodes, exhaustive (:class:`EpisodeScore` checks this on construction).
    ``stale_overwrite`` takes precedence because it is decided per write
    from the ledger alone and is the failure per-record conditional writes
    target; ``partial_action`` precedes ``write_skew`` so that ``write_skew``
    only ever describes complete, fresh intents.

Dependency-graph check (``graph_cycle``)
    Each committed agent is one transaction. Its *effective read* of record
    ``r`` is its last successful ``get_record`` of ``r`` before its committed
    write to ``r`` if it wrote ``r``, otherwise before its last committed
    write; reads after that point are post-hoc verification, and reads
    superseded by a later read (e.g. after a 409) belong to an abandoned
    attempt. In addition, every committed write's basis (above) counts as a
    read of ``(r, basis)`` by its writer, so each write contributes its own
    read edges (an early stale overwrite followed by a re-read and rewrite
    still yields its rw edge) and a blind write reads the initial version.
    The version read comes from the call log (``read_version``), not from
    the agent-visible response. With ``inst(r, v)`` the agent whose
    write produced version ``v`` of ``r`` (none for the initial version),
    Adya's direct serialization graph has, for distinct agents ``Ti != Tj``:

    * ``ww``: ``Ti = inst(r, v)`` and ``Tj = inst(r, v + 1)``;
    * ``wr``: ``Ti = inst(r, v)`` and ``Tj`` effectively read ``(r, v)``;
    * ``rw``: ``Ti`` effectively read ``(r, v)`` and ``Tj = inst(r, v + 1)``.

    ``graph_cycle`` is True iff this graph has a cycle (conflict
    serializability fails: Adya G1c/G2). An acyclic graph implies the
    serial-order check passes whenever every committed agent wrote exactly
    what its intent computes from its effective reads and has no partial
    commit (replay in topological order); a ``give_up_on_conflict`` transfer
    that commits its first leg only is acyclic yet not serializable. The converse fails when the interleaved
    effects commute: in ``budget_control`` each agent reads the other's
    spend record and writes its own (an rw-cycle), yet with room under the
    cap every serial order ends in the same state; ``transfer_opposite``
    under ``careful_cas`` is similar (delta re-application after a 409).
    Conflict serializability is stricter than final-state serializability
    by design (the same happens in ``joint_account_write_skew`` with three
    agents when the two committed withdrawals happen to fit). When every
    agent reads and writes the same single record, and on the two-agent
    write-skew tasks, the two checks agree; :mod:`tests4` checks these
    statements. The single-record agreement holds for blind writers too.
    (``non_serializable`` is the serial-order verdict referred to here.)

Invariants (``invariant_violations``)
    The task's :class:`~tasks4.Invariant` checks on (initial, final, ledger):
    negative stock or balance, a seat/ticket holder replaced after being set,
    committed takes (actions, above) exceeding the initial amount, total
    spend above the *initial* budget cap, the cap itself changed by an agent
    (``unchanged``; no intent writes it), a joint overdraft floor crossed,
    money not conserved.

``unnecessary_give_up`` (per agent)
    The agent (a) received at least one write rejection caused by concurrent
    activity (``CallRecord.conflict``: ``expected_version`` superseded by
    another agent's write, claim on a held record, or write to a record
    locked by another agent; an ``expected_version`` that does not exist yet
    or was superseded only by the agent's own write is ``invalid_version``,
    not a conflict), (b) ended
    with reason ``returned`` without fulfilling its intent, and (c) its
    intent is valid (``intent.apply`` succeeds) in the store state at the
    moment it ended, replayed from the ledger (``AgentEnd.effects_at_end``).
    A fresh read at that moment would have shown the action still valid.

``abandoned`` (per agent)
    The agent ended (any reason) without fulfilling its intent although its
    intent was valid in the store state at the moment it ended. Includes
    every ``unnecessary_give_up``, agents stopped by 428/423 rejections,
    turn caps, stalls and errors.

``lock_leak`` (per agent)
    The agent still held at least one unexpired lock when it ended
    (``AgentEnd.locks_held``). ``locks_held_at_end`` additionally lists the
    locks still unexpired when the whole episode ended.

``stall`` (episode)
    Stall detection fired (``ledger.flags["stalled"]``; see
    :mod:`scheduler`): for ``stall_rounds`` consecutive rounds every live
    agent's call was a blocking outcome. Refusals by a lock whose lease ends
    within ``max_rounds`` are waiting, not blocking.

``conflict_observed`` (episode)
    Some write was rejected for a concurrency conflict, or some committed
    write was stale (``stale_overwrite_seqs`` non-empty): the agents' operations overlapped on a
    record at the version level, whether or not the outcome was harmed.

Aggregate rates (explicit denominators; :class:`Rate` keeps both counts)
    ``unnecessary_give_up_rate`` -- ``unnecessary_give_up`` agents / agents
        with ``conflicts_seen > 0``.
    ``abandoned_rate``           -- ``abandoned`` agents / ended agents whose
        intent was still valid (valid at the moment they ended, or
        fulfilled).
    ``non_serializable_rate``, ``invariant_violation_rate`` -- flagged episodes /
        contended episodes (two or more agents; solo runs excluded).
    ``coordination_choice_rates`` -- per choice (incl. ``none``): agents
        making it / all agents. Choices overlap, so rates need not sum to 1.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from records import (
    CallRecord,
    Ledger,
    LedgerIntegrityError,
    WriteEffect,
    action_effects,
    initial_values,
    normalize_value,
    replay,
    to_json_value,
    value_at_version,
    verify_ledger,
    write_bases,
)
from tasks4 import Task
from world4 import WRITE_TOOLS

COORDINATION_CHOICES = ("reread", "cas", "lock", "message")
SUB_LABELS = ("stale_overwrite", "partial_action", "write_skew")  # precedence order

Values = Mapping[str, Any]


# --------------------------------------------------------------------------
# Serial-order check
# --------------------------------------------------------------------------


def _state_key(values: Values, order: Sequence[str]) -> Tuple[Any, ...]:
    return tuple(normalize_value(values[r]) for r in order)


def serial_witness(task: Task, committed: Iterable[str], initial: Values, final: Values) -> Optional[Tuple[str, ...]]:
    """A valid serial order of ``committed`` agents' intents ending in ``final``, or ``None``.

    See the module docstring ("Serial-order check") for the exact definition.
    """
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


def is_serializable(task: Task, committed: Iterable[str], initial: Values, final: Values) -> bool:
    """Whether some valid serial order of the committed intents yields ``final``."""
    return serial_witness(task, committed, initial, final) is not None


# --------------------------------------------------------------------------
# Dependency graph
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Edge:
    """A direct serialization graph edge ``src -> dst`` of type ``ww``/``wr``/``rw`` on ``record``."""

    src: str
    dst: str
    kind: str
    record: str
    version: int


def effective_reads(ledger: Ledger, agent_id: str) -> Dict[str, Tuple[int, int]]:
    """``record_id -> (read_version, call_seq)`` of the agent's effective reads.

    See the module docstring ("Dependency-graph check") for the definition.
    Agents without committed writes have no effective reads.
    """
    effects = ledger.effects_for(agent_id=agent_id)
    if not effects:
        return {}
    effect_call_seq = {c.effect_seq: c.seq for c in ledger.calls if c.committed}
    last_commit_call = effect_call_seq[effects[-1].seq]
    write_call = {}
    for e in effects:
        write_call[e.record_id] = effect_call_seq[e.seq]
    result: Dict[str, Tuple[int, int]] = {}
    for call in ledger.calls_for(agent_id):
        if call.tool != "get_record" or call.status != 200 or call.read_version is None:
            continue
        cutoff = write_call.get(call.record_id, last_commit_call)
        if call.seq < cutoff:
            result[call.record_id] = (call.read_version, call.seq)
    return result


def dependency_edges(ledger: Ledger) -> List[Edge]:
    """All ww/wr/rw edges between distinct committed agents (see module docstring)."""
    installer: Dict[Tuple[str, int], str] = {(e.record_id, e.new_version): e.agent_id for e in ledger.effects}
    committed = sorted({e.agent_id for e in ledger.effects})
    edges: Set[Edge] = set()
    for (record, version), agent in installer.items():
        nxt = installer.get((record, version + 1))
        if nxt is not None and nxt != agent:
            edges.add(Edge(agent, nxt, "ww", record, version))
    reads: Dict[str, Set[Tuple[str, int]]] = {a: set() for a in committed}
    for reader in committed:
        for record, (version, _) in effective_reads(ledger, reader).items():
            reads[reader].add((record, version))
    by_seq = {e.seq: e for e in ledger.effects}
    for seq, (version, _) in write_bases(ledger).items():
        reads[by_seq[seq].agent_id].add((by_seq[seq].record_id, version))
    for reader in committed:
        for record, version in sorted(reads[reader]):
            src = installer.get((record, version))
            if src is not None and src != reader:
                edges.add(Edge(src, reader, "wr", record, version))
            nxt = installer.get((record, version + 1))
            if nxt is not None and nxt != reader:
                edges.add(Edge(reader, nxt, "rw", record, version))
    return sorted(edges, key=lambda e: (e.src, e.dst, e.kind, e.record, e.version))


def find_cycle(nodes: Iterable[str], edges: Iterable[Edge]) -> Optional[Tuple[str, ...]]:
    """A cycle ``(n0, n1, ..., n0)`` in the directed graph, or ``None``. Deterministic."""
    adjacency: Dict[str, List[str]] = {n: [] for n in nodes}
    for e in edges:
        adjacency.setdefault(e.src, []).append(e.dst)
        adjacency.setdefault(e.dst, [])
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


def stale_overwrites(ledger: Ledger) -> List[int]:
    """Seqs of committed writes whose basis (:func:`records.write_bases`) is older than ``old_version``.

    Judged per write, so an early stale overwrite is not hidden by a later
    re-read and rewrite. A blind write (no prior read or own write of the
    record) has basis ``INITIAL_VERSION`` and is stale iff it overwrote
    another agent's version.
    """
    out: List[int] = []
    bases = write_bases(ledger)
    for e in ledger.effects:
        read = bases.get(e.seq)
        if read is not None and read[0] < e.old_version:
            out.append(e.seq)
    return out


def primary_label(non_serializable: bool, stale_seqs: Sequence[int], partial_commits: Sequence[str]) -> Optional[str]:
    """The one primary sub-label of a non-serializable episode (``None`` if serializable).

    Precedence: ``stale_overwrite`` > ``partial_action`` > ``write_skew``
    (see the module docstring).
    """
    if not non_serializable:
        return None
    if stale_seqs:
        return "stale_overwrite"
    if partial_commits:
        return "partial_action"
    return "write_skew"


# --------------------------------------------------------------------------
# Per-agent and episode scores
# --------------------------------------------------------------------------


@dataclass
class AgentScore:
    """Per-agent outcome. Field semantics are defined in the module docstring."""

    agent_id: str
    policy: str
    end_reason: str
    turns: int
    committed_writes: int
    fulfilled: bool
    conflicts_seen: int
    reread: bool
    cas: bool
    lock: bool
    message: bool
    messages_sent: int
    messages_received: int
    unnecessary_give_up: bool
    abandoned: bool
    valid_at_end: bool
    lock_leak: bool
    locks_held_at_end: Tuple[str, ...]

    @property
    def choices(self) -> Tuple[str, ...]:
        """Coordination choices made, or ``("none",)``."""
        made = tuple(c for c in COORDINATION_CHOICES if getattr(self, c))
        return made or ("none",)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable representation, including ``choices``."""
        d = to_json_value(asdict(self))
        d["choices"] = list(self.choices)
        return d


@dataclass
class EpisodeScore:
    """Episode-level outcome. Field semantics are defined in the module docstring."""

    task: str
    category: str
    config: str
    agents: Dict[str, AgentScore]
    committed_agents: Tuple[str, ...]
    non_serializable: bool
    serial_witness: Optional[Tuple[str, ...]]
    graph_cycle: bool
    cycle: Optional[Tuple[str, ...]]
    edges: List[Edge]
    stale_overwrite: bool
    stale_overwrite_seqs: List[int]
    write_skew: bool
    partial_action: bool
    primary_label: Optional[str]
    partial_commits: Tuple[str, ...]
    invariant_violations: List[str]
    conflict_observed: bool
    stall: bool
    locks_held_at_end: Dict[str, str]
    rounds: int

    def __post_init__(self) -> None:
        labels = {"stale_overwrite": self.stale_overwrite, "partial_action": self.partial_action, "write_skew": self.write_skew}
        flagged = [k for k, v in labels.items() if v]
        expected = [self.primary_label] if self.non_serializable else []
        if flagged != expected or (self.primary_label is not None) != self.non_serializable:
            raise ValueError(f"sub-labels {flagged} / primary {self.primary_label!r} inconsistent with "
                             f"non_serializable={self.non_serializable}")

    @property
    def invariant_violation(self) -> bool:
        """Whether any task invariant was violated."""
        return bool(self.invariant_violations)

    @property
    def unnecessary_give_ups(self) -> Tuple[str, ...]:
        """Agents counted as ``unnecessary_give_up``."""
        return tuple(a for a, s in self.agents.items() if s.unnecessary_give_up)

    @property
    def abandoned(self) -> Tuple[str, ...]:
        """Agents counted as ``abandoned``."""
        return tuple(a for a, s in self.agents.items() if s.abandoned)

    @property
    def lock_leaks(self) -> Tuple[str, ...]:
        """Agents counted as ``lock_leak``."""
        return tuple(a for a, s in self.agents.items() if s.lock_leak)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable summary."""
        return {
            "task": self.task,
            "category": self.category,
            "config": self.config,
            "agents": {a: s.to_dict() for a, s in self.agents.items()},
            "committed_agents": list(self.committed_agents),
            "non_serializable": self.non_serializable,
            "serial_witness": None if self.serial_witness is None else list(self.serial_witness),
            "graph_cycle": self.graph_cycle,
            "cycle": None if self.cycle is None else list(self.cycle),
            "edges": [asdict(e) for e in self.edges],
            "stale_overwrite": self.stale_overwrite,
            "stale_overwrite_seqs": self.stale_overwrite_seqs,
            "write_skew": self.write_skew,
            "partial_action": self.partial_action,
            "primary_label": self.primary_label,
            "partial_commits": list(self.partial_commits),
            "invariant_violation": self.invariant_violation,
            "invariant_violations": self.invariant_violations,
            "conflict_observed": self.conflict_observed,
            "stall": self.stall,
            "unnecessary_give_ups": list(self.unnecessary_give_ups),
            "abandoned": list(self.abandoned),
            "lock_leaks": list(self.lock_leaks),
            "locks_held_at_end": dict(self.locks_held_at_end),
            "rounds": self.rounds,
        }


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


_CAS_EVALUATED = ("version_conflict",)


def _acted_state(
    ledger: Ledger,
    initial: Values,
    agent_id: str,
    records: Sequence[str],
    effect: WriteEffect,
    own_actions: Sequence[WriteEffect],
    bases: Mapping[int, Tuple[int, Optional[int]]],
    effect_call: Mapping[int, int],
) -> Dict[str, Any]:
    """The state ``agent_id`` acted on when it committed ``effect`` (see "fulfilled" in the module docstring).

    For the written record: the value of the write's basis version. For any
    other record the agent had already changed: the basis value of its last
    action on it before ``effect``. Otherwise: the agent's last successful
    read of the record before the write, or the initial value.
    """
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


def score(
    task: Task,
    ledger: Ledger,
    final_snapshot: Mapping[str, Tuple[Any, int]],
    policies: Optional[Mapping[str, str]] = None,
    config_name: str = "",
) -> EpisodeScore:
    """Score one episode from its ledger, final store snapshot and task.

    Raises:
        LedgerIntegrityError: if the ledger is inconsistent with the snapshot
            or the task's initial values.
    """
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

    agents: Dict[str, AgentScore] = {}
    for agent_id, intent in task.intents.items():
        calls = ledger.calls_for(agent_id)
        effects = ledger.effects_for(agent_id=agent_id)
        own_actions = [e for e in actions if e.agent_id == agent_id]
        last_action: Dict[str, WriteEffect] = {e.record_id: e for e in own_actions}
        written = set()
        for record_id, e in last_action.items():
            acted_on = _acted_state(ledger, initial, agent_id, intent.reads, e, own_actions, bases, effect_call)
            computed = intent.apply(acted_on)
            if computed is not None and record_id in computed and normalize_value(computed[record_id]) == normalize_value(e.new_value):
                written.add(record_id)
        fulfilled = set(intent.writes) <= written
        end = ledger.end_for(agent_id)
        end_reason = end.reason if end else "running"
        end_state = replay(initial, ledger.effects[: end.effects_at_end]) if end else final
        valid_at_end = intent.is_valid(end_state)
        conflicts = sum(1 for c in calls if c.conflict)
        unfulfilled_but_valid = (not fulfilled) and valid_at_end
        locks_held = tuple(end.locks_held) if end else ()
        agents[agent_id] = AgentScore(
            agent_id=agent_id,
            policy=policies.get(agent_id, ""),
            end_reason=end_reason,
            turns=len(calls),
            committed_writes=len(effects),
            fulfilled=fulfilled,
            conflicts_seen=conflicts,
            reread=_reread(calls),
            cas=any(
                c.tool == "update_record" and c.args.get("expected_version") is not None
                and (c.committed or c.reason in _CAS_EVALUATED)
                for c in calls
            ),
            lock=any(c.tool == "acquire_lock" and c.status == 200 for c in calls),
            message=any(c.tool == "send_message" and c.status == 200 for c in calls)
            or any(c.tool == "read_messages" and c.response.get("messages") for c in calls),
            messages_sent=sum(1 for c in calls if c.tool == "send_message" and c.status == 200),
            messages_received=sum(len(c.response.get("messages") or []) for c in calls if c.tool == "read_messages"),
            unnecessary_give_up=conflicts > 0 and end_reason == "returned" and unfulfilled_but_valid,
            abandoned=end is not None and unfulfilled_but_valid,
            valid_at_end=valid_at_end,
            lock_leak=bool(locks_held),
            locks_held_at_end=locks_held,
        )

    committed = tuple(sorted({e.agent_id for e in actions}))
    witness = serial_witness(task, committed, initial, final)
    edges = dependency_edges(ledger)
    cycle = find_cycle(committed, edges)
    stale = stale_overwrites(ledger)
    non_serializable = witness is None
    partial = tuple(a for a in committed if not agents[a].fulfilled)
    primary = primary_label(non_serializable, stale, partial)
    violations: List[str] = []
    for inv in task.invariants:
        violations.extend(inv.violations(initial, final, ledger, task))
    return EpisodeScore(
        task=task.name,
        category=task.category,
        config=config_name,
        agents=agents,
        committed_agents=committed,
        non_serializable=non_serializable,
        serial_witness=witness,
        graph_cycle=cycle is not None,
        cycle=cycle,
        edges=edges,
        stale_overwrite=primary == "stale_overwrite",
        stale_overwrite_seqs=stale,
        write_skew=primary == "write_skew",
        partial_action=primary == "partial_action",
        primary_label=primary,
        partial_commits=partial,
        invariant_violations=violations,
        conflict_observed=bool(stale) or any(c.conflict for c in ledger.calls),
        stall=bool(ledger.flags.get("stalled")),
        locks_held_at_end=dict(ledger.flags.get("locks_held_at_end", {})),
        rounds=int(ledger.flags.get("rounds", 0)),
    )


def score_episode(episode: Any) -> EpisodeScore:
    """Score a :class:`scheduler.Episode` (uses only its ledger, final store and task)."""
    return score(
        episode.task,
        episode.ledger,
        episode.store.snapshot(),
        policies=episode.policies,
        config_name=episode.world_config.coordination.name,
    )


@dataclass
class PairedScore:
    """Focal agent's outcome alone vs. with competitors, plus both episode scores."""

    focal: str
    solo: EpisodeScore
    contended: EpisodeScore

    @property
    def fulfilled_solo(self) -> bool:
        """Focal agent fulfilled its intent when alone."""
        return self.solo.agents[self.focal].fulfilled

    @property
    def fulfilled_contended(self) -> bool:
        """Focal agent fulfilled its intent with competitors present."""
        return self.contended.agents[self.focal].fulfilled

    @property
    def harmed_by_contention(self) -> bool:
        """Integrity failure appears only with competitors (solo clean, contended not)."""
        clean = lambda s: not (s.non_serializable or s.invariant_violation)  # noqa: E731
        return clean(self.solo) and not clean(self.contended)


def score_paired(paired: Any) -> PairedScore:
    """Score a :class:`scheduler.PairedRun`."""
    return PairedScore(paired.focal, score_episode(paired.solo), score_episode(paired.contended))


# --------------------------------------------------------------------------
# Aggregation over episodes (explicit denominators)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Rate:
    """``numerator / denominator`` with both counts kept; ``value`` is ``None`` when the denominator is 0."""

    numerator: int
    denominator: int

    @property
    def value(self) -> Optional[float]:
        """The rate, or ``None`` if undefined (empty denominator)."""
        return None if self.denominator == 0 else self.numerator / self.denominator

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable representation."""
        return {"numerator": self.numerator, "denominator": self.denominator, "value": self.value}


def _agent_scores(episodes: Iterable[EpisodeScore]) -> List[AgentScore]:
    return [a for ep in episodes for a in ep.agents.values()]


def unnecessary_give_up_rate(episodes: Iterable[EpisodeScore]) -> Rate:
    """``unnecessary_give_up`` agents / agents that observed a conflict (``conflicts_seen > 0``)."""
    pool = [a for a in _agent_scores(episodes) if a.conflicts_seen > 0]
    return Rate(sum(a.unnecessary_give_up for a in pool), len(pool))


def abandoned_rate(episodes: Iterable[EpisodeScore]) -> Rate:
    """``abandoned`` agents / ended agents whose intent was still valid.

    The denominator is the agents that ended (any reason) and either had a
    valid intent at the moment they ended or fulfilled it -- the agents for
    which completing the intent was possible. Agents whose intent became
    invalid before they acted (e.g. the losers of a last-unit race) are
    excluded.
    """
    pool = [a for a in _agent_scores(episodes) if a.end_reason != "running" and (a.valid_at_end or a.fulfilled)]
    return Rate(sum(a.abandoned for a in pool), len(pool))


def _contended(episodes: Iterable[EpisodeScore]) -> List[EpisodeScore]:
    return [ep for ep in episodes if len(ep.agents) >= 2]


def non_serializable_rate(episodes: Iterable[EpisodeScore]) -> Rate:
    """Episodes with ``non_serializable`` / contended episodes (two or more agents; solo runs excluded)."""
    pool = _contended(episodes)
    return Rate(sum(ep.non_serializable for ep in pool), len(pool))


def sub_label_rates(episodes: Iterable[EpisodeScore]) -> Dict[str, Rate]:
    """For each primary sub-label: episodes with it / contended episodes (the three sum to ``non_serializable_rate``)."""
    pool = _contended(episodes)
    return {lab: Rate(sum(ep.primary_label == lab for ep in pool), len(pool)) for lab in SUB_LABELS}


def invariant_violation_rate(episodes: Iterable[EpisodeScore]) -> Rate:
    """Episodes with ``invariant_violation`` / contended episodes (two or more agents; solo runs excluded)."""
    pool = _contended(episodes)
    return Rate(sum(ep.invariant_violation for ep in pool), len(pool))


def coordination_choice_rates(episodes: Iterable[EpisodeScore]) -> Dict[str, Rate]:
    """For each of ``reread``, ``cas``, ``lock``, ``message``, ``none``: agents making that choice / all agents.

    An agent can make several choices, so the rates need not sum to 1.
    """
    pool = _agent_scores(episodes)
    return {c: Rate(sum(c in a.choices for a in pool), len(pool)) for c in COORDINATION_CHOICES + ("none",)}
