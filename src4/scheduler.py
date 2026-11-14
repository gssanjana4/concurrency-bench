"""Deterministic, seeded interleaving of concurrent agents.

Agent protocol
    An agent is a generator produced by ``AgentSpec.make(ctx)``. It yields one
    :class:`ToolCall` at a time, receives the world's response dict via
    ``send``, and may ``return`` a short report string (recorded, never
    scored). Scripted reference agents live in :mod:`agents4`; a model-driven
    agent can implement the same protocol.

Rounds
    The episode proceeds in rounds. At the start of each round the world clock
    ticks. Every live, non-suspended agent then executes exactly one tool call,
    in an order drawn from ``random.Random(seed)`` (a fresh permutation per
    round). Identical inputs therefore produce identical ledgers.

Read-to-write gap (think time)
    ``read_write_gap = G`` suspends an agent for ``G`` rounds right after the
    first successful ``get_record`` of each *decision cycle*; a cycle starts at
    the beginning of the episode and after each write attempt (``update_record``
    or ``claim``, committed or not). The gap models deliberation between
    observing state and acting on it. Further reads in the same cycle are not
    delayed, so an agent that re-reads after deliberating (``rereader``) acts
    on fresher state than one that does not (``naive``).

Termination of an agent (``AgentEnd.reason``)
    ``returned``   the generator finished;
    ``turn_cap``   it wanted another call after ``turn_cap`` executed calls;
    ``stalled``    stall detection fired while it was live;
    ``max_rounds`` the episode hit ``max_rounds``;
    ``error``      it raised, or yielded something that is not a ToolCall.

Stall
    A round is *blocked* when at least one agent is live, no live agent is
    suspended, and every live agent's call in that round had a blocking
    outcome (:func:`world4.is_blocking_outcome`: lock refused, write refused
    because of another agent's lock, or an empty ``read_messages``). A call
    refused by a lock whose lease ends within the episode (logged
    ``lease_expires_at <= max_rounds``) is *waiting*, not blocked: the lock
    frees itself, so it does not count toward a stall. Hence only locks that
    never expire (``lock_expiry=False``) and empty mailboxes can stall, and
    lock expiry on/off is a real ablation whatever ``stall_rounds`` is. After
    ``stall_rounds`` consecutive blocked rounds every live agent ends with
    reason ``stalled`` and ``ledger.flags["stalled"]`` is set.

Lock leases
    Measured in rounds: a lease of ``L`` granted in round ``c`` covers rounds
    ``c .. c+L-1`` (``WorldConfig.lock_expiry``); without expiry, locks are
    held until released.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Generator, List, Mapping, NamedTuple, Optional, Tuple, Union

from records import AgentEnd, Ledger, SharedStore, verify_ledger
from tasks4 import Intent, Task
from world4 import READ_TOOLS, WRITE_TOOLS, CoordinationConfig, ConcurrentWorld, WorldConfig, is_blocking_outcome

AGENT_COUNTS = (2, 4, 8)


class ToolCall(NamedTuple):
    """One tool invocation yielded by an agent."""

    tool: str
    args: Dict[str, Any]


AgentGen = Generator[ToolCall, Dict[str, Any], Optional[str]]


@dataclass(frozen=True)
class AgentContext:
    """What an agent knows at start: its id, its intent, its peers, the tool surface."""

    agent_id: str
    intent: Intent
    peers: Tuple[str, ...]
    coordination: CoordinationConfig


@dataclass(frozen=True)
class AgentSpec:
    """A named agent policy.

    Attributes:
        name: policy name (``naive``, ``careful_cas``, ...).
        make: builds the agent generator from an :class:`AgentContext`.
        requires: capabilities the policy needs, a subset of
            ``{"versions", "conditional_writes", "locks", "messages"}``;
            :func:`run_episode` refuses configurations lacking them.
    """

    name: str
    make: Callable[[AgentContext], AgentGen]
    requires: FrozenSet[str] = frozenset()

    def supported_by(self, config: CoordinationConfig) -> bool:
        """Whether ``config`` offers every capability this policy requires."""
        have = {
            "versions": config.expose_versions,
            "conditional_writes": config.conditional_writes != "off",
            "locks": config.locks,
            "messages": config.messages,
        }
        return all(have[r] for r in self.requires)


@dataclass(frozen=True)
class ScheduleConfig:
    """Scheduler parameters.

    Attributes:
        seed: RNG seed for round orders and start jitter.
        read_write_gap: think-time rounds after the first read of a decision cycle.
        start_jitter: each agent starts after ``randint(0, start_jitter)`` rounds.
        turn_cap: maximum executed tool calls per agent.
        stall_rounds: consecutive blocked rounds that constitute a stall (M).
            Refusals by a lock that expires within ``max_rounds`` are not
            blocked rounds (see "Stall" above).
        max_rounds: hard limit on episode length.
    """

    seed: int = 0
    read_write_gap: int = 0
    start_jitter: int = 0
    turn_cap: int = 40
    stall_rounds: int = 6
    max_rounds: int = 2000

    def __post_init__(self) -> None:
        if self.read_write_gap < 0 or self.start_jitter < 0:
            raise ValueError("gaps must be non-negative")
        if self.turn_cap < 1 or self.stall_rounds < 1 or self.max_rounds < 1:
            raise ValueError("turn_cap, stall_rounds and max_rounds must be >= 1")


@dataclass
class Episode:
    """Everything one run produced. Scoring reads ``ledger``, ``store`` and ``task``."""

    task: Task
    world_config: WorldConfig
    schedule: ScheduleConfig
    policies: Dict[str, str]
    store: SharedStore
    ledger: Ledger

    @property
    def agent_ids(self) -> Tuple[str, ...]:
        """Agents that took part."""
        return tuple(self.policies)


@dataclass
class _Runner:
    agent_id: str
    gen: AgentGen
    started: bool = False
    pending: Optional[ToolCall] = None
    last_response: Optional[Dict[str, Any]] = None
    turns: int = 0
    resume_at: int = 0
    cycle_gapped: bool = False
    live: bool = True


def _resolve_specs(task: Task, agents: Union[AgentSpec, Mapping[str, AgentSpec]]) -> Dict[str, AgentSpec]:
    if isinstance(agents, AgentSpec):
        return {a: agents for a in task.agent_ids}
    missing = [a for a in task.agent_ids if a not in agents]
    extra = [a for a in agents if a not in task.intents]
    if missing or extra:
        raise ValueError(f"agent specs must match task agents; missing={missing} extra={extra}")
    return {a: agents[a] for a in task.agent_ids}


def run_episode(
    task: Task,
    agents: Union[AgentSpec, Mapping[str, AgentSpec]],
    world_config: WorldConfig,
    schedule: ScheduleConfig = ScheduleConfig(),
) -> Episode:
    """Run one episode and return it.

    Args:
        task: the task (records, intents, invariants).
        agents: one spec for every agent, or ``agent_id -> spec``.
        world_config: coordination affordances and lock settings.
        schedule: interleaving parameters.

    Raises:
        ValueError: if a policy requires a capability the configuration lacks.
    """
    specs = _resolve_specs(task, agents)
    coord = world_config.coordination
    for agent_id, spec in specs.items():
        if not spec.supported_by(coord):
            raise ValueError(f"policy {spec.name} of {agent_id} requires {sorted(spec.requires)}; config is {coord.name}")
    ids = task.agent_ids
    store = SharedStore(task.initial)
    world = ConcurrentWorld(store, world_config, ids)
    ledger = store.ledger
    rng = random.Random(schedule.seed)

    runners: List[_Runner] = []
    for agent_id in ids:
        ctx = AgentContext(agent_id, task.intents[agent_id], tuple(a for a in ids if a != agent_id), coord)
        runners.append(_Runner(agent_id, specs[agent_id].make(ctx)))
    for r in runners:
        r.resume_at = 1 + (rng.randint(0, schedule.start_jitter) if schedule.start_jitter else 0)

    def end(r: _Runner, reason: str, report: Optional[str] = None) -> None:
        r.live = False
        r.gen.close()
        ledger.append_end(
            AgentEnd(
                agent_id=r.agent_id,
                reason=reason,
                step=world.clock,
                turns=r.turns,
                effects_at_end=len(ledger.effects),
                locks_held=world.locks_held_by(r.agent_id),
                report=report,
            )
        )

    blocked_streak = 0
    while any(r.live for r in runners):
        if world.clock >= schedule.max_rounds:
            for r in runners:
                if r.live:
                    end(r, "max_rounds")
            break
        clock = world.tick()
        order = list(runners)
        rng.shuffle(order)
        acted = 0
        blocked = 0
        suspended = 0
        for r in order:
            if not r.live:
                continue
            if clock < r.resume_at:
                suspended += 1
                continue
            if r.pending is None:
                try:
                    item = r.gen.send(r.last_response) if r.started else next(r.gen)
                    r.started = True
                except StopIteration as stop:
                    end(r, "returned", None if stop.value is None else str(stop.value))
                    continue
                except Exception as exc:  # noqa: BLE001 - an agent bug ends that agent only
                    end(r, "error", f"{type(exc).__name__}: {exc}")
                    continue
                if not isinstance(item, ToolCall):
                    end(r, "error", f"yielded {type(item).__name__}, expected ToolCall")
                    continue
                r.pending = item
            if r.turns >= schedule.turn_cap:
                end(r, "turn_cap")
                continue
            call = r.pending
            r.pending = None
            r.last_response = world.call(r.agent_id, call.tool, call.args)
            r.turns += 1
            acted += 1
            record = ledger.calls[-1]
            if is_blocking_outcome(record):
                blocked += 1
                if record.lease_expires_at is not None and record.lease_expires_at <= schedule.max_rounds:
                    blocked -= 1  # the blocking lock expires within the episode: waiting, not stalled
            if call.tool in WRITE_TOOLS:
                r.cycle_gapped = False
            elif call.tool in READ_TOOLS and record.status == 200 and not r.cycle_gapped and schedule.read_write_gap:
                r.cycle_gapped = True
                r.resume_at = clock + 1 + schedule.read_write_gap
        live_now = [r for r in runners if r.live]
        if live_now and suspended == 0 and acted > 0 and blocked == acted:
            blocked_streak += 1
        else:
            blocked_streak = 0
        if live_now and blocked_streak >= schedule.stall_rounds:
            ledger.flags["stalled"] = True
            ledger.flags["stall_step"] = world.clock
            for r in live_now:
                end(r, "stalled")
            break

    ledger.flags["rounds"] = world.clock
    ledger.flags["locks_held_at_end"] = world.all_locks()
    verify_ledger(ledger, store.snapshot())
    return Episode(task, world_config, schedule, {a: specs[a].name for a in ids}, store, ledger)


@dataclass
class PairedRun:
    """The same focal agent, seed and task with and without its competitors."""

    focal: str
    solo: Episode
    contended: Episode


def run_paired(
    task: Task,
    agents: Union[AgentSpec, Mapping[str, AgentSpec]],
    world_config: WorldConfig,
    schedule: ScheduleConfig = ScheduleConfig(),
    focal: Optional[str] = None,
) -> PairedRun:
    """Run ``task`` twice with the same seed: focal agent alone, then with all agents.

    The solo run uses :meth:`Task.restrict` so records and invariants are
    identical; only the competing intents are removed. ``focal`` defaults to
    the first agent.
    """
    specs = _resolve_specs(task, agents)
    focal = focal if focal is not None else task.agent_ids[0]
    if focal not in specs:
        raise ValueError(f"unknown focal agent {focal!r}")
    solo = run_episode(task.restrict([focal]), {focal: specs[focal]}, world_config, schedule)
    contended = run_episode(task, specs, world_config, schedule)
    return PairedRun(focal, solo, contended)
