"""Tool surface that concurrent agents use to act on shared records.

:class:`ConcurrentWorld` wraps a :class:`~records.SharedStore` and exposes the
tools an agent may call. Which coordination tools exist, and how writes are
guarded, is set by :class:`CoordinationConfig` -- the primary experimental
variable of the benchmark.

Tools (always available)
    ``get_record(record_id)``
        Current value; the version too unless the configuration hides it.
    ``update_record(record_id, value, expected_version?)``
        Set a record's value. ``expected_version`` is accepted only when
        conditional writes are enabled and is mandatory when they are required.
    ``claim(record_id, holder?)``
        Set a seat/ticket holder (``holder`` defaults to the caller's id). When
        conditional writes are enabled, ``claim`` is an atomic test-and-set
        (it fails with 409 if someone else holds the record); otherwise it is a
        blind overwrite.
    ``list_effects(record_id?)``
        The caller's *own* committed writes (self-verification, not a
        coordination channel).

Tools (configuration-dependent)
    ``acquire_lock(record_id, lease_steps)`` / ``release_lock(record_id)``
        Exclusive per-record locks. While another agent holds an unexpired lock
        on a record, writes to it are rejected with 423.
    ``send_message(to_agent, text)`` / ``read_messages()``
        Point-to-point inter-agent mailbox.

Write guarding
    * no conditional writes: last writer wins silently (the no-protection
      baseline -- the only place silent overwrites exist);
    * stale ``expected_version``: 409 with the record's current version. The
      call log separates a *concurrency* conflict (``version_conflict``:
      another agent wrote the record after the expected version) from any
      other mismatch (``invalid_version``: a version that does not exist yet,
      or one superseded only by the caller's own writes). Both are rejected
      with the same agent-visible response; only the former sets
      ``CallRecord.conflict``;
    * missing ``expected_version`` when required: 428;
    * record locked by another agent: 423.
    Rejected writes never commit and never touch the ledger's effect stream.

Response text is fixed per outcome; it is not an experimental variable.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from records import (
    HOLDER_KINDS,
    CallRecord,
    RecordNotFound,
    SharedStore,
    ValidationError,
    coerce_value,
    to_json_value,
)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

CAS_OFF = "off"
CAS_AVAILABLE = "available"
CAS_REQUIRED = "required"

PRESET_NAMES: Tuple[str, ...] = (
    "none",
    "reread_only",
    "cas_available",
    "cas_required",
    "locks",
    "messages",
)

WRITE_TOOLS = frozenset({"update_record", "claim"})
READ_TOOLS = frozenset({"get_record"})
MAX_MESSAGE_CHARS = 2000


@dataclass(frozen=True)
class CoordinationConfig:
    """Which coordination affordances the world offers.

    Attributes:
        expose_versions: ``get_record`` responses include the record version.
            Without versions an agent can still re-read and compare values.
        conditional_writes: ``"off"`` (blind writes only; silent
            last-writer-wins), ``"available"`` (``expected_version`` optional)
            or ``"required"`` (writes without ``expected_version`` are rejected
            with 428). Enabling conditional writes also makes ``claim`` an
            atomic test-and-set.
        locks: ``acquire_lock`` / ``release_lock`` exist and are enforced on
            writes by other agents.
        messages: ``send_message`` / ``read_messages`` exist.
    """

    expose_versions: bool = False
    conditional_writes: str = CAS_OFF
    locks: bool = False
    messages: bool = False

    def __post_init__(self) -> None:
        if self.conditional_writes not in (CAS_OFF, CAS_AVAILABLE, CAS_REQUIRED):
            raise ValueError(f"conditional_writes must be off/available/required, got {self.conditional_writes!r}")
        if self.conditional_writes != CAS_OFF and not self.expose_versions:
            raise ValueError("conditional writes require expose_versions=True")

    @classmethod
    def from_names(cls, spec: str | Iterable[str]) -> "CoordinationConfig":
        """Build a configuration from preset names joined by ``+``.

        Presets: ``none`` (blind writes, versions hidden), ``reread_only``
        (versions visible, no conditional writes), ``cas_available``,
        ``cas_required``, ``locks``, ``messages``. Combinations take the union;
        ``cas_required`` dominates ``cas_available``. ``none`` combined with
        anything else is rejected as contradictory.

        Example: ``CoordinationConfig.from_names("cas_available+messages")``.
        """
        names = [n.strip() for n in (spec.split("+") if isinstance(spec, str) else spec) if n.strip()]
        if not names:
            raise ValueError("empty coordination spec")
        unknown = [n for n in names if n not in PRESET_NAMES]
        if unknown:
            raise ValueError(f"unknown coordination preset(s) {unknown}; known: {PRESET_NAMES}")
        if "none" in names and len(set(names)) > 1:
            raise ValueError("'none' cannot be combined with other presets")
        expose = any(n in ("reread_only", "cas_available", "cas_required") for n in names)
        cas = CAS_REQUIRED if "cas_required" in names else CAS_AVAILABLE if "cas_available" in names else CAS_OFF
        return cls(expose_versions=expose, conditional_writes=cas, locks="locks" in names, messages="messages" in names)

    @property
    def name(self) -> str:
        """Canonical ``+``-joined preset name of this configuration."""
        parts: List[str] = []
        if self.conditional_writes == CAS_REQUIRED:
            parts.append("cas_required")
        elif self.conditional_writes == CAS_AVAILABLE:
            parts.append("cas_available")
        elif self.expose_versions:
            parts.append("reread_only")
        if self.locks:
            parts.append("locks")
        if self.messages:
            parts.append("messages")
        return "+".join(parts) if parts else "none"

    @property
    def claim_is_conditional(self) -> bool:
        """``claim`` fails on records held by someone else (vs. silent overwrite)."""
        return self.conditional_writes != CAS_OFF

    def available_tools(self) -> Tuple[str, ...]:
        """Names of the tools callable under this configuration, in schema order."""
        tools = ["get_record", "update_record", "claim", "list_effects"]
        if self.locks:
            tools += ["acquire_lock", "release_lock"]
        if self.messages:
            tools += ["send_message", "read_messages"]
        return tuple(tools)


@dataclass(frozen=True)
class WorldConfig:
    """Full world configuration.

    Attributes:
        coordination: the coordination affordances (experimental variable).
        lock_expiry: if True, a lock lease ends ``lease_steps`` scheduler
            rounds after it was granted; if False, leases never expire and
            ``lease_steps`` is ignored (a leaked lock is held forever).
        max_lease_steps: upper bound on ``lease_steps``.
        concurrency_aware_prompt: plumbing flag for a model loop; when True,
            :func:`build_system_prompt` appends :data:`CONCURRENCY_NOTICE`.
            It has no effect on the world's behaviour.
    """

    coordination: CoordinationConfig = field(default_factory=CoordinationConfig)
    lock_expiry: bool = True
    max_lease_steps: int = 50
    concurrency_aware_prompt: bool = False

    def __post_init__(self) -> None:
        if self.max_lease_steps < 1:
            raise ValueError("max_lease_steps must be >= 1")


def world_config(spec: str = "none", **kwargs: Any) -> WorldConfig:
    """Shorthand: ``world_config("cas_available+locks", lock_expiry=False)``."""
    return WorldConfig(coordination=CoordinationConfig.from_names(spec), **kwargs)


# --------------------------------------------------------------------------
# Tool schemas and prompt plumbing
# --------------------------------------------------------------------------

_RECORD_ID = {"type": "string", "description": "Record id, e.g. 'inventory:widget'."}


def tool_schemas(config: CoordinationConfig) -> List[Dict[str, Any]]:
    """JSON tool schemas (name / description / input_schema) for ``config``.

    The set of tools and the ``expected_version`` parameter vary with the
    configuration; descriptions are fixed text per configuration.
    """
    get_desc = "Read a record. Returns its current value" + (" and version." if config.expose_versions else ".")
    upd_props: Dict[str, Any] = {
        "record_id": _RECORD_ID,
        "value": {"description": "New value: integer stock, decimal string for money, holder name or null."},
    }
    upd_required = ["record_id", "value"]
    upd_desc = "Set a record's value."
    if config.conditional_writes != CAS_OFF:
        upd_props["expected_version"] = {
            "type": "integer",
            "minimum": 1,
            "description": "Commit only if the record is still at this version; otherwise 409 with the current version.",
        }
        if config.conditional_writes == CAS_REQUIRED:
            upd_required.append("expected_version")
            upd_desc += " expected_version is required."
        else:
            upd_desc += " Optionally conditional on expected_version."
    claim_desc = "Set the holder of a seat or ticket record (holder defaults to your agent id)."
    if config.claim_is_conditional:
        claim_desc += " Fails with 409 if the record is held by someone else."
    schemas: List[Dict[str, Any]] = [
        {
            "name": "get_record",
            "description": get_desc,
            "input_schema": {"type": "object", "properties": {"record_id": _RECORD_ID}, "required": ["record_id"], "additionalProperties": False},
        },
        {
            "name": "update_record",
            "description": upd_desc,
            "input_schema": {"type": "object", "properties": upd_props, "required": upd_required, "additionalProperties": False},
        },
        {
            "name": "claim",
            "description": claim_desc,
            "input_schema": {
                "type": "object",
                "properties": {"record_id": _RECORD_ID, "holder": {"type": "string"}},
                "required": ["record_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_effects",
            "description": "List the writes you have committed, optionally for one record.",
            "input_schema": {"type": "object", "properties": {"record_id": _RECORD_ID}, "additionalProperties": False},
        },
    ]
    if config.locks:
        schemas += [
            {
                "name": "acquire_lock",
                "description": "Acquire an exclusive lock on a record for lease_steps steps. While you hold it, other agents' writes to the record are rejected.",
                "input_schema": {
                    "type": "object",
                    "properties": {"record_id": _RECORD_ID, "lease_steps": {"type": "integer", "minimum": 1}},
                    "required": ["record_id", "lease_steps"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "release_lock",
                "description": "Release a lock you hold.",
                "input_schema": {"type": "object", "properties": {"record_id": _RECORD_ID}, "required": ["record_id"], "additionalProperties": False},
            },
        ]
    if config.messages:
        schemas += [
            {
                "name": "send_message",
                "description": "Send a text message to another agent.",
                "input_schema": {
                    "type": "object",
                    "properties": {"to_agent": {"type": "string"}, "text": {"type": "string", "maxLength": MAX_MESSAGE_CHARS}},
                    "required": ["to_agent", "text"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "read_messages",
                "description": "Return messages sent to you that you have not read yet.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        ]
    return schemas


CONCURRENCY_NOTICE = "Other agents may be reading and writing the same records at the same time as you."


def build_system_prompt(agent_id: str, peers: Sequence[str], intent_text: str, config: WorldConfig) -> str:
    """Assemble a model-loop system prompt (plumbing; the text is not a variable).

    Only ``config.concurrency_aware_prompt`` changes the prompt, by appending
    :data:`CONCURRENCY_NOTICE`.
    """
    lines = [
        f"You are agent {agent_id}. Use the tools to complete your task.",
        f"Task: {intent_text}",
    ]
    if config.coordination.messages and peers:
        lines.append("Agents you can message: " + ", ".join(peers) + ".")
    if config.concurrency_aware_prompt:
        lines.append(CONCURRENCY_NOTICE)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# World
# --------------------------------------------------------------------------


@dataclass
class Lock:
    """A granted lock. ``expires_at`` is the first clock value at which it is free (``None``: never)."""

    holder: str
    acquired_at: int
    expires_at: Optional[int]


@dataclass(frozen=True)
class Message:
    """One inter-agent message."""

    msg_id: int
    sender: str
    recipient: str
    text: str
    step: int


class ToolError(Exception):
    """Internal: a call is rejected before reaching the record (400/404)."""

    def __init__(self, status: int, reason: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.message = message


def is_blocking_outcome(call: CallRecord) -> bool:
    """Whether a call left its agent waiting on another agent.

    Blocking outcomes are: ``acquire_lock`` refused (``lock_held``), a write
    rejected because another agent holds the lock (``locked_by_other``), and
    ``read_messages`` returning no messages. Used by stall detection.
    """
    if call.reason in ("lock_held", "locked_by_other"):
        return True
    return call.tool == "read_messages" and call.status == 200 and not call.response.get("messages")


class ConcurrentWorld:
    """Executes tool calls from multiple agents against one shared store.

    The world is single-threaded; concurrency is produced by the scheduler's
    interleaving of calls. The scheduler advances :attr:`clock` (one tick per
    round); lock leases are measured in clock ticks.
    """

    def __init__(self, store: SharedStore, config: WorldConfig, agent_ids: Sequence[str]) -> None:
        if len(set(agent_ids)) != len(agent_ids):
            raise ValueError("agent ids must be unique")
        self.store = store
        self.ledger = store.ledger
        self.config = config
        self.agent_ids: Tuple[str, ...] = tuple(agent_ids)
        self.clock = 0
        self._locks: Dict[str, Lock] = {}
        self._messages: List[Message] = []
        self._read_cursor: Dict[str, int] = {a: 0 for a in agent_ids}

    # ---------------------------------------------------------------- clock

    def tick(self) -> int:
        """Advance the clock by one round and return the new value."""
        self.clock += 1
        return self.clock

    # ---------------------------------------------------------------- locks

    def lock_holder(self, record_id: str) -> Optional[str]:
        """Holder of the unexpired lock on ``record_id``, or ``None``."""
        lock = self._locks.get(record_id)
        if lock is None:
            return None
        if lock.expires_at is not None and self.clock >= lock.expires_at:
            del self._locks[record_id]
            return None
        return lock.holder

    def locks_held_by(self, agent_id: str) -> Tuple[str, ...]:
        """Records on which ``agent_id`` holds an unexpired lock, sorted."""
        return tuple(sorted(r for r in list(self._locks) if self.lock_holder(r) == agent_id))

    def all_locks(self) -> Dict[str, str]:
        """``record_id -> holder`` for every unexpired lock."""
        return {r: h for r in sorted(self._locks) if (h := self.lock_holder(r)) is not None}

    # ----------------------------------------------------------------- calls

    def call(self, agent_id: str, tool: str, args: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Execute one tool call and log its disposition. Returns the response.

        Every call, committed or not, is appended to ``ledger.calls``. The
        returned dict is JSON-serialisable and always has ``ok`` and ``status``.
        """
        args_dict: Dict[str, Any] = copy.deepcopy(dict(args)) if isinstance(args, Mapping) else {}
        log: Dict[str, Any] = {"record_id": None, "committed": False, "effect_seq": None, "conflict": False}
        try:
            if agent_id not in self._read_cursor:
                raise ToolError(400, "unknown_agent", f"400 Bad Request: unknown agent {agent_id!r}.")
            if not isinstance(args, Mapping) and args is not None:
                raise ToolError(400, "invalid_arguments", "400 Bad Request: arguments must be an object.")
            if tool not in self.config.coordination.available_tools():
                raise ToolError(404, "tool_unavailable", f"404 Not Found: no tool named {tool!r}.")
            handler = getattr(self, f"_t_{tool}")
            status, reason, body = handler(agent_id, args_dict, log)
            if reason in ("lock_held", "locked_by_other"):
                log["lease_expires_at"] = self._locks[log["record_id"]].expires_at  # the blocking lock's lease
        except ToolError as err:
            status, reason, body = err.status, err.reason, {"error": err.reason, "message": err.message}
        response = to_json_value({"ok": 200 <= status < 300, "status": status, **body})
        self.ledger.append_call(
            step=self.clock,
            agent_id=agent_id,
            tool=tool,
            args=args_dict,
            status=status,
            reason=reason,
            record_id=log["record_id"],
            committed=log["committed"],
            effect_seq=log["effect_seq"],
            conflict=log["conflict"],
            lease_expires_at=log.get("lease_expires_at"),
            read_version=log.get("read_version"),
            response=copy.deepcopy(response),
        )
        return response

    # -------------------------------------------------------- arg validation

    @staticmethod
    def _check_keys(args: Mapping[str, Any], required: Iterable[str], optional: Iterable[str] = ()) -> None:
        required = tuple(required)
        allowed = set(required) | set(optional)
        missing = [k for k in required if k not in args]
        extra = sorted(k for k in args if k not in allowed)
        if missing:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: missing argument(s) {missing}.")
        if extra:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: unsupported argument(s) {extra}.")

    def _record(self, args: Mapping[str, Any], log: Dict[str, Any]):
        record_id = args.get("record_id")
        if not isinstance(record_id, str):
            raise ToolError(400, "invalid_arguments", "400 Bad Request: record_id must be a string.")
        try:
            record = self.store.get(record_id)
        except RecordNotFound:
            raise ToolError(404, "not_found", f"404 Not Found: no record {record_id!r}.") from None
        log["record_id"] = record_id
        return record

    @staticmethod
    def _positive_int(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: {name} must be a positive integer.")
        return value

    def _check_lock(self, agent_id: str, record, log: Dict[str, Any]) -> Optional[Tuple[int, str, Dict[str, Any]]]:
        if not self.config.coordination.locks:
            return None
        holder = self.lock_holder(record.record_id)
        if holder is None or holder == agent_id:
            return None
        log["conflict"] = True
        return 423, "locked_by_other", {
            "error": "locked",
            "message": f"423 Locked: {record.record_id} is locked by another agent; current version is {record.version}.",
            "current_version": record.version,
        }

    @staticmethod
    def _conflict(record, detail: str, reason: str, log: Dict[str, Any]) -> Tuple[int, str, Dict[str, Any]]:
        log["conflict"] = True
        return 409, reason, {
            "error": "conflict",
            "message": f"409 Conflict: {record.record_id} {detail}; current version is {record.version}.",
            "current_version": record.version,
        }

    def _written_by_other_since(self, record_id: str, version: int, agent_id: str) -> bool:
        """Whether an agent other than ``agent_id`` committed a write to ``record_id`` on top of ``version`` or later."""
        return any(
            e.agent_id != agent_id and e.old_version >= version for e in self.ledger.effects_for(record_id=record_id)
        )

    def _commit(self, agent_id: str, record, value: Any, tool: str, args: Dict[str, Any], log: Dict[str, Any]) -> Dict[str, Any]:
        effect = self.store.commit(agent_id, record.record_id, value, tool, args, self.clock)
        log["committed"] = True
        log["effect_seq"] = effect.seq
        body: Dict[str, Any] = {"record_id": record.record_id, "value": effect.new_value}
        if self.config.coordination.expose_versions:
            body["version"] = effect.new_version
        return body

    # ----------------------------------------------------------------- tools

    def _t_get_record(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, ["record_id"])
        record = self._record(args, log)
        log["read_version"] = record.version
        body: Dict[str, Any] = {"record_id": record.record_id, "kind": record.kind, "value": record.value}
        if self.config.coordination.expose_versions:
            body["version"] = record.version
        return 200, None, body

    def _t_update_record(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        cas = self.config.coordination.conditional_writes
        self._check_keys(args, ["record_id", "value"], ["expected_version"] if cas != CAS_OFF else [])
        record = self._record(args, log)
        expected = args.get("expected_version")
        if expected is not None:
            self._positive_int(expected, "expected_version")
        try:
            value = coerce_value(record.kind, args["value"])
        except ValidationError as exc:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: {exc}.") from None
        if cas == CAS_REQUIRED and expected is None:
            return 428, "missing_expected_version", {
                "error": "precondition_required",
                "message": f"428 Precondition Required: writes to {record.record_id} must include expected_version.",
            }
        locked = self._check_lock(agent_id, record, log)
        if locked:
            return locked
        if expected is not None and expected != record.version:
            body = self._conflict(record, f"was modified (expected version {expected})", "version_conflict", log)
            if not self._written_by_other_since(record.record_id, expected, agent_id):
                log["conflict"] = False
                return body[0], "invalid_version", body[2]
            return body
        return 200, None, self._commit(agent_id, record, value, "update_record", args, log)

    def _t_claim(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, ["record_id"], ["holder"])
        record = self._record(args, log)
        if record.kind not in HOLDER_KINDS:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: {record.record_id} is not a seat or ticket.")
        holder = args.get("holder", agent_id)
        try:
            holder = coerce_value(record.kind, holder)
        except ValidationError as exc:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: {exc}.") from None
        if holder is None:
            raise ToolError(400, "invalid_arguments", "400 Bad Request: holder must be a non-empty string.")
        locked = self._check_lock(agent_id, record, log)
        if locked:
            return locked
        if record.value == holder:
            body: Dict[str, Any] = {"record_id": record.record_id, "value": holder}
            if self.config.coordination.expose_versions:
                body["version"] = record.version
            return 200, "noop", body
        if record.value is not None and self.config.coordination.claim_is_conditional:
            return self._conflict(record, "is held by someone else", "claim_conflict", log)
        return 200, None, self._commit(agent_id, record, holder, "claim", args, log)

    def _t_list_effects(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, [], ["record_id"])
        record_id = args.get("record_id")
        if record_id is not None:
            self._record(args, log)
        effects = [
            {"record_id": e.record_id, "old_value": e.old_value, "new_value": e.new_value, "tool": e.tool}
            for e in self.ledger.effects_for(record_id=record_id, agent_id=agent_id)
        ]
        return 200, None, {"effects": effects}

    def _t_acquire_lock(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, ["record_id", "lease_steps"])
        record = self._record(args, log)
        lease = self._positive_int(args["lease_steps"], "lease_steps")
        if lease > self.config.max_lease_steps:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: lease_steps must be <= {self.config.max_lease_steps}.")
        holder = self.lock_holder(record.record_id)
        if holder is not None and holder != agent_id:
            return 423, "lock_held", {"error": "locked", "message": f"423 Locked: {record.record_id} is locked by another agent."}
        expires = self.clock + lease if self.config.lock_expiry else None
        self._locks[record.record_id] = Lock(agent_id, self.clock, expires)
        log["lease_expires_at"] = expires
        body = {"record_id": record.record_id, "lease_steps": lease if self.config.lock_expiry else None}
        return 200, ("renewed" if holder == agent_id else None), body

    def _t_release_lock(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, ["record_id"])
        record = self._record(args, log)
        if self.lock_holder(record.record_id) != agent_id:
            return 409, "not_lock_holder", {"error": "not_lock_holder", "message": f"409 Conflict: you do not hold the lock on {record.record_id}."}
        del self._locks[record.record_id]
        return 200, None, {"record_id": record.record_id}

    def _t_send_message(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, ["to_agent", "text"])
        to_agent, text = args["to_agent"], args["text"]
        if not isinstance(to_agent, str):
            raise ToolError(400, "invalid_arguments", "400 Bad Request: to_agent must be a string.")
        if to_agent not in self._read_cursor or to_agent == agent_id:
            raise ToolError(404, "unknown_agent", f"404 Not Found: no other agent named {to_agent!r}.")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_MESSAGE_CHARS:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: text must be a non-empty string of at most {MAX_MESSAGE_CHARS} characters.")
        msg = Message(len(self._messages) + 1, agent_id, to_agent, text, self.clock)
        self._messages.append(msg)
        return 200, None, {"message_id": msg.msg_id}

    def _t_read_messages(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, [])
        start = self._read_cursor[agent_id]
        unread = [m for m in self._messages[start:] if m.recipient == agent_id]
        self._read_cursor[agent_id] = len(self._messages)
        return 200, None, {"messages": [{"message_id": m.msg_id, "from": m.sender, "text": m.text} for m in unread]}
