"""Versioned shared records and the ground-truth ledger (Study 2 harness, src5).

Changes from src4/records.py: :class:`CallRecord` gains ``own_call`` (the
caller's own 1-based tool-call index), ``fencing_token`` (granted or presented
token), ``lease_remaining`` (holder's remaining own-call lease after the call)
and ``waited_rounds`` (rounds a blocking ``acquire_lock`` waited). Everything
else is unchanged.

This module is the data layer of the multi-agent concurrency benchmark. It owns
three things:

* :class:`SharedStore` -- a set of versioned records. Every record has a kind
  (``inventory``, ``seat``, ``account``, ``ticket``, ``budget``), a value, and an integer
  version that starts at :data:`INITIAL_VERSION` and is incremented by exactly
  one on every committed write.
* :class:`Ledger` -- the single source of truth for scoring. It holds the
  committed :class:`WriteEffect` stream, the :class:`CallRecord` stream (every
  tool invocation and how the server disposed of it, including rejected calls)
  and the :class:`AgentEnd` events written by the scheduler. Agents never see
  the ledger except through the read-only ``list_effects`` tool.
* Value canonicalisation (:func:`coerce_value`, :func:`normalize_value`,
  :func:`to_json_value`).

Record ids are ``"<kind>:<name>"``, e.g. ``inventory:widget``,
``seat:concert-1/12A``, ``account:acct-1``, ``ticket:T-100``,
``budget:team/cap``.

Value domains:

* ``inventory`` -- ``int`` stock level (negative values are *storable*: the
  store enforces types, not business rules, so that oversells are observable).
* ``account``   -- :class:`~decimal.Decimal` balance with at most two decimal
  places (negative values storable for the same reason).
* ``seat`` / ``ticket`` -- holder name (non-empty ``str``) or ``None``.
* ``budget``    -- :class:`~decimal.Decimal` amount, same domain as ``account``.
  Write-skew tasks use one budget record for a shared cap and one per agent
  for that agent's spend.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation, Overflow
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

KINDS: Tuple[str, ...] = ("inventory", "seat", "account", "ticket", "budget")
HOLDER_KINDS = frozenset({"seat", "ticket"})
DECIMAL_KINDS = frozenset({"account", "budget"})
NUMERIC_KINDS = frozenset({"inventory"}) | DECIMAL_KINDS
INITIAL_VERSION = 1
CENT = Decimal("0.01")

_INT_RE = re.compile(r"^[+-]?[0-9]+$")
_DEC_RE = re.compile(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$")


class ValidationError(ValueError):
    """A value or record id does not fit the record kind's domain."""


class RecordNotFound(KeyError):
    """The requested record id does not exist in the store."""


class LedgerIntegrityError(AssertionError):
    """The ledger's effect chain is inconsistent with itself or the store."""


# --------------------------------------------------------------------------
# Value handling
# --------------------------------------------------------------------------


def kind_of(record_id: str) -> str:
    """Return the record kind encoded in ``record_id`` (``"<kind>:<name>"``).

    Raises:
        ValidationError: if the id is malformed or the kind is unknown.
    """
    if not isinstance(record_id, str) or ":" not in record_id:
        raise ValidationError(f"malformed record id {record_id!r}; expected '<kind>:<name>'")
    kind, name = record_id.split(":", 1)
    if kind not in KINDS:
        raise ValidationError(f"unknown record kind {kind!r} in {record_id!r}")
    if not name:
        raise ValidationError(f"empty record name in {record_id!r}")
    return kind


def coerce_value(kind: str, value: Any) -> Any:
    """Coerce a tool-call value into the canonical Python type for ``kind``.

    Tool calls arrive as JSON, so numbers may be strings and money may be a
    float. Coercion is strict: anything ambiguous is rejected rather than
    guessed, and a rejected value never commits.

    * inventory: ``int`` or an ASCII integer string. ``bool`` is rejected.
    * account/budget: ``int``, ``Decimal``, ASCII numeric string, or float (via its
      shortest ``repr``); must be finite, representable at cent precision
      (huge magnitudes are rejected) and have at most two decimal places.
      Returned quantised to cents.
    * Negative zero (``"-0"``, ``"-0.00"``, ``-0.0``) and strings with
      non-ASCII digits, underscores or surrounding junk are rejected for
      every numeric kind.
    * seat/ticket: ``None`` or a non-empty, non-blank ``str``.

    Raises:
        ValidationError: if the value is outside the kind's domain.
    """
    if kind == "inventory":
        if isinstance(value, bool):
            raise ValidationError("inventory stock must be an integer, not a boolean")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and _INT_RE.match(value.strip()):
            text = value.strip()
            try:
                stock = int(text)
            except ValueError as exc:  # beyond the int-string conversion limit
                raise ValidationError(f"inventory stock is too large: {value!r}") from exc
            if stock == 0 and text.startswith("-"):
                raise ValidationError(f"inventory stock must not be negative zero, got {value!r}")
            return stock
        raise ValidationError(f"inventory stock must be an integer, got {value!r}")
    if kind in DECIMAL_KINDS:
        if isinstance(value, bool):
            raise ValidationError(f"{kind} amount must be a number, not a boolean")
        try:
            if isinstance(value, float):
                dec = Decimal(repr(value))
            elif isinstance(value, (int, Decimal)):
                dec = Decimal(value)
            elif isinstance(value, str):
                if not _DEC_RE.match(value.strip()):
                    raise ValidationError(f"{kind} amount is not a number: {value!r}")
                dec = Decimal(value.strip())
            else:
                raise ValidationError(f"{kind} amount must be a number, got {value!r}")
        except InvalidOperation as exc:
            raise ValidationError(f"{kind} amount is not a number: {value!r}") from exc
        if not dec.is_finite():
            raise ValidationError(f"{kind} amount must be finite, got {value!r}")
        if dec.is_zero() and dec.is_signed():
            raise ValidationError(f"{kind} amount must not be negative zero, got {value!r}")
        try:
            quantized = dec.quantize(CENT)
        except (InvalidOperation, Overflow) as exc:
            raise ValidationError(f"{kind} amount is too large: {value!r}") from exc
        if dec != quantized:
            raise ValidationError(f"{kind} amount has more than two decimal places: {value!r}")
        return quantized
    if kind in HOLDER_KINDS:
        if value is None:
            return None
        if isinstance(value, str) and value.strip():
            return value
        raise ValidationError(f"{kind} holder must be a non-empty string or null, got {value!r}")
    raise ValidationError(f"unknown record kind {kind!r}")


def normalize_value(value: Any) -> Any:
    """Return a hashable canonical form of ``value`` for equality comparison.

    ``Decimal`` values compare and hash numerically (``Decimal("30.00") ==
    Decimal("30")``), so they are returned as-is; floats are converted to
    ``Decimal`` via ``repr``; mappings become sorted tuples of pairs and
    sequences become tuples, recursively. ``bool`` is kept distinct from
    ``int`` by tagging it.
    """
    if isinstance(value, bool):
        return ("__bool__", value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, Mapping):
        return tuple(sorted((str(k), normalize_value(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(normalize_value(v) for v in value)
    return value


def to_json_value(value: Any) -> Any:
    """Convert a stored value to a JSON-serialisable form (Decimal -> str)."""
    if isinstance(value, Decimal):
        return str(value.quantize(CENT))
    if isinstance(value, Mapping):
        return {k: to_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(v) for v in value]
    return value


# --------------------------------------------------------------------------
# Ledger entries
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Record:
    """An immutable snapshot of one record."""

    record_id: str
    kind: str
    value: Any
    version: int


@dataclass(frozen=True)
class WriteEffect:
    """One committed write. Appended to the ledger iff the write committed.

    Attributes:
        agent_id: agent whose tool call produced the write.
        record_id: record written.
        old_value / new_value: value immediately before / after the commit.
        old_version / new_version: version before / after (``new = old + 1``).
        seq: 1-based position in the ledger's effect stream.
        tool: tool that produced the write (``update_record`` or ``claim``).
        args: the tool call's arguments, as received.
        step: world clock (scheduler round) at which the write committed.
    """

    agent_id: str
    record_id: str
    old_value: Any
    new_value: Any
    old_version: int
    new_version: int
    seq: int
    tool: str
    args: Dict[str, Any]
    step: int

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable representation."""
        return to_json_value(asdict(self))


@dataclass(frozen=True)
class CallRecord:
    """Server-side disposition of one tool call (committed or not).

    The call log is the second ground-truth stream next to the effects. It
    records what the server *did*, including facts the calling agent was not
    shown (for example ``read_version`` is logged even in configurations
    whose ``get_record`` response hides versions).

    Attributes:
        seq: 1-based position in the call stream.
        step: world clock (scheduler round) of the call.
        agent_id, tool, args: the call as received.
        status: HTTP-like status code returned to the agent.
        reason: server-side cause. One of ``None`` (plain success),
            ``"noop"`` (claim on a record the caller already holds),
            ``"renewed"`` (lock re-acquired by its holder),
            ``"version_conflict"`` (stale ``expected_version``: another agent
            wrote the record after that version), ``"invalid_version"``
            (any other ``expected_version`` mismatch: a version that does not
            exist yet, or one superseded only by the caller's own writes;
            rejected like a conflict, same response, but ``conflict`` is
            False), ``"claim_conflict"``, ``"locked_by_other"``
            (write rejected because another agent holds the lock),
            ``"lock_held"`` (``acquire_lock`` refused), ``"not_lock_holder"``,
            ``"missing_expected_version"``, ``"invalid_arguments"``,
            ``"tool_unavailable"``, ``"not_found"``, ``"unknown_agent"``.
        record_id: target record, if any.
        committed: whether a :class:`WriteEffect` was appended.
        effect_seq: ``seq`` of that effect, if committed.
        conflict: the server rejected a write because of concurrent activity
            (stale ``expected_version``, claim on a record held by someone
            else, or write to a record locked by another agent). Rejected
            writes never commit, so ``conflict`` implies ``not committed``.
        lease_expires_at: unused in src5 (leases are counted in the holder's
            own calls, see ``lease_remaining``); kept for schema stability.
        read_version: for successful ``get_record`` calls, the version read.
        response: the exact response returned to the agent.
    """

    seq: int
    step: int
    agent_id: str
    tool: str
    args: Dict[str, Any]
    status: int
    reason: Optional[str]
    record_id: Optional[str]
    committed: bool
    effect_seq: Optional[int]
    conflict: bool
    lease_expires_at: Optional[int] = None
    read_version: Optional[int] = None
    response: Dict[str, Any] = field(default_factory=dict)
    own_call: Optional[int] = None
    fencing_token: Optional[int] = None
    lease_remaining: Optional[int] = None
    waited_rounds: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable representation."""
        return to_json_value(asdict(self))


@dataclass(frozen=True)
class AgentEnd:
    """Why and when an agent stopped.

    Attributes:
        agent_id: the agent.
        reason: ``"returned"`` (the agent finished on its own), ``"turn_cap"``,
            ``"stalled"`` (cut off by stall detection), ``"max_rounds"`` (the
            episode hit its round limit), ``"error"`` (the agent raised or
            yielded something that is not a tool call), ``"truncated"`` /
            ``"provider_error"`` (a cut-off last completion), ``"refusal"`` /
            ``"content_filter"`` (a refusal or safety stop with no tool call)
            or ``"probe"``.
        step: world clock at which the agent stopped.
        turns: tool calls the agent executed.
        effects_at_end: ``len(ledger.effects)`` when the agent stopped, so the
            store state at that moment can be replayed from the ledger.
        locks_held: records whose lock the agent still held (unexpired lease)
            when it stopped.
        report: the agent's own return value; recorded for analysis, never
            used for scoring.
    """

    agent_id: str
    reason: str
    step: int
    turns: int
    effects_at_end: int = 0
    locks_held: Tuple[str, ...] = ()
    report: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable representation."""
        return to_json_value(asdict(self))


class Ledger:
    """Append-only ground truth of an episode.

    Only the store (effects), the world (calls) and the scheduler (agent ends,
    flags) append to it. Scoring reads it together with the final store and
    nothing else.
    """

    def __init__(self) -> None:
        self.effects: List[WriteEffect] = []
        self.calls: List[CallRecord] = []
        self.agent_ends: List[AgentEnd] = []
        self.flags: Dict[str, Any] = {
            "stalled": False,
            "stall_step": None,
            "locks_held_at_end": {},
            "rounds": 0,
        }

    def append_effect(self, **fields: Any) -> WriteEffect:
        """Append a committed write; ``seq`` is assigned here."""
        effect = WriteEffect(seq=len(self.effects) + 1, **fields)
        self.effects.append(effect)
        return effect

    def append_call(self, **fields: Any) -> CallRecord:
        """Append a call disposition; ``seq`` is assigned here."""
        call = CallRecord(seq=len(self.calls) + 1, **fields)
        self.calls.append(call)
        return call

    def append_end(self, end: AgentEnd) -> None:
        """Record that an agent stopped."""
        self.agent_ends.append(end)

    def calls_for(self, agent_id: str) -> List[CallRecord]:
        """All calls made by ``agent_id``, in seq order."""
        return [c for c in self.calls if c.agent_id == agent_id]

    def effects_for(self, record_id: Optional[str] = None, agent_id: Optional[str] = None) -> List[WriteEffect]:
        """Committed effects, optionally filtered by record and/or agent, in seq order."""
        return [
            e
            for e in self.effects
            if (record_id is None or e.record_id == record_id) and (agent_id is None or e.agent_id == agent_id)
        ]

    def end_for(self, agent_id: str) -> Optional[AgentEnd]:
        """The :class:`AgentEnd` for ``agent_id``, or ``None`` if it has not ended."""
        for end in self.agent_ends:
            if end.agent_id == agent_id:
                return end
        return None

    def fingerprint(self) -> str:
        """Canonical JSON of the full ledger; equal iff two episodes are identical."""
        payload = {
            "effects": [e.to_dict() for e in self.effects],
            "calls": [c.to_dict() for c in self.calls],
            "ends": [e.to_dict() for e in self.agent_ends],
            "flags": to_json_value(self.flags),
        }
        return json.dumps(payload, sort_keys=True)


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------


class SharedStore:
    """Versioned records whose every committed write is appended to a ledger.

    The store performs type validation only (:func:`coerce_value`); it does not
    enforce business rules such as non-negative stock, so that the scorer can
    observe violations.
    """

    def __init__(self, records: Mapping[str, Any], ledger: Optional[Ledger] = None) -> None:
        self.ledger = ledger if ledger is not None else Ledger()
        self._records: Dict[str, Record] = {}
        for record_id, value in records.items():
            kind = kind_of(record_id)
            self._records[record_id] = Record(record_id, kind, coerce_value(kind, value), INITIAL_VERSION)

    def __contains__(self, record_id: object) -> bool:
        return record_id in self._records

    def record_ids(self) -> List[str]:
        """All record ids, in insertion order."""
        return list(self._records)

    def get(self, record_id: str) -> Record:
        """Return the current snapshot of ``record_id``.

        Raises:
            RecordNotFound: if the record does not exist.
        """
        try:
            return self._records[record_id]
        except KeyError:
            raise RecordNotFound(record_id) from None

    def commit(self, agent_id: str, record_id: str, new_value: Any, tool: str, args: Mapping[str, Any], step: int) -> WriteEffect:
        """Commit a write unconditionally and append it to the ledger.

        Preconditions (versions, locks, claims) are the caller's job; this is
        the single choke point through which state changes.

        Raises:
            RecordNotFound: if the record does not exist.
            ValidationError: if ``new_value`` is outside the kind's domain.
        """
        current = self.get(record_id)
        value = coerce_value(current.kind, new_value)
        updated = Record(record_id, current.kind, value, current.version + 1)
        self._records[record_id] = updated
        return self.ledger.append_effect(
            agent_id=agent_id,
            record_id=record_id,
            old_value=current.value,
            new_value=value,
            old_version=current.version,
            new_version=updated.version,
            tool=tool,
            args=copy.deepcopy(dict(args)),
            step=step,
        )

    def values(self) -> Dict[str, Any]:
        """Current value of every record."""
        return {rid: r.value for rid, r in self._records.items()}

    def snapshot(self) -> Dict[str, Tuple[Any, int]]:
        """Current ``(value, version)`` of every record."""
        return {rid: (r.value, r.version) for rid, r in self._records.items()}


def verify_ledger(ledger: Ledger, snapshot: Mapping[str, Tuple[Any, int]]) -> None:
    """Check that the effect stream is a consistent version chain ending in ``snapshot``.

    For every record: versions advance by exactly one per effect starting at
    :data:`INITIAL_VERSION`, each effect's ``old_value`` equals the previous
    effect's ``new_value``, and the last effect matches the final snapshot.
    Effect ``seq`` numbers must be ``1..n``.

    Raises:
        LedgerIntegrityError: on the first inconsistency found.
    """
    for i, effect in enumerate(ledger.effects, start=1):
        if effect.seq != i:
            raise LedgerIntegrityError(f"effect seq {effect.seq} at position {i}")
    last: Dict[str, Tuple[Any, int]] = {}
    for effect in ledger.effects:
        if effect.record_id not in snapshot:
            raise LedgerIntegrityError(f"effect on unknown record {effect.record_id}")
        if effect.new_version != effect.old_version + 1:
            raise LedgerIntegrityError(f"effect {effect.seq} skips versions")
        if effect.record_id in last:
            prev_value, prev_version = last[effect.record_id]
            if effect.old_version != prev_version or normalize_value(effect.old_value) != normalize_value(prev_value):
                raise LedgerIntegrityError(f"effect {effect.seq} does not chain from the previous write")
        elif effect.old_version != INITIAL_VERSION:
            raise LedgerIntegrityError(f"first effect on {effect.record_id} starts at version {effect.old_version}")
        last[effect.record_id] = (effect.new_value, effect.new_version)
    for record_id, (value, version) in snapshot.items():
        expected_value, expected_version = last.get(record_id, (value, INITIAL_VERSION))
        if version != expected_version or normalize_value(value) != normalize_value(expected_value):
            raise LedgerIntegrityError(f"final state of {record_id} does not match the ledger")


def replay(initial: Mapping[str, Any], effects: Iterable[WriteEffect]) -> Dict[str, Any]:
    """Return record values after applying ``effects`` (in order) to ``initial``."""
    values = dict(initial)
    for effect in effects:
        values[effect.record_id] = effect.new_value
    return values


def value_at_version(ledger: Ledger, initial: Mapping[str, Any], record_id: str, version: int) -> Any:
    """Value of ``record_id`` at ``version``, reconstructed from the ledger.

    Raises:
        LedgerIntegrityError: if no committed write produced that version.
    """
    if version == INITIAL_VERSION:
        return initial[record_id]
    for effect in ledger.effects:
        if effect.record_id == record_id and effect.new_version == version:
            return effect.new_value
    raise LedgerIntegrityError(f"no committed write produced {record_id} version {version}")


def initial_values(ledger: Ledger, snapshot: Mapping[str, Tuple[Any, int]], record_ids: Iterable[str]) -> Dict[str, Any]:
    """Reconstruct each record's initial value from the ledger and final snapshot.

    The initial value is the ``old_value`` of the first effect on the record,
    or the final value if the record was never written.
    """
    result: Dict[str, Any] = {}
    for record_id in record_ids:
        effects = ledger.effects_for(record_id=record_id)
        result[record_id] = effects[0].old_value if effects else snapshot[record_id][0]
    return result


def write_bases(ledger: Ledger) -> Dict[int, Tuple[int, Optional[int]]]:
    """``effect seq -> (basis_version, read_call_seq)`` for every committed write.

    The *basis* of a write by agent ``T`` to record ``r`` is the latest
    version of ``r`` that ``T`` had observed when it sent the write: its last
    successful ``get_record`` of ``r`` before the write, or the version
    produced by ``T``'s own earlier committed write to ``r``, whichever is
    later. A write with neither (a blind first write) has basis
    :data:`INITIAL_VERSION`: it acts on the initial state as given in the
    task. ``read_call_seq`` is the seq of the basis read, or ``None`` when the
    basis is the agent's own write or the blind default.

    Raises:
        LedgerIntegrityError: if an effect has no committing call record.
    """
    effect_call: Dict[int, int] = {c.effect_seq: c.seq for c in ledger.calls if c.committed}
    new_version = {e.seq: e.new_version for e in ledger.effects}
    by_agent: Dict[str, List[CallRecord]] = {}
    for c in ledger.calls:
        by_agent.setdefault(c.agent_id, []).append(c)
    out: Dict[int, Tuple[int, Optional[int]]] = {}
    for e in ledger.effects:
        if e.seq not in effect_call:
            raise LedgerIntegrityError(f"effect {e.seq} has no committing call")
        write_seq = effect_call[e.seq]
        basis: Tuple[int, Optional[int]] = (INITIAL_VERSION, None)
        for c in by_agent.get(e.agent_id, []):
            if c.seq >= write_seq:
                break
            if c.record_id != e.record_id:
                continue
            if c.tool == "get_record" and c.status == 200 and c.read_version is not None:
                if c.read_version >= basis[0]:
                    basis = (c.read_version, c.seq)
            elif c.committed and c.effect_seq is not None and new_version[c.effect_seq] >= basis[0]:
                basis = (new_version[c.effect_seq], None)
        out[e.seq] = basis
    return out


def action_effects(ledger: Ledger, initial: Mapping[str, Any]) -> List[WriteEffect]:
    """Committed writes that count as the writer's action, in seq order.

    A write counts iff its new value differs from the value of its basis
    version (:func:`write_bases`), i.e. the agent changed what it last saw.
    Writing back the value one observed (a no-op write-back) is not an
    action: it is not a take, a sale or a commitment of the agent's intent.
    A stale write that happens to leave the stored value unchanged (two
    agents read stock 1 and both write 0) *does* count, because the writer
    changed the value it saw.
    """
    bases = write_bases(ledger)
    return [
        e
        for e in ledger.effects
        if normalize_value(e.new_value) != normalize_value(value_at_version(ledger, initial, e.record_id, bases[e.seq][0]))
    ]
