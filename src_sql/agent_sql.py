"""Truly concurrent SQL agents: prompts, tools, the per-agent model loop, and one episode.

Every agent runs in its own thread with its own model conversation and its
own sqlite3 connection (sqlenv.SqlSession). There is no scheduler: agents
start together (a barrier) and their model calls and SQL statements
interleave in wall-clock time. Temperature 0 is requested; timing is not
deterministic, so repeated episodes of one cell are repetitions, not
replays.

Tools: ``run_sql(sql)`` and ``finish(status, note)``. ``finish`` ends the
agent (status "done" or "declined" is its claim, used by the integrity
check). Replying without a tool call also ends the agent (claim: none).

Turn cap: at most ``turn_cap`` (12) executed non-finish tool calls per agent;
an agent that asks for call 13 is ended with reason ``turn_cap`` (as in the
main study: 12 executed calls, at most 13 completions). ``finish`` is not
counted.

Provider failures and the spend cap abort the whole episode (nothing is
written; a resumed run repeats it), as in src4/run4.py.

The provider layer, price table, spend log and fake provider are imported
unchanged from src4 (read-only; no file there is modified, and no bytecode
is written there).
"""

from __future__ import annotations

import copy
import json
import os
import random
import sys
import threading
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

sys.dont_write_bytecode = True  # never write __pycache__ into the frozen src4/
HERE = os.path.dirname(os.path.abspath(__file__))
SRC4 = os.path.join(os.path.dirname(HERE), "src4")
if SRC4 not in sys.path:
    sys.path.append(SRC4)

from model_agent4 import (  # noqa: E402  (src4, read-only)
    DEFAULT_MAX_TOKENS,
    TRUNCATED_STOPS,
    BudgetExceeded,
    PriceTable,
    ProviderFailure,
    SpendTracker,
    completion_cost,
    make_provider,
    normalized_usage,
    now_utc,
)

import classify_sql as C  # noqa: E402
import tasks_sql as T  # noqa: E402
from sqlenv import DEFAULT_BUSY_TIMEOUT_S, EpisodeClock, SqlLog, SqlSession  # noqa: E402

TURN_CAP = 12
TEMPERATURE = 0.0
START_MESSAGE = "Begin."

SYSTEM_TEMPLATE = (
    "You are {agent}. You have SQL access to a shared SQLite database (a database file in WAL mode) through the "
    "run_sql tool; each call runs on your own database connection. Other clients may be reading and writing the "
    "same database at the same time as you.\n"
    "Schema:\n{schema}\n"
    "Task: {task}\n"
    'When you are finished, call finish with status "done" if you completed the task or "declined" if you did not, '
    "and a one-line note."
)

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "run_sql",
        "description": ("Run SQL on your connection to the shared SQLite database. Several statements may be separated "
                        "by semicolons; they run in order and stop at the first error. Returns the rows of queries, "
                        "rows_affected for writes, or the SQLite error message."),
        "input_schema": {"type": "object", "properties": {"sql": {"type": "string", "description": "SQL text"}},
                         "required": ["sql"]},
    },
    {
        "name": "finish",
        "description": "End your work and report the outcome.",
        "input_schema": {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["done", "declined"]},
            "note": {"type": "string", "description": "one-line summary"}},
            "required": ["status"]},
    },
]


def system_prompt(inst: T.Instance, agent: str) -> str:
    return SYSTEM_TEMPLATE.format(agent=agent, schema=inst.schema_text(), task=inst.instructions[agent])


class LockedSpend(SpendTracker):
    """src4 SpendTracker made safe for concurrent agent threads."""

    def __init__(self, path: Optional[str], max_usd: Optional[float] = None) -> None:
        super().__init__(path, max_usd)
        self._lock = threading.Lock()

    def record(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            super().record(entry)


# --------------------------------------------------------------------------
# One agent
# --------------------------------------------------------------------------


class SqlAgent:
    def __init__(self, inst: T.Instance, agent: str, session: SqlSession, provider: Any, probe: Any, *, model: str,
                 turn_cap: int, max_tokens: int, temperature: Optional[float], prices: Optional[PriceTable],
                 spend: Optional[SpendTracker], episode_id: str, abort: threading.Event) -> None:
        self.inst, self.agent, self.session = inst, agent, session
        self.provider, self.probe, self.model = provider, probe, model
        self.turn_cap, self.max_tokens, self.temperature = turn_cap, max_tokens, temperature
        self.prices, self.spend, self.episode_id, self.abort = prices, spend, episode_id, abort
        self.system = system_prompt(inst, agent)
        self.fatal: Optional[BaseException] = None
        self.record: Dict[str, Any] = {
            "agent_id": agent, "task": inst.instructions[agent], "system": self.system, "messages": [], "turns": [],
            "executions": [], "completions": 0, "tool_calls": 0, "multi_tool_turns": 0, "invalid_calls": [],
            "unexecuted_tool_calls": [], "claim": None, "note": None, "final_text": None, "end_reason": "running",
            "stop_reason": None, "truncated": False, "left_txn_open": False,
            "usage": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}, "cost_usd": 0.0,
        }

    def _log_completion(self, comp: Any) -> None:
        rec = self.record
        usage = normalized_usage(comp, self.probe)
        cost, source = completion_cost(self.model, comp, usage, self.prices)
        for k in ("input", "output", "cache_read", "cache_write"):
            rec["usage"][k] += usage.get(k) or 0
        rec["cost_usd"] += cost
        turn = {"index": rec["completions"], "content": copy.deepcopy(comp.blocks), "stop_reason": comp.stop_reason,
                "model_served": comp.model_served, "temperature_requested": comp.temperature_requested,
                "temperature_effective": comp.temperature_effective, "at_utc": comp.timestamp_utc,
                "t_episode": self.session.clock.now(), "usage": usage, "cost_usd": cost, "cost_source": source}
        if comp.provider_meta:
            turn["provider_meta"] = copy.deepcopy(comp.provider_meta)
        rec["turns"].append(turn)
        if self.spend is not None:
            self.spend.record({"episode_id": self.episode_id, "agent_id": self.agent, "model": self.model,
                               "completion": rec["completions"], "usage": usage, "cost_usd": cost,
                               "cost_source": source, "at_utc": comp.timestamp_utc})

    def run(self) -> None:
        try:
            self._loop()
        except (ProviderFailure, BudgetExceeded) as exc:
            self.fatal = exc
            self.record["end_reason"] = "aborted"
            self.abort.set()
        except Exception as exc:  # noqa: BLE001 - a harness bug ends this agent, recorded
            self.record["end_reason"] = "error"
            self.record["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            self.record["left_txn_open"] = self.session.close()

    def _loop(self) -> None:
        rec = self.record
        history: List[Dict[str, Any]] = [{"role": "user", "content": START_MESSAGE}]
        rec["messages"].append({"role": "user", "content": START_MESSAGE})
        while True:
            if self.abort.is_set():
                rec["end_reason"] = "aborted_by_episode"
                return
            if rec["completions"] >= self.turn_cap + 1:
                rec["end_reason"] = "completion_cap"
                return
            if self.probe is not None:
                self.probe.last_usage = None
            try:
                comp = self.provider.complete(self.model, self.system, TOOLS, history, self.max_tokens, self.temperature)
            except Exception as exc:  # noqa: BLE001
                raise ProviderFailure(f"{self.model}: {type(exc).__name__}: {exc}") from exc
            rec["completions"] += 1
            self._log_completion(comp)
            rec["stop_reason"] = comp.stop_reason
            blocks = comp.blocks
            tool_uses = comp.tool_uses
            rec["messages"].append({"role": "assistant", "content": copy.deepcopy(blocks)})
            if not tool_uses:
                rec["final_text"] = "".join(b.get("text", "") for b in blocks if b["type"] == "text")
                rec["truncated"] = comp.stop_reason in TRUNCATED_STOPS
                rec["end_reason"] = "returned_without_finish"
                return
            if len(tool_uses) > 1:
                rec["multi_tool_turns"] += 1
            history.append(self.provider.history_assistant(comp))
            results: List[Dict[str, Any]] = []
            for i, tu in enumerate(tool_uses):
                name, args = tu.get("name"), tu.get("input")
                if name == "finish":
                    status = args.get("status") if isinstance(args, dict) else None
                    if status in ("done", "declined"):
                        rec["claim"] = status
                        note = args.get("note")
                        rec["note"] = note if isinstance(note, str) else None
                        rec["end_reason"] = "finished"
                        rec["executions"].append({"completion": rec["completions"] - 1, "tool": "finish",
                                                  "args": copy.deepcopy(args), "t": self.session.clock.now()})
                        rec["unexecuted_tool_calls"] = [{"tool": t.get("name"), "args": copy.deepcopy(t.get("input"))}
                                                        for t in tool_uses[i + 1:]]
                        return
                    response: Dict[str, Any] = {"ok": False, "error": 'finish needs status "done" or "declined"'}
                    rec["invalid_calls"].append({"tool": name, "args": copy.deepcopy(args)})
                else:
                    if rec["tool_calls"] >= self.turn_cap:
                        rec["end_reason"] = "turn_cap"
                        rec["unexecuted_tool_calls"] = [{"tool": t.get("name"), "args": copy.deepcopy(t.get("input"))}
                                                        for t in tool_uses[i:]]
                        return
                    rec["tool_calls"] += 1
                    if name == "run_sql" and isinstance(args, dict) and isinstance(args.get("sql"), str) \
                            and "_unparsed_arguments" not in args:
                        response = self.session.run(args["sql"])
                    else:
                        response = {"ok": False, "error": f"unknown tool or bad arguments for {name!r}"}
                        rec["invalid_calls"].append({"tool": name, "args": copy.deepcopy(args)})
                rec["executions"].append({"completion": rec["completions"] - 1, "tool": name, "args": copy.deepcopy(args),
                                          "response": copy.deepcopy(response), "sql_call": self.session.calls,
                                          "t": self.session.clock.now()})
                result = {"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps(response, default=str)}
                if not response.get("ok"):
                    result["is_error"] = True
                results.append(result)
            history.append(self.provider.history_tool_results(results))
            rec["messages"].append({"role": "user", "content": copy.deepcopy(results)})


# --------------------------------------------------------------------------
# One episode
# --------------------------------------------------------------------------


def run_episode(inst: T.Instance, model: str, providers: List[Tuple[Any, Any]], db_path: str, *, episode_id: str,
                turn_cap: int = TURN_CAP, max_tokens: int = DEFAULT_MAX_TOKENS, temperature: Optional[float] = TEMPERATURE,
                prices: Optional[PriceTable] = None, spend: Optional[SpendTracker] = None,
                busy_timeout_s: float = DEFAULT_BUSY_TIMEOUT_S, episode_timeout_s: float = 900.0,
                dry_run: bool = False) -> Dict[str, Any]:
    """Run all agents concurrently on a fresh database; return the transcript (not written).

    ``providers[k]`` is the (provider, usage_probe) pair for agent k; each agent
    thread uses only its own pair. Raises ProviderFailure / BudgetExceeded.
    """
    import sqlite3

    T.setup_db(db_path, inst)
    log, clock = SqlLog(), EpisodeClock()
    abort = threading.Event()
    probe_col = (inst.target.table, inst.target.unique_col) if inst.target.unique_col else None
    agents: List[SqlAgent] = []
    for k, a in enumerate(inst.agents):
        session = SqlSession(db_path, a, log, clock, busy_timeout_s=busy_timeout_s, unique_probe=probe_col)
        prov, probe = providers[k]
        agents.append(SqlAgent(inst, a, session, prov, probe, model=model, turn_cap=turn_cap, max_tokens=max_tokens,
                               temperature=temperature, prices=prices, spend=spend, episode_id=episode_id, abort=abort))
    barrier = threading.Barrier(len(agents))

    def start(ag: SqlAgent) -> None:
        try:
            barrier.wait(timeout=30)
        except threading.BrokenBarrierError:
            pass
        ag.run()

    started_utc, t0 = now_utc(), time.monotonic()
    threads = [threading.Thread(target=start, args=(ag,), name=f"{episode_id}:{ag.agent}", daemon=True) for ag in agents]
    for th in threads:
        th.start()
    deadline = t0 + episode_timeout_s
    for th in threads:
        th.join(max(0.0, deadline - time.monotonic()))
    if any(th.is_alive() for th in threads):
        abort.set()
        for ag, th in zip(agents, threads):
            if th.is_alive():
                ag.record["timed_out"] = True
        for th in threads:
            th.join()
    for ag in agents:
        if ag.record.get("timed_out") and ag.record["end_reason"] == "aborted_by_episode":
            ag.record["end_reason"] = "episode_timeout"
    fatal = next((ag.fatal for ag in agents if ag.fatal is not None), None)
    if fatal is not None:
        raise fatal

    entries = log.entries
    claims = {ag.agent: ag.record["claim"] for ag in agents}
    per_agent = {a: [e for e in entries if e["agent"] == a] for a in inst.agents}
    effects = {a: C.committed_effects(per_agent[a], inst) for a in inst.agents}
    behaviors = {a: C.classify_agent(per_agent[a], inst, claims[a]) for a in inst.agents}
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        integrity = T.check_integrity(conn, inst, claims, effects)
        final_db = T.snapshot_tables(conn)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
    finally:
        conn.close()
    records = {ag.agent: ag.record for ag in agents}
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    for r in records.values():
        for k in totals:
            totals[k] += r["usage"][k]
    return {
        "episode_id": episode_id, "dry_run": dry_run, "model": model, "exploratory": True,
        "provider": getattr(providers[0][0], "name", "?"),
        "instance": inst.describe(), "task": inst.template, "variant": inst.variant, "n_agents": inst.n_agents,
        "settings": {"turn_cap": turn_cap, "max_tokens": max_tokens, "temperature_requested": temperature,
                     "busy_timeout_s": busy_timeout_s, "journal_mode": "wal", "isolation_level": None,
                     "episode_timeout_s": episode_timeout_s, "sqlite_version": sqlite3.sqlite_version,
                     "python": sys.version.split()[0]},
        "run_info": {"started_utc": started_utc, "finished_utc": now_utc(), "wall_seconds": round(time.monotonic() - t0, 3)},
        "agents": records,
        "sql_log": entries,
        "effects": {a: e.__dict__ for a, e in effects.items()},
        "behaviors": behaviors,
        "integrity": integrity,
        "final_db": final_db,
        "totals": {"usage": totals, "cost_usd": sum(r["cost_usd"] for r in records.values()),
                   "completions": sum(r["completions"] for r in records.values()),
                   "tool_calls": sum(r["tool_calls"] for r in records.values()),
                   "truncated_agents": [a for a, r in records.items() if r["truncated"]]},
    }


# --------------------------------------------------------------------------
# Fake model (dry runs and tests): scripted SQL styles, no network
# --------------------------------------------------------------------------

STYLES: Dict[str, Tuple[str, ...]] = {
    "counter": ("blind", "atomic", "txn"),
    "withdraw": ("blind", "atomic", "txn", "cas"),
    "handle": ("blind", "guarded", "txn", "constraint"),
    "order": ("blind", "atomic", "txn"),
}

Action = Tuple[str, ...]


def _rows(r: Optional[Dict[str, Any]]) -> List[List[Any]]:
    try:
        return r["results"][-1]["rows"]
    except (TypeError, KeyError, IndexError):
        return []


def _affected(r: Optional[Dict[str, Any]]) -> int:
    try:
        return int(r["results"][-1].get("rows_affected", -1))
    except (TypeError, KeyError, IndexError, ValueError):
        return -1


def _ok(r: Optional[Dict[str, Any]]) -> bool:
    return bool(r and r.get("ok"))


def fake_script(inst: T.Instance, agent: str, style: str) -> Generator[Action, Optional[Dict[str, Any]], None]:
    """A scripted 'agent': yields ('sql', text) or ('finish', status, note); receives the run_sql result."""
    t, p = inst.template, inst.params
    mine = p["per_agent"][agent]
    for _attempt in range(3):
        if t == "counter":
            name = p["name"]
            if style == "atomic":
                r = yield ("sql", f"UPDATE counters SET value = value + {mine} WHERE name = '{name}'")
                if _ok(r):
                    yield ("finish", "done", "added")
                    return
                continue
            if style == "txn":
                r = yield ("sql", "BEGIN IMMEDIATE")
                if not _ok(r):
                    continue
            r = yield ("sql", f"SELECT value FROM counters WHERE name = '{name}'")
            v = _rows(r)[0][0] if _rows(r) else None
            if v is None:
                yield ("sql", "ROLLBACK") if style == "txn" else ("sql", "SELECT 1")
                continue
            r = yield ("sql", f"UPDATE counters SET value = {v + mine} WHERE name = '{name}'")
            if style == "txn":
                r = yield ("sql", "COMMIT") if _ok(r) else ("sql", "ROLLBACK")
            if _ok(r):
                yield ("finish", "done", "added")
                return
            if style == "txn":
                yield ("sql", "ROLLBACK")
        elif t == "withdraw":
            acct = p["account"]
            if style == "atomic":
                r = yield ("sql", f"UPDATE accounts SET balance = balance - {mine} WHERE id = {acct} AND balance >= {mine}")
                if _ok(r):
                    yield ("finish", "done" if _affected(r) == 1 else "declined", "withdrawal")
                    return
                continue
            if style == "cas":
                r = yield ("sql", f"SELECT balance, version FROM accounts WHERE id = {acct}")
                b, ver = _rows(r)[0] if _rows(r) else (None, None)
                if b is None:
                    continue
                if b < mine:
                    yield ("finish", "declined", "insufficient")
                    return
                r = yield ("sql", f"UPDATE accounts SET balance = {b - mine}, version = {ver + 1} WHERE id = {acct} AND version = {ver}")
                if _ok(r) and _affected(r) == 1:
                    yield ("finish", "done", "withdrawn")
                    return
                continue
            if style == "txn":
                r = yield ("sql", "BEGIN IMMEDIATE")
                if not _ok(r):
                    continue
            r = yield ("sql", f"SELECT balance FROM accounts WHERE id = {acct}")
            b = _rows(r)[0][0] if _rows(r) else None
            if b is None or b < mine:
                if style == "txn":
                    yield ("sql", "ROLLBACK")
                yield ("finish", "declined", "insufficient")
                return
            r = yield ("sql", f"UPDATE accounts SET balance = {b - mine} WHERE id = {acct}")
            if style == "txn":
                r = yield ("sql", "COMMIT") if _ok(r) else ("sql", "ROLLBACK")
            if _ok(r):
                yield ("finish", "done", "withdrawn")
                return
        elif t == "handle":
            h = p["handle"]
            ins = f"INSERT INTO users (handle, owner) VALUES ('{h}', '{agent}')"
            if style == "guarded":
                r = yield ("sql", f"INSERT INTO users (handle, owner) SELECT '{h}', '{agent}' "
                                  f"WHERE NOT EXISTS (SELECT 1 FROM users WHERE handle = '{h}')")
                if _ok(r):
                    yield ("finish", "done" if _affected(r) == 1 else "declined", "registration")
                    return
                continue
            if style == "constraint":
                r = yield ("sql", "CREATE UNIQUE INDEX IF NOT EXISTS users_handle_ux ON users(handle)")
                r = yield ("sql", ins)
                if _ok(r):
                    yield ("finish", "done", "registered")
                    return
                if "UNIQUE" in str(r.get("error") if r else ""):
                    yield ("finish", "declined", "taken")
                    return
                continue
            if style == "txn":
                r = yield ("sql", "BEGIN IMMEDIATE")
                if not _ok(r):
                    continue
            r = yield ("sql", f"SELECT COUNT(*) FROM users WHERE handle = '{h}'")
            c = _rows(r)[0][0] if _rows(r) else None
            if c is None or c > 0:
                if style == "txn":
                    yield ("sql", "ROLLBACK")
                yield ("finish", "declined", "taken")
                return
            r = yield ("sql", ins)
            if style == "txn":
                r = yield ("sql", "COMMIT") if _ok(r) else ("sql", "ROLLBACK")
            if _ok(r):
                yield ("finish", "done", "registered")
                return
        else:  # order
            sku = p["sku"]
            ins = f"INSERT INTO orders (customer, sku, qty, status) VALUES ('{agent}', '{sku}', {mine}, 'confirmed')"
            if style == "atomic":
                r = yield ("sql", f"UPDATE stock SET qty = qty - {mine} WHERE sku = '{sku}' AND qty >= {mine}")
                if not _ok(r):
                    continue
                if _affected(r) != 1:
                    yield ("finish", "declined", "insufficient")
                    return
                r = yield ("sql", ins)
                yield ("finish", "done", "ordered")
                return
            if style == "txn":
                r = yield ("sql", "BEGIN IMMEDIATE")
                if not _ok(r):
                    continue
            r = yield ("sql", f"SELECT qty FROM stock WHERE sku = '{sku}'")
            q = _rows(r)[0][0] if _rows(r) else None
            if q is None or q < mine:
                if style == "txn":
                    yield ("sql", "ROLLBACK")
                yield ("finish", "declined", "insufficient")
                return
            r = yield ("sql", f"UPDATE stock SET qty = {q - mine} WHERE sku = '{sku}'")
            if _ok(r):
                r = yield ("sql", ins)
            if style == "txn":
                r = yield ("sql", "COMMIT") if _ok(r) else ("sql", "ROLLBACK")
            if _ok(r):
                yield ("finish", "done", "ordered")
                return
            if style == "txn":
                yield ("sql", "ROLLBACK")
    yield ("finish", "declined", "gave up after retries")


class FakeSqlPolicy:
    """Stateful policy for src4's FakeProvider: drives :func:`fake_script` from the tool results.

    A short random sleep before each 'completion' stands in for model latency,
    so threads really interleave between read and write.
    """

    def __init__(self, inst: T.Instance, agent: str, style: str, seed: str, think_s: Tuple[float, float] = (0.005, 0.04)) -> None:
        self.gen = fake_script(inst, agent, style)
        self.started = False
        self.rng = random.Random(seed)
        self.think_s = think_s
        self.style = style

    def __call__(self, system: str, tools: List[Dict[str, Any]], messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        lo, hi = self.think_s
        if hi > 0:
            time.sleep(self.rng.uniform(lo, hi))
        last = None
        for m in reversed(messages):
            if m["role"] == "user" and isinstance(m["content"], list):
                for b in m["content"]:
                    if b.get("type") == "tool_result":
                        try:
                            last = json.loads(b["content"])
                        except (TypeError, ValueError):
                            last = None
                break
        try:
            action = self.gen.send(last) if self.started else next(self.gen)
            self.started = True
        except StopIteration:
            action = ("text", "Done.")
        if action[0] == "sql":
            return [{"type": "tool_use", "name": "run_sql", "input": {"sql": action[1]}}]
        if action[0] == "finish":
            return [{"type": "tool_use", "name": "finish", "input": {"status": action[1], "note": action[2]}}]
        return [{"type": "text", "text": action[1]}]


def fake_providers(inst: T.Instance, rep: int, episode_id: str, think_s: Tuple[float, float] = (0.005, 0.04),
                   styles: Optional[List[str]] = None) -> List[Tuple[Any, Any]]:
    """One FakeProvider per agent; agent k uses style STYLES[t][(k + rep) % len] unless ``styles`` is given."""
    out = []
    st = STYLES[inst.template]
    for k, a in enumerate(inst.agents):
        style = styles[k] if styles else st[(k + rep) % len(st)]
        out.append(make_provider("fake", dry_run=True, fake_policy=FakeSqlPolicy(inst, a, style, f"{episode_id}|{a}", think_s)))
    return out
