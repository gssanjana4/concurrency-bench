"""Tool surface for concurrent agents on shared records (Study 3 harness, src6; derived from src5/world5.py).

Study 3 changes (registration PREREGISTRATION_STUDY3.md, "The Study 3 lock bundle"). The lock service has two texts:

* ``lock_text = "s2"`` (config ``locks_s2text``): the Study 2 tool texts and responses, byte for byte (tested
  against ``study2_lock_schemas.json``, written from the frozen src5).
* ``lock_text = "s3"`` (configs ``locks`` and ``all_available``), the Study 3 bundle of three changes:
  1. the ``acquire_lock`` description asks the agent to acquire the lock before reading a record it will update and
     to lock every record its decision depends on, and says that reads made before the grant may be out of date;
  2. an ``acquire_lock`` that the scheduler held reports it: the response carries ``waited_rounds`` and the note
     :data:`WAIT_NOTE` (Study 2: a waited grant looked like an immediate one, apart from the token);
  3. while a record is locked under a lease the caller does not hold, ``get_record`` returns ``locked: true``.
  In a control no other agent can lock an agent's records, so (2) and (3) never occur there (tested).
The configs are ``none``, ``cas_available``, ``locks_s2text`` (= ``locks+s2text``), ``locks`` and
``all_available`` (= ``cas_available+locks``, Study 3 lock text).

Study 2 description of this module follows.

Derived from src4/world4.py. The tool API is unchanged except where Study 1's
reviews required a change (each marked *Study 2* below).

Tools (always available)
    ``get_record(record_id)``
        Current value; the version too unless the configuration hides it.
    ``update_record(record_id, value, expected_version?, fencing_token?)``
        Set a record's value. ``expected_version`` exists only when conditional
        writes are enabled (mandatory under ``cas_required``); ``fencing_token``
        exists only when locks are enabled (*Study 2*).
    ``claim(record_id, holder?, expected_version?, fencing_token?)``
        Set a seat/ticket holder (``holder`` defaults to the caller's id). *V2 fix
        (review V1 B1)*: ``claim`` is a plain overwrite in **every**
        configuration, exactly like ``update_record`` with the holder as value;
        under conditional-write configurations it accepts an optional
        ``expected_version`` (409 if stale), as ``update_record`` does. (Before
        the fix it was a server-side test-and-set under CAS configurations, so a
        no-protocol agent was fully protected on seat/ticket by the API.)
    ``list_effects(record_id?)``
        The caller's *own* committed writes.

Tools (configuration-dependent)
    ``acquire_lock(record_id, lease_calls)`` / ``renew_lock(record_id, lease_calls)``
    / ``release_lock(record_id)``  (*Study 2*: fenced, exclusive writes)
        * The lease is counted in the **holder's own tool calls**: a lease of
          ``L`` covers the holder's next ``L`` tool calls of any kind on any
          record (the ``acquire_lock``/``renew_lock`` call itself is not
          counted). Rounds in which the holder makes no call (think time, other
          agents acting, waiting for the model) do not count. ``1 <= L <=
          max_lease_calls`` (20). Every call by the holder first consumes one
          unit of every lease it holds; a lease whose units are exhausted ends
          before that call is processed, so the ``L+1``-th call is not covered.
        * ``acquire_lock`` returns a **fencing token** (a positive integer,
          strictly increasing over the grants *on that record*; *V2 fix, review
          V1 B4*: one counter per record, so a token value carries no
          information about other records or other agents) and
          ``lease_remaining``. ``renew_lock`` restarts the lease of a lock the
          caller still holds (same token) and returns ``lease_remaining``.
          Every write that presents a valid token also returns
          ``lease_remaining``.
        * While a record is locked, the server accepts a write to it only if
          it carries the lock's token: anyone else gets ``423``; the holder
          without a token gets ``428``; a wrong token gets ``409``.
        * When the record is not locked, a write without a token is accepted
          (locks are optional); a write that presents a token whose lease has
          ended is rejected with ``409`` (``lease_expired`` if no newer lock was
          granted on the record, ``stale_fencing_token`` if one was). So every
          write accepted with a token was made while its lease was live, and
          no two lock holders' writes can interleave on a record.
        * What fencing does **not** give (review V1 B5): mutual exclusion of a
          *read-modify-write*. A read under one lease and a write under a later
          lease (re-acquired, new token) is accepted, and so is a tokenless
          write once the record is unlocked. Read-modify-write is safe only
          when the read is inside the same lease as the write; the scorer flags
          a fenced write whose basis read precedes its token's grant
          (``fenced_stale_basis``).
        * ``acquire_lock`` on a record locked by someone else waits (the
          scheduler holds the call) for at most ``lock_wait_rounds`` rounds
          (150; *Round 3 fix, review V1b R1*: the wait covers the longest hold
          one non-renewed lease allows, (max_lease_calls + 1) x (1 + gap_max +
          latency_max) = 21 x 7 = 147 rounds, so a correct holder is never
          timed out however many calls it makes inside its lease. History: v1
          used 6; V2 used 48, which covered only the shortest correct holder
          (``lock_protected``) and refused 10-35 % of waits against holders
          making 2-4 more calls)
          and grants the lock if it is freed meanwhile; otherwise it returns
          ``423``. The wait is one tool call. (*Study 2*: in Study 1 a
          refusal returned at once, so waiting meant polling and burned the
          call cap.)
        * Locks of an agent that has finished are released when it ends.
        * Reads are never blocked by locks (lock users must lock before they
          read; non-lock readers may see a lock holder's intermediate state).
    ``send_message(to_agent, text)`` / ``read_messages()``
        Point-to-point mailbox; ``message_id`` counts the messages *to that
        recipient* (*V2 fix, review V1 B4*: a global id leaked the peer's
        message count). Not offered in any Study 2 grid configuration (review
        V2 F4); only in the labelled ``all_peer_informed``.

Write guarding (first matching rule wins)
    malformed arguments 400/404; missing ``expected_version`` under
    ``cas_required`` 428; lock rules above (423/428/409); stale
    ``expected_version`` 409 with one neutral text that names neither the
    current version nor a modification (Round 3; the call log separates
    ``version_conflict`` -- another agent wrote after that version -- from
    ``invalid_version``, the agent sees the same response); otherwise the
    write commits.

Peer cues (*Study 2*): response and description texts no longer mention
"another agent" / "someone else" (Study 1: "locked by another agent", "held by
someone else"). A 423 or a 409 still reveals that something else changed or
holds the record; that is the observable contention itself, not a prior cue.
*V2 fix (review V2 F1)*: the lock tool text no longer says "every agent" or
"others". Cues that must remain are listed in the README.

Configurations (presets, combinable with ``+``): ``none``, ``reread_only``,
``cas_available``, ``cas_required``, ``locks``, ``messages``, and the aliases
``all_available`` = ``cas_available+locks`` (*V2 fix, review V2 F4*: the
messages tool and its peer list are out of every Study 2 grid configuration)
and ``all_peer_informed`` = ``cas_available+locks+messages`` (peer-informed by
definition: the prompt names the peers; not in the Study 2 grid, used only to
rehearse the message channel). As in Study 1, ``locks`` and ``messages`` alone
hide versions, so ``locks`` vs ``all_available`` is confounded with version
visibility (README).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from records7 import (
    HOLDER_KINDS,
    CallRecord,
    RecordNotFound,
    SharedStore,
    ValidationError,
    coerce_value,
    to_json_value,
)

CAS_OFF = "off"
CAS_AVAILABLE = "available"
CAS_REQUIRED = "required"

PRESET_NAMES: Tuple[str, ...] = ("none", "reread_only", "cas_available", "cas_required", "locks", "messages", "s2text",
                                 "instr", "signals")
ALIASES: Dict[str, str] = {"all_available": "cas_available+locks", "all_peer_informed": "cas_available+locks+messages",
                           "locks_s2text": "locks+s2text", "locks_instr": "locks+instr",
                           "locks_signals": "locks+signals"}
PEER_INFORMED_CONFIGS: Tuple[str, ...] = ("all_peer_informed",)  # never compared with the grid configs
STUDY2_CONFIGS: Tuple[str, ...] = ("none", "cas_available", "locks", "all_available")
STUDY3_CONFIGS: Tuple[str, ...] = ("none", "cas_available", "locks_s2text", "locks", "all_available")
LOCK_TEXTS: Tuple[str, ...] = ("s2", "s3", "instr", "signals")
# Study 4: the lock configurations, a 2 x 2 of the bundle's instruction (part 1) and its two signals (parts 2 and 3)
STUDY4_CONFIGS: Tuple[str, ...] = ("locks_s2text", "locks_instr", "locks_signals", "locks")

WRITE_TOOLS = frozenset({"update_record", "claim"})
READ_TOOLS = frozenset({"get_record"})
LOCK_TOOLS = frozenset({"acquire_lock", "renew_lock", "release_lock"})
MAX_MESSAGE_CHARS = 2000
MAX_LEASE_CALLS = 20
LOCK_WAIT_ROUNDS = 150  # Round 3 (V1b R1): (MAX_LEASE_CALLS + 1) x (1 + gap_max 4 + latency_max 2) = 147


@dataclass(frozen=True)
class CoordinationConfig:
    """Which coordination affordances the world offers (see src4 for field semantics)."""

    expose_versions: bool = False
    conditional_writes: str = CAS_OFF
    locks: bool = False
    messages: bool = False
    lock_text: str = "s3"  # "s2" = the Study 2 lock texts (locks_s2text), "s3" = the Study 3 bundle (locks);
    # Study 4: "instr" = the bundle's instruction only (locks_instr), "signals" = its two signals only (locks_signals)

    def __post_init__(self) -> None:
        if self.lock_text not in LOCK_TEXTS:
            raise ValueError(f"lock_text must be one of {LOCK_TEXTS}, got {self.lock_text!r}")
        if self.conditional_writes not in (CAS_OFF, CAS_AVAILABLE, CAS_REQUIRED):
            raise ValueError(f"conditional_writes must be off/available/required, got {self.conditional_writes!r}")
        if self.conditional_writes != CAS_OFF and not self.expose_versions:
            raise ValueError("conditional writes require expose_versions=True")

    @classmethod
    def from_names(cls, spec: "str | Iterable[str]") -> "CoordinationConfig":
        raw = spec.split("+") if isinstance(spec, str) else list(spec)
        names: List[str] = []
        for n in (x.strip() for x in raw):
            if n:
                names.extend(ALIASES[n].split("+") if n in ALIASES else [n])
        if not names:
            raise ValueError("empty coordination spec")
        unknown = [n for n in names if n not in PRESET_NAMES]
        if unknown:
            raise ValueError(f"unknown coordination preset(s) {unknown}; known: {PRESET_NAMES + tuple(ALIASES)}")
        if "none" in names and len(set(names)) > 1:
            raise ValueError("'none' cannot be combined with other presets")
        texts = [n for n in ("s2text", "instr", "signals") if n in names]
        if len(texts) > 1:
            raise ValueError(f"at most one lock text preset, got {texts}")
        if texts and "locks" not in names:
            raise ValueError(f"{texts[0]!r} (a lock text) needs 'locks'")
        expose = any(n in ("reread_only", "cas_available", "cas_required") for n in names)
        cas = CAS_REQUIRED if "cas_required" in names else CAS_AVAILABLE if "cas_available" in names else CAS_OFF
        return cls(expose_versions=expose, conditional_writes=cas, locks="locks" in names, messages="messages" in names,
                   lock_text={"s2text": "s2", "instr": "instr", "signals": "signals"}.get(texts[0] if texts else "", "s3"))

    @property
    def name(self) -> str:
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
        if self.locks and self.lock_text != "s3":
            parts.append({"s2": "s2text", "instr": "instr", "signals": "signals"}[self.lock_text])
        full = "+".join(parts) if parts else "none"
        for alias, expansion in ALIASES.items():
            if full == expansion:
                return alias
        return full

    @property
    def s3_locks(self) -> bool:
        """Locks with the full Study 3 bundle (description, reported wait, ``locked: true`` on reads)."""
        return self.locks and self.lock_text == "s3"

    @property
    def lock_instruction(self) -> bool:
        """Study 4: the bundle's part 1 (lock before reading, lock every record the decision depends on)."""
        return self.locks and self.lock_text in ("s3", "instr")

    @property
    def lock_signals(self) -> bool:
        """Study 4: the bundle's parts 2 and 3 (a held acquire reports its wait; reads show ``locked: true``)."""
        return self.locks and self.lock_text in ("s3", "signals")

    @property
    def claim_is_conditional(self) -> bool:
        """V2 (review V1 B1): ``claim`` is never a server-side test-and-set (kept for callers; always False)."""
        return False

    @property
    def peer_informed(self) -> bool:
        """The prompt names the peers (messages offered): never compared with the grid configurations."""
        return self.messages

    def available_tools(self) -> Tuple[str, ...]:
        tools = ["get_record", "update_record", "claim", "list_effects"]
        if self.locks:
            tools += ["acquire_lock", "renew_lock", "release_lock"]
        if self.messages:
            tools += ["send_message", "read_messages"]
        return tuple(tools)


@dataclass(frozen=True)
class WorldConfig:
    """Full world configuration.

    Attributes:
        coordination: the affordances (experimental variable).
        lock_expiry: if False, leases never end (``lease_calls`` still validated).
        max_lease_calls: upper bound on ``lease_calls`` (stated in the tool description).
        lock_wait_rounds: rounds a blocking ``acquire_lock`` waits (scheduler; stated in the description).
        concurrency_aware_prompt: appends :data:`CONCURRENCY_NOTICE` to the system prompt.
    """

    coordination: CoordinationConfig = field(default_factory=CoordinationConfig)
    lock_expiry: bool = True
    max_lease_calls: int = MAX_LEASE_CALLS
    lock_wait_rounds: int = LOCK_WAIT_ROUNDS
    concurrency_aware_prompt: bool = False

    def __post_init__(self) -> None:
        if self.max_lease_calls < 1 or self.lock_wait_rounds < 0:
            raise ValueError("max_lease_calls must be >= 1 and lock_wait_rounds >= 0")


def world_config(spec: str = "none", **kwargs: Any) -> WorldConfig:
    return WorldConfig(coordination=CoordinationConfig.from_names(spec), **kwargs)


# --------------------------------------------------------------------------
# Tool schemas and prompt
# --------------------------------------------------------------------------

_RECORD_ID = {"type": "string", "description": "Record id, e.g. 'inventory:widget'."}


def _fence_prop() -> Dict[str, Any]:
    return {"type": "integer", "minimum": 1,
            "description": "The fencing_token returned by acquire_lock. Required while the record is locked. "
                           "A write whose token's lease has ended is rejected with 409."}


def tool_schemas(config: CoordinationConfig, wc: Optional[WorldConfig] = None) -> List[Dict[str, Any]]:
    """JSON tool schemas for ``config`` (fixed text per configuration)."""
    wc = wc or WorldConfig(coordination=config)
    get_desc = "Read a record. Returns its current value" + (" and version." if config.expose_versions else ".")
    if config.lock_signals:
        get_desc += " While the record is locked under a lease you do not hold, also returns locked: true."
    upd_props: Dict[str, Any] = {
        "record_id": _RECORD_ID,
        "value": {"description": "New value: integer stock, decimal string for money, holder name or null."},
    }
    upd_required = ["record_id", "value"]
    upd_desc = "Set a record's value."
    if config.conditional_writes != CAS_OFF:
        upd_props["expected_version"] = {
            "type": "integer", "minimum": 1,
            "description": "Commit only if the record is still at this version; otherwise 409.",
        }
        if config.conditional_writes == CAS_REQUIRED:
            upd_required.append("expected_version")
            upd_desc += " expected_version is required."
        else:
            upd_desc += " Optionally conditional on expected_version."
    claim_props: Dict[str, Any] = {"record_id": _RECORD_ID, "holder": {"type": "string"}}
    claim_desc = "Set the holder of a seat or ticket record (holder defaults to your agent id)."
    if config.conditional_writes != CAS_OFF:  # V2 (V1 B1): a plain overwrite, optionally conditional, as update_record
        claim_props["expected_version"] = dict(upd_props["expected_version"])
        if config.conditional_writes == CAS_REQUIRED:
            claim_desc += " expected_version is required."
        else:
            claim_desc += " Optionally conditional on expected_version."
    if config.locks:
        upd_props["fencing_token"] = _fence_prop()
        claim_props["fencing_token"] = _fence_prop()
    schemas: List[Dict[str, Any]] = [
        {"name": "get_record", "description": get_desc,
         "input_schema": {"type": "object", "properties": {"record_id": _RECORD_ID}, "required": ["record_id"],
                          "additionalProperties": False}},
        {"name": "update_record", "description": upd_desc,
         "input_schema": {"type": "object", "properties": upd_props, "required": upd_required, "additionalProperties": False}},
        {"name": "claim", "description": claim_desc,
         "input_schema": {"type": "object", "properties": claim_props, "required": ["record_id"], "additionalProperties": False}},
        {"name": "list_effects", "description": "List the writes you have committed, optionally for one record.",
         "input_schema": {"type": "object", "properties": {"record_id": _RECORD_ID}, "additionalProperties": False}},
    ]
    if config.locks:
        lease = {"type": "integer", "minimum": 1, "maximum": wc.max_lease_calls,
                 "description": f"Lease length in your own tool calls (1-{wc.max_lease_calls})."}
        schemas += [
            {"name": "acquire_lock",
             "description": acquire_desc(config.lock_instruction, config.lock_signals).format(
                 max_lease=wc.max_lease_calls, wait=wc.lock_wait_rounds),
             "input_schema": {"type": "object", "properties": {"record_id": _RECORD_ID, "lease_calls": lease},
                              "required": ["record_id", "lease_calls"], "additionalProperties": False}},
            {"name": "renew_lock",
             "description": ("Restart the lease of a lock you still hold so it covers your next lease_calls tool calls "
                             f"(1-{wc.max_lease_calls}). Returns the same fencing_token and lease_remaining. "
                             "Fails with 409 if you no longer hold the lock."),
             "input_schema": {"type": "object", "properties": {"record_id": _RECORD_ID, "lease_calls": lease},
                              "required": ["record_id", "lease_calls"], "additionalProperties": False}},
            {"name": "release_lock", "description": "Release a lock you hold.",
             "input_schema": {"type": "object", "properties": {"record_id": _RECORD_ID}, "required": ["record_id"],
                              "additionalProperties": False}},
        ]
    if config.messages:
        schemas += [
            {"name": "send_message", "description": "Send a text message to another agent.",
             "input_schema": {"type": "object",
                              "properties": {"to_agent": {"type": "string"}, "text": {"type": "string", "maxLength": MAX_MESSAGE_CHARS}},
                              "required": ["to_agent", "text"], "additionalProperties": False}},
            {"name": "read_messages", "description": "Return messages sent to you that you have not read yet.",
             "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
        ]
    return schemas


# The Study 2 acquire_lock description (config locks_s2text), byte for byte as src5/world5.py builds it
ACQUIRE_DESC_S2 = (
    "Take an exclusive lock on a record. The lease covers your next lease_calls tool calls "
    "(1-{max_lease}): every tool call you make after this one, of any kind and on any record, "
    "uses one unit; time between your calls does not count. Returns fencing_token and lease_remaining. "
    "While the lock is held, writes to the record are accepted only if they carry this fencing_token "
    "(writes without it get 423). When the lease runs out or you release it, the lock ends and the token "
    "stops working. If the record is already locked, the call waits up to {wait} rounds (a "
    "round is one scheduling step) for it to be released, then returns 423.")
# Study 3 bundle, part 1 and the stated parts 2 and 3: read under the lease, lock every record the decision depends on
ACQUIRE_DESC_S3 = (
    "Take an exclusive lock on a record. Acquire the lock before you read a record you will update, and lock every "
    "record your decision depends on: the records your condition reads as well as the ones you write. A value you "
    "read before the lock was granted may be out of date. The lease covers your next lease_calls tool calls "
    "(1-{max_lease}): every tool call you make after this one, of any kind and on any record, "
    "uses one unit; time between your calls does not count. Returns fencing_token and lease_remaining. "
    "While the lock is held, writes to the record are accepted only if they carry this fencing_token "
    "(writes without it get 423). When the lease runs out or you release it, the lock ends and the token "
    "stops working. If the record is already locked, the call waits up to {wait} rounds (a "
    "round is one scheduling step) for it to be released, then returns 423; a call that waited says so in its "
    "response (waited_rounds).")
# Study 4: the acquire_lock description from the bundle's parts. Part 1 inserts the instruction after the first
# sentence; the signals add the wait clause at the end. (False, False) is ACQUIRE_DESC_S2 and (True, True)
# ACQUIRE_DESC_S3, byte for byte (tested).
_ACQ_FIRST = "Take an exclusive lock on a record. "
ACQUIRE_INSTRUCTION = ("Acquire the lock before you read a record you will update, and lock every record your decision "
                       "depends on: the records your condition reads as well as the ones you write. A value you read "
                       "before the lock was granted may be out of date. ")
ACQUIRE_WAIT_CLAUSE = "; a call that waited says so in its response (waited_rounds)."


def acquire_desc(instruction: bool, signals: bool) -> str:
    """The acquire_lock description template ({max_lease} and {wait} unfilled) for a Study 4 lock text."""
    assert ACQUIRE_DESC_S2.startswith(_ACQ_FIRST) and ACQUIRE_DESC_S2.endswith(".")
    rest = ACQUIRE_DESC_S2[len(_ACQ_FIRST):]
    if signals:
        rest = rest[:-1] + ACQUIRE_WAIT_CLAUSE
    return _ACQ_FIRST + (ACQUIRE_INSTRUCTION if instruction else "") + rest


# Study 3 bundle, part 2: the note of a granted acquire that waited
WAIT_NOTE = ("The record was locked when you asked; this call waited {k} rounds before the lock was granted. "
             "Values you read before this grant may be out of date.")

# Round 3: the one 409 text for an expected_version mismatch (no "was modified", no current version)
VERSION_MISMATCH_TEXT = ("409 Conflict: write to {record_id} rejected: expected_version does not match the record's "
                         "current version.")

CONCURRENCY_NOTICE = "Other agents may be reading and writing the same records at the same time as you."


def build_system_prompt(agent_id: str, peers: Sequence[str], intent_text: str, config: WorldConfig) -> str:
    """System prompt; identical to src4's. The peer list appears only when messaging exists, i.e. only in the
    peer-informed configuration (no Study 2 grid configuration offers messages)."""
    lines = [f"You are agent {agent_id}. Use the tools to complete your task.", f"Task: {intent_text}"]
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
    """A granted lock. ``calls_left``: holder's own calls still covered (``None``: never expires)."""

    holder: str
    token: int
    lease: int
    calls_left: Optional[int]
    granted_at: int


@dataclass(frozen=True)
class Message:
    msg_id: int
    sender: str
    recipient: str
    text: str
    step: int


class ToolError(Exception):
    def __init__(self, status: int, reason: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.message = message


def is_blocking_outcome(call: CallRecord) -> bool:
    """Lock refused, write refused by another's lock, or an empty ``read_messages`` (stall detection)."""
    if call.reason in ("lock_held", "locked_by_other"):
        return True
    return call.tool == "read_messages" and call.status == 200 and not call.response.get("messages")


class ConcurrentWorld:
    """Executes tool calls from several agents against one shared store (single-threaded)."""

    def __init__(self, store: SharedStore, config: WorldConfig, agent_ids: Sequence[str]) -> None:
        if len(set(agent_ids)) != len(agent_ids):
            raise ValueError("agent ids must be unique")
        self.store = store
        self.ledger = store.ledger
        self.config = config
        self.agent_ids: Tuple[str, ...] = tuple(agent_ids)
        self.clock = 0
        self._locks: Dict[str, Lock] = {}
        self._latest_token: Dict[str, Tuple[int, str]] = {}   # record -> (latest granted token, its holder)
        self._tokens: set = set()                             # (record, token) pairs ever granted
        self._next_token: Dict[str, int] = {}                 # record -> next token (V2, V1 B4: per-record counters)
        self._own_calls: Dict[str, int] = {a: 0 for a in agent_ids}
        self._messages: List[Message] = []
        self._inbox_count: Dict[str, int] = {a: 0 for a in agent_ids}  # per-recipient message ids (V1 B4)
        self._read_cursor: Dict[str, int] = {a: 0 for a in agent_ids}
        self._waited = 0
        # grant / renew / expire / release / end_release; ``seq`` = the ledger call seq at which the event takes
        # effect (V2, V1 B6): a token's writes are valid iff grant seq < write seq < end seq.
        self.lock_events: List[Dict[str, Any]] = []

    def tick(self) -> int:
        self.clock += 1
        return self.clock

    # ---------------------------------------------------------------- locks
    def lock_holder(self, record_id: str) -> Optional[str]:
        lock = self._locks.get(record_id)
        return None if lock is None else lock.holder

    def lock_on(self, record_id: str) -> Optional[Lock]:
        return self._locks.get(record_id)

    def locks_held_by(self, agent_id: str) -> Tuple[str, ...]:
        return tuple(sorted(r for r, l in self._locks.items() if l.holder == agent_id))

    def all_locks(self) -> Dict[str, str]:
        return {r: l.holder for r, l in sorted(self._locks.items())}

    def own_calls(self, agent_id: str) -> int:
        return self._own_calls.get(agent_id, 0)

    def _seq_now(self) -> int:
        """Seq of the call being processed (or, between calls, of the next call)."""
        return len(self.ledger.calls) + 1

    def _consume_leases(self, agent_id: str) -> None:
        for rid in list(self._locks):
            lock = self._locks[rid]
            if lock.holder != agent_id or lock.calls_left is None:
                continue
            lock.calls_left -= 1
            if lock.calls_left < 0:
                del self._locks[rid]
                self.lock_events.append({"event": "expire", "record_id": rid, "holder": agent_id, "token": lock.token,
                                         "step": self.clock, "own_call": self._own_calls[agent_id], "seq": self._seq_now()})

    def release_all(self, agent_id: str) -> Tuple[str, ...]:
        """Release every lock ``agent_id`` holds (called by the scheduler when the agent ends)."""
        held = self.locks_held_by(agent_id)
        for rid in held:
            lock = self._locks.pop(rid)
            self.lock_events.append({"event": "end_release", "record_id": rid, "holder": agent_id, "token": lock.token,
                                     "step": self.clock, "seq": self._seq_now()})
        return held

    def acquire_would_wait(self, agent_id: str, tool: str, args: Any) -> bool:
        """Whether a blocking ``acquire_lock`` call would wait now (well-formed, locked by someone else)."""
        if tool != "acquire_lock" or not self.config.coordination.locks or not isinstance(args, Mapping):
            return False
        rid = args.get("record_id")
        if not isinstance(rid, str) or rid not in self.store:
            return False
        lock = self._locks.get(rid)
        if lock is None or lock.holder == agent_id:
            return False
        # A lock whose holder's next call would end it is still held now.
        return True

    # ----------------------------------------------------------------- calls
    def call(self, agent_id: str, tool: str, args: Optional[Mapping[str, Any]] = None, waited_rounds: int = 0) -> Dict[str, Any]:
        args_dict: Dict[str, Any] = copy.deepcopy(dict(args)) if isinstance(args, Mapping) else {}
        log: Dict[str, Any] = {"record_id": None, "committed": False, "effect_seq": None, "conflict": False}
        own = None
        try:
            if agent_id not in self._read_cursor:
                raise ToolError(400, "unknown_agent", f"400 Bad Request: unknown agent {agent_id!r}.")
            self._own_calls[agent_id] += 1
            own = self._own_calls[agent_id]
            self._consume_leases(agent_id)
            if not isinstance(args, Mapping) and args is not None:
                raise ToolError(400, "invalid_arguments", "400 Bad Request: arguments must be an object.")
            if tool not in self.config.coordination.available_tools():
                raise ToolError(404, "tool_unavailable", f"404 Not Found: no tool named {tool!r}.")
            handler = getattr(self, f"_t_{tool}")
            self._waited = waited_rounds  # Study 3: a held acquire_lock reports its wait (s3 lock text)
            status, reason, body = handler(agent_id, args_dict, log)
        except ToolError as err:
            status, reason, body = err.status, err.reason, {"error": err.reason, "message": err.message}
        response = to_json_value({"ok": 200 <= status < 300, "status": status, **body})
        self.ledger.append_call(
            step=self.clock, agent_id=agent_id, tool=tool, args=args_dict, status=status, reason=reason,
            record_id=log["record_id"], committed=log["committed"], effect_seq=log["effect_seq"], conflict=log["conflict"],
            read_version=log.get("read_version"), response=copy.deepcopy(response), own_call=own,
            fencing_token=log.get("fencing_token"), lease_remaining=log.get("lease_remaining"), waited_rounds=waited_rounds,
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

    def _version_suffix(self, record) -> str:
        return f"; current version is {record.version}" if self.config.coordination.expose_versions else ""

    def _version_body(self, record) -> Dict[str, Any]:
        return {"current_version": record.version} if self.config.coordination.expose_versions else {}

    def _check_lock(self, agent_id: str, record, args: Mapping[str, Any], log: Dict[str, Any]):
        """Lock and fencing rules for a write (see module docstring); ``None`` if the write may proceed."""
        if not self.config.coordination.locks:
            return None
        rid = record.record_id
        tok = args.get("fencing_token")
        if tok is not None:
            self._positive_int(tok, "fencing_token")
            log["fencing_token"] = tok
            if (rid, tok) not in self._tokens:
                raise ToolError(400, "invalid_arguments", f"400 Bad Request: {tok} is not a fencing token for {rid}.")
        lock = self._locks.get(rid)
        if lock is not None:
            if lock.holder != agent_id:
                log["conflict"] = True
                return 423, "locked_by_other", {
                    "error": "locked",
                    "message": f"423 Locked: {rid} is locked; writes need the lock's fencing_token{self._version_suffix(record)}.",
                    **self._version_body(record)}
            if tok is None:
                return 428, "missing_fencing_token", {
                    "error": "precondition_required",
                    "message": f"428 Precondition Required: {rid} is locked by you; include your fencing_token."}
            if tok != lock.token:
                return 409, "invalid_fencing_token", {
                    "error": "fencing", "message": f"409 Conflict: fencing_token {tok} is not the token of your current lock on {rid}."}
            log["lease_remaining"] = lock.calls_left
            return None
        if tok is not None:
            latest, latest_holder = self._latest_token[rid]
            if tok < latest:
                log["conflict"] = latest_holder != agent_id
                return 409, "stale_fencing_token", {
                    "error": "fencing",
                    "message": f"409 Conflict: fencing_token {tok} is stale: {rid} was locked again after your lease ended."}
            return 409, "lease_expired", {
                "error": "fencing",
                "message": f"409 Conflict: your lock on {rid} has ended."}  # V2 (V1 B5): neutral, no "acquire it again"
        return None

    @staticmethod
    def _conflict(record, reason: str, log: Dict[str, Any]):
        """Round 3 (review V2b finding 5, task item 6): one neutral text for every ``expected_version`` mismatch,
        identical for ``version_conflict`` and ``invalid_version`` and so in contended and control worlds; it does
        not say "was modified" and does not reveal the current version (re-read to get it)."""
        log["conflict"] = True
        return 409, reason, {"error": "conflict", "message": VERSION_MISMATCH_TEXT.format(record_id=record.record_id)}

    def _written_by_other_since(self, record_id: str, version: int, agent_id: str) -> bool:
        return any(e.agent_id != agent_id and e.old_version >= version for e in self.ledger.effects_for(record_id=record_id))

    def _commit(self, agent_id: str, record, value: Any, tool: str, args: Dict[str, Any], log: Dict[str, Any]) -> Dict[str, Any]:
        effect = self.store.commit(agent_id, record.record_id, value, tool, args, self.clock)
        log["committed"] = True
        log["effect_seq"] = effect.seq
        body: Dict[str, Any] = {"record_id": record.record_id, "value": effect.new_value}
        if self.config.coordination.expose_versions:
            body["version"] = effect.new_version
        if log.get("lease_remaining") is not None:
            body["lease_remaining"] = log["lease_remaining"]
        return body

    # ----------------------------------------------------------------- tools
    def _t_get_record(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, ["record_id"])
        record = self._record(args, log)
        log["read_version"] = record.version
        body: Dict[str, Any] = {"record_id": record.record_id, "kind": record.kind, "value": record.value}
        if self.config.coordination.expose_versions:
            body["version"] = record.version
        lock = self._locks.get(record.record_id)
        if self.config.coordination.lock_signals and lock is not None and lock.holder != agent_id:
            body["locked"] = True  # Study 3 bundle, part 3 (never in a control: no one else can lock its records)
        return 200, None, body

    def _write_optional(self) -> List[str]:
        opt = []
        if self.config.coordination.conditional_writes != CAS_OFF:
            opt.append("expected_version")
        if self.config.coordination.locks:
            opt.append("fencing_token")
        return opt

    def _t_update_record(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        cas = self.config.coordination.conditional_writes
        self._check_keys(args, ["record_id", "value"], self._write_optional())
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
                "message": f"428 Precondition Required: writes to {record.record_id} must include expected_version."}
        locked = self._check_lock(agent_id, record, args, log)
        if locked:
            return locked
        if expected is not None and expected != record.version:
            body = self._conflict(record, "version_conflict", log)
            if not self._written_by_other_since(record.record_id, expected, agent_id):
                log["conflict"] = False
                return body[0], "invalid_version", body[2]
            return body
        return 200, None, self._commit(agent_id, record, value, "update_record", args, log)

    def _t_claim(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        """A plain overwrite of the holder in every configuration (V2, review V1 B1), optionally conditional on
        ``expected_version`` under CAS configurations -- the same rules, in the same order, as update_record."""
        cas = self.config.coordination.conditional_writes
        opt = ["holder"] + self._write_optional()
        self._check_keys(args, ["record_id"], opt)
        record = self._record(args, log)
        if record.kind not in HOLDER_KINDS:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: {record.record_id} is not a seat or ticket.")
        expected = args.get("expected_version")
        if expected is not None:
            self._positive_int(expected, "expected_version")
        holder = args.get("holder", agent_id)
        try:
            holder = coerce_value(record.kind, holder)
        except ValidationError as exc:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: {exc}.") from None
        if holder is None:
            raise ToolError(400, "invalid_arguments", "400 Bad Request: holder must be a non-empty string.")
        if cas == CAS_REQUIRED and expected is None:
            return 428, "missing_expected_version", {
                "error": "precondition_required",
                "message": f"428 Precondition Required: writes to {record.record_id} must include expected_version."}
        locked = self._check_lock(agent_id, record, args, log)
        if locked:
            return locked
        if expected is not None and expected != record.version:
            body = self._conflict(record, "version_conflict", log)
            if not self._written_by_other_since(record.record_id, expected, agent_id):
                log["conflict"] = False
                return body[0], "invalid_version", body[2]
            return body
        if record.value == holder:
            body2: Dict[str, Any] = {"record_id": record.record_id, "value": holder}
            if self.config.coordination.expose_versions:
                body2["version"] = record.version
            return 200, "noop", body2
        return 200, None, self._commit(agent_id, record, holder, "claim", args, log)

    def _t_list_effects(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, [], ["record_id"])
        record_id = args.get("record_id")
        if record_id is not None:
            self._record(args, log)
        effects = [{"record_id": e.record_id, "old_value": e.old_value, "new_value": e.new_value, "tool": e.tool}
                   for e in self.ledger.effects_for(record_id=record_id, agent_id=agent_id)]
        return 200, None, {"effects": effects}

    def _lease_arg(self, args: Mapping[str, Any]) -> int:
        lease = self._positive_int(args["lease_calls"], "lease_calls")
        if lease > self.config.max_lease_calls:
            raise ToolError(400, "invalid_arguments", f"400 Bad Request: lease_calls must be <= {self.config.max_lease_calls}.")
        return lease

    def _t_acquire_lock(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, ["record_id", "lease_calls"])
        record = self._record(args, log)
        lease = self._lease_arg(args)
        rid = record.record_id
        lock = self._locks.get(rid)
        waited = self._waited if self.config.coordination.lock_signals else 0
        if lock is not None and lock.holder != agent_id:
            body423: Dict[str, Any] = {"error": "locked", "message": f"423 Locked: {rid} is already locked."}
            if waited > 0:
                body423["waited_rounds"] = waited
            return 423, "lock_held", body423
        if lock is not None:  # re-acquire by the holder = renew (same token)
            lock.calls_left = lease if self.config.lock_expiry else None
            lock.lease = lease
            reason = "renewed"
        else:
            token = self._next_token.get(rid, 1)
            self._next_token[rid] = token + 1
            lock = Lock(agent_id, token, lease, lease if self.config.lock_expiry else None, self.clock)
            self._locks[rid] = lock
            self._latest_token[rid] = (token, agent_id)
            self._tokens.add((rid, token))
            reason = None
        self.lock_events.append({"event": "grant" if reason is None else "renew", "record_id": rid, "holder": agent_id,
                                 "token": lock.token, "lease": lease, "step": self.clock, "own_call": self._own_calls[agent_id],
                                 "seq": self._seq_now()})
        log["fencing_token"] = lock.token
        log["lease_remaining"] = lock.calls_left
        body: Dict[str, Any] = {"record_id": rid, "fencing_token": lock.token, "lease_remaining": lock.calls_left}
        if waited > 0:  # Study 3 bundle, part 2: a held acquire says so
            body["waited_rounds"] = waited
            body["note"] = WAIT_NOTE.format(k=waited)
        return 200, reason, body

    def _t_renew_lock(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, ["record_id", "lease_calls"])
        record = self._record(args, log)
        lease = self._lease_arg(args)
        rid = record.record_id
        lock = self._locks.get(rid)
        if lock is None or lock.holder != agent_id:
            return 409, "not_lock_holder", {"error": "not_lock_holder",
                                            "message": f"409 Conflict: you do not hold a lock on {rid}."}
        lock.calls_left = lease if self.config.lock_expiry else None
        lock.lease = lease
        self.lock_events.append({"event": "renew", "record_id": rid, "holder": agent_id, "token": lock.token, "lease": lease,
                                 "step": self.clock, "own_call": self._own_calls[agent_id], "seq": self._seq_now()})
        log["fencing_token"] = lock.token
        log["lease_remaining"] = lock.calls_left
        return 200, "renewed", {"record_id": rid, "fencing_token": lock.token, "lease_remaining": lock.calls_left}

    def _t_release_lock(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, ["record_id"])
        record = self._record(args, log)
        lock = self._locks.get(record.record_id)
        if lock is None or lock.holder != agent_id:
            return 409, "not_lock_holder", {"error": "not_lock_holder",
                                            "message": f"409 Conflict: you do not hold a lock on {record.record_id}."}
        del self._locks[record.record_id]
        self.lock_events.append({"event": "release", "record_id": record.record_id, "holder": agent_id, "token": lock.token,
                                 "step": self.clock, "seq": self._seq_now()})
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
        self._inbox_count[to_agent] += 1  # per-recipient id (V1 B4): reveals nothing about other mailboxes
        msg = Message(self._inbox_count[to_agent], agent_id, to_agent, text, self.clock)
        self._messages.append(msg)
        return 200, None, {"message_id": msg.msg_id}

    def _t_read_messages(self, agent_id: str, args: Dict[str, Any], log: Dict[str, Any]):
        self._check_keys(args, [])
        start = self._read_cursor[agent_id]
        unread = [m for m in self._messages[start:] if m.recipient == agent_id]
        self._read_cursor[agent_id] = len(self._messages)
        return 200, None, {"messages": [{"message_id": m.msg_id, "from": m.sender, "text": m.text} for m in unread]}
