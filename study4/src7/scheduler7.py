"""Seeded, randomized interleaving of concurrent agents (Study 3 harness, src6; derived from src5/scheduler5.py).

Study 3 change: the **start mode** (registration, "Start modes"). ``together`` is the Study 2 schedule (every agent
starts in round ``1 + U{0..start_jitter}``). ``staggered``: the first agent (a0) starts in round
``1 + U{0..lead_jitter}`` (stream ``a0|start``); every other agent starts ``U{stagger_min..stagger_max}`` rounds
after a0 (stream ``<agent>|stagger``), so it tends to begin while a0 is inside its read-decide-write cycle and to
meet a perceivable sign of a0's work (a lock it is shown on a read, a wait, a 423, a 409) before it protects.
Everything else (think time, latency, round order, lock waits, deadlock and stall detection) is unchanged.

Study 2 description follows.

Study 1 (src4/scheduler.py) explored essentially one interleaving: a fixed
read-to-write gap, no jitter, and a seed that only permuted the order within a
round, so identical agents stayed in lockstep, every first read preceded every
first write, and the seed fixed the first mover (reviews T1 sec. 7, T2 F9).

Study 2 draws a random *environment* per episode from its schedule seed:

Rounds
    Each round the world clock ticks, then every live agent that is not
    delayed makes one call, in a fresh random order (stream ``order``).

Start offset
    Agent ``a`` starts in round ``1 + U{0..start_jitter}`` (stream ``a|start``).

Think time (before every completion; *V2 fix, review V1 B2*)
    After a call that ends a *turn* the agent is suspended for
    ``U{gap_min..gap_max}`` rounds, drawn per (agent, turn) (stream ``a|gap``):
    that is the time the model takes to produce its next completion. A model
    agent marks the last queued call of each reply ``ToolCall.ends_turn``
    (the calls of one reply run without a think gap between them); every
    scripted yield is its own turn (the default). Before the fix the gap came
    only after the first read of a decision cycle, so a re-read followed by a
    write had a near-zero read-to-write window by rule; that rule made
    re-reading look twice as useful as it is (V1 B2: rereader/naive failure
    0.50 under the old rule, 0.74 with a gap before every completion).

Call latency
    After each executed call, with probability ``latency_p`` the agent is
    delayed a further ``U{1..latency_max}`` rounds (stream ``a|lat``). This
    breaks the lockstep of multi-call replies.

All draws are indexed by the agent's own counters (cycle number, call number),
so the schedule is a deterministic function of the seed and of what each
agent does; identical inputs give identical ledgers (tested), and a scripted
policy sees the same environment in every configuration.

Blocking lock wait
    A well-formed ``acquire_lock`` on a record locked by another agent is held
    by the scheduler for at most ``WorldConfig.lock_wait_rounds`` rounds; it is
    executed (one call, one turn) as soon as the lock is free, or when the wait
    ends (then the world returns 423). ``CallRecord.waited_rounds`` logs it.

Termination of an agent (``AgentEnd.reason``): ``returned``, ``turn_cap`` (it
wanted call ``turn_cap + 1``), ``stalled``, ``max_rounds``, ``error``, and the
reasons an agent generator returns with :class:`AgentStop` (*V2*, review V2
§5: ``truncated`` -- the model hit max_tokens without a tool call;
``provider_error`` -- the provider ended the completion with an error, e.g.
Gemini ``MALFORMED_FUNCTION_CALL``), so neither is counted as the agent
finishing on its own. When an agent ends, its locks are released (world7).

Deadlock (*V2*, review V2 F5): in every round the scheduler builds the
wait-for graph of agents whose ``acquire_lock`` is being held (agent ->
holder of the record it waits for). A cycle is a lock-order deadlock; it is
recorded (``ledger.flags['deadlock_rounds']``, ``deadlock_first_step``,
``deadlock_agents``). It resolves when a wait times out (a waiting agent makes
no calls, so its own leases do not run down), not by the stall rule.

Stall: as in src4 -- ``stall_rounds`` consecutive rounds in which every live,
undelayed agent's call was blocking and no lock involved can expire.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Generator, List, Mapping, NamedTuple, Optional, Tuple, Union

from records7 import AgentEnd, Ledger, SharedStore, verify_ledger
from tasks7 import Intent, Task
from world7 import READ_TOOLS, WRITE_TOOLS, CoordinationConfig, ConcurrentWorld, WorldConfig, is_blocking_outcome


class ToolCall(NamedTuple):
    tool: str
    args: Dict[str, Any]
    ends_turn: bool = True  # V2 (V1 B2): the think gap follows a call that ends a turn


class AgentStop(NamedTuple):
    """Return value of an agent generator that ends for a reason other than finishing (``truncated``,
    ``provider_error``, ``refusal``, ``content_filter``); ``report`` is the agent's text, as for ``returned``."""

    reason: str
    report: Optional[str] = None


# "probe": a first-reply probe agent (one completion); "refusal" / "content_filter": a refusal or safety stop (Round 4)
AGENT_STOP_REASONS = ("truncated", "provider_error", "probe", "refusal", "content_filter")


AgentGen = Generator[ToolCall, Dict[str, Any], Optional[str]]
START_MODES = ("together", "staggered")


def start_rounds(seed: int, ids: Tuple[str, ...], schedule: "ScheduleConfig") -> Dict[str, int]:
    """Round in which each agent makes its first completion (see module docstring, Study 3 start modes)."""
    if schedule.start_mode == "together" or not ids:
        return {a: 1 + random.Random(f"{seed}|{a}|start").randint(0, schedule.start_jitter) for a in ids}
    lead = ids[0]
    first = 1 + random.Random(f"{seed}|{lead}|start").randint(0, schedule.lead_jitter)
    out = {lead: first}
    for a in ids[1:]:
        out[a] = first + random.Random(f"{seed}|{a}|stagger").randint(schedule.stagger_min, schedule.stagger_max)
    return out


@dataclass(frozen=True)
class AgentContext:
    agent_id: str
    intent: Intent
    peers: Tuple[str, ...]
    coordination: CoordinationConfig
    seed: int = 0  # the episode's schedule seed (scripted policies seed their randomized back-off with it)


@dataclass(frozen=True)
class AgentSpec:
    name: str
    make: Callable[[AgentContext], AgentGen]
    requires: FrozenSet[str] = frozenset()

    def supported_by(self, config: CoordinationConfig) -> bool:
        have = {"versions": config.expose_versions, "conditional_writes": config.conditional_writes != "off",
                "locks": config.locks, "messages": config.messages}
        return all(have[r] for r in self.requires)


@dataclass(frozen=True)
class ScheduleConfig:
    """Scheduler parameters (Study 2 defaults; see module docstring)."""

    seed: int = 0
    gap_min: int = 0
    gap_max: int = 4
    start_jitter: int = 3
    latency_p: float = 0.3
    latency_max: int = 2
    turn_cap: int = 40
    stall_rounds: int = 6
    max_rounds: int = 3000
    start_mode: str = "together"   # Study 3: together | staggered
    lead_jitter: int = 2           # staggered: a0 starts in round 1 + U{0..lead_jitter}
    stagger_min: int = 5           # staggered: every other agent starts U{stagger_min..stagger_max} rounds after a0
    stagger_max: int = 10

    def __post_init__(self) -> None:
        if self.start_mode not in START_MODES:
            raise ValueError(f"start_mode must be one of {START_MODES}, got {self.start_mode!r}")
        if self.lead_jitter < 0 or self.stagger_min < 0 or self.stagger_max < self.stagger_min:
            raise ValueError("lead_jitter, stagger_min >= 0 and stagger_max >= stagger_min required")
        if self.gap_min < 0 or self.gap_max < self.gap_min or self.start_jitter < 0 or self.latency_max < 0:
            raise ValueError("gaps, jitter and latency must be non-negative and gap_max >= gap_min")
        if not 0.0 <= self.latency_p <= 1.0:
            raise ValueError("latency_p must be in [0, 1]")
        if self.turn_cap < 1 or self.stall_rounds < 1 or self.max_rounds < 1:
            raise ValueError("turn_cap, stall_rounds and max_rounds must be >= 1")

    def as_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in ("seed", "gap_min", "gap_max", "start_jitter", "latency_p", "latency_max",
                                              "turn_cap", "stall_rounds", "max_rounds", "start_mode", "lead_jitter",
                                              "stagger_min", "stagger_max")}


def schedule_seed(*parts: Any) -> int:
    """A 63-bit schedule seed from a key (template, instance, schedule index); never the same first mover by design."""
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:15], 16)


@dataclass
class Episode:
    task: Task
    world_config: WorldConfig
    schedule: ScheduleConfig
    policies: Dict[str, str]
    store: SharedStore
    ledger: Ledger

    @property
    def agent_ids(self) -> Tuple[str, ...]:
        return tuple(self.policies)


@dataclass
class _Runner:
    agent_id: str
    gen: AgentGen
    rng_gap: random.Random
    rng_lat: random.Random
    started: bool = False
    pending: Optional[ToolCall] = None
    last_response: Optional[Dict[str, Any]] = None
    turns: int = 0
    resume_at: int = 0
    live: bool = True
    wait_start: Optional[int] = None


def _resolve_specs(task: Task, agents: Union[AgentSpec, Mapping[str, AgentSpec]]) -> Dict[str, AgentSpec]:
    if isinstance(agents, AgentSpec):
        return {a: agents for a in task.agent_ids}
    missing = [a for a in task.agent_ids if a not in agents]
    extra = [a for a in agents if a not in task.intents]
    if missing or extra:
        raise ValueError(f"agent specs must match task agents; missing={missing} extra={extra}")
    return {a: agents[a] for a in task.agent_ids}


def run_episode(task: Task, agents: Union[AgentSpec, Mapping[str, AgentSpec]], world_config: WorldConfig,
                schedule: ScheduleConfig = ScheduleConfig()) -> Episode:
    """Run one episode and return it (deterministic given its inputs)."""
    specs = _resolve_specs(task, agents)
    coord = world_config.coordination
    for agent_id, spec in specs.items():
        if not spec.supported_by(coord):
            raise ValueError(f"policy {spec.name} of {agent_id} requires {sorted(spec.requires)}; config is {coord.name}")
    ids = task.agent_ids
    store = SharedStore(task.initial)
    world = ConcurrentWorld(store, world_config, ids)
    ledger = store.ledger
    s = schedule.seed
    order_rng = random.Random(f"{s}|order")

    runners: List[_Runner] = []
    starts: Dict[str, int] = {}
    first_round = start_rounds(s, ids, schedule)
    for agent_id in ids:
        ctx = AgentContext(agent_id, task.intents[agent_id], tuple(a for a in ids if a != agent_id), coord, s)
        r = _Runner(agent_id, specs[agent_id].make(ctx), random.Random(f"{s}|{agent_id}|gap"),
                    random.Random(f"{s}|{agent_id}|lat"))
        r.resume_at = first_round[agent_id]
        starts[agent_id] = r.resume_at
        runners.append(r)

    def end(r: _Runner, reason: str, report: Optional[str] = None) -> None:
        r.live = False
        r.gen.close()
        held = world.locks_held_by(r.agent_id)
        world.release_all(r.agent_id)
        ledger.append_end(AgentEnd(agent_id=r.agent_id, reason=reason, step=world.clock, turns=r.turns,
                                   effects_at_end=len(ledger.effects), locks_held=held, report=report))

    blocked_streak = 0
    deadlock_rounds = 0
    deadlock_first: Optional[int] = None
    deadlock_agents: set = set()
    while any(r.live for r in runners):
        if world.clock >= schedule.max_rounds:
            for r in runners:
                if r.live:
                    end(r, "max_rounds")
            break
        clock = world.tick()
        order = list(runners)
        order_rng.shuffle(order)
        acted = blocked = suspended = 0
        waits_for: Dict[str, str] = {}
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
                    if isinstance(stop.value, AgentStop) and stop.value.reason in AGENT_STOP_REASONS:
                        end(r, stop.value.reason, stop.value.report)
                    else:
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
            if world.acquire_would_wait(r.agent_id, call.tool, call.args):
                if r.wait_start is None:
                    r.wait_start = clock
                if clock - r.wait_start < world_config.lock_wait_rounds:
                    lock = world.lock_on(call.args["record_id"])
                    if lock is not None:
                        waits_for[r.agent_id] = lock.holder
                    acted += 1
                    if lock is not None and lock.calls_left is None:
                        blocked += 1  # waiting on a lock that never expires
                    continue
            waited = 0 if r.wait_start is None else clock - r.wait_start
            r.wait_start = None
            r.pending = None
            r.last_response = world.call(r.agent_id, call.tool, call.args, waited_rounds=waited)
            r.turns += 1
            acted += 1
            record = ledger.calls[-1]
            if is_blocking_outcome(record):
                lock = world.lock_on(record.record_id) if record.record_id else None
                if record.tool == "read_messages" or (lock is not None and lock.calls_left is None):
                    blocked += 1
            delay = 0
            if getattr(call, "ends_turn", True):  # think time before the agent's next completion (V1 B2)
                delay += r.rng_gap.randint(schedule.gap_min, schedule.gap_max)
            if schedule.latency_p > 0 and schedule.latency_max > 0 and r.rng_lat.random() < schedule.latency_p:
                delay += r.rng_lat.randint(1, schedule.latency_max)
            r.resume_at = clock + 1 + delay
        # lock-order deadlock: a cycle in this round's wait-for graph (resolved later by lease expiry)
        for start in sorted(waits_for):
            seen, a = [], start
            while a in waits_for and a not in seen:
                seen.append(a)
                a = waits_for[a]
            if a in seen:
                deadlock_rounds += 1
                deadlock_first = clock if deadlock_first is None else deadlock_first
                deadlock_agents |= set(seen[seen.index(a):])
                break
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
    ledger.flags["deadlock_rounds"] = deadlock_rounds
    ledger.flags["deadlock_first_step"] = deadlock_first
    ledger.flags["deadlock_agents"] = sorted(deadlock_agents)
    ledger.flags["locks_held_at_end"] = world.all_locks()
    ledger.flags["start_rounds"] = starts
    ledger.flags["start_mode"] = schedule.start_mode
    ledger.flags["lock_events"] = list(world.lock_events)
    verify_ledger(ledger, store.snapshot())
    return Episode(task, world_config, schedule, {a: specs[a].name for a in ids}, store, ledger)
