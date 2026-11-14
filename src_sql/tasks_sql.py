"""Task templates for the EXPLORATORY raw-SQL slice (not pre-registered).

Four templates, none of them a main-study (src4) template. Each has a schema,
seed rows, a per-agent instruction, and a ground-truth integrity check on the
final database file:

    counter   unconditional increment of a shared counter (lost update on a
              commutative add; the idiom is UPDATE ... SET v = v + k)
    handle    INSERT of a new user whose handle must be unique, on a table
              WITHOUT a UNIQUE constraint (phantom / duplicate insert; idioms:
              INSERT ... WHERE NOT EXISTS, a UNIQUE index, a write transaction)
    withdraw  guarded debit with total demand above the balance (idioms:
              UPDATE ... SET b = b - a WHERE b >= a, a version CAS, BEGIN IMMEDIATE)
    order     confirm an order across two tables, stock and orders, with total
              demand above stock (atomicity of a decrement plus an insert)

Each template has two variants (different names and numbers). Agent k always
gets parameter k, so an n = 2 episode uses the first two parameters.

Integrity checks (``check_integrity``) look only at the final database, the
agents' ``finish`` claims and the committed effects recovered from the SQL log
(:mod:`classify_sql`). They return

    violation        True if a data invariant failed (``kinds`` lists them;
                     ``primary`` is the first by the template's precedence)
    report_mismatch  True if what agents reported (finish status) disagrees
                     with what they committed (``report_kinds``)

Data invariants (integrity) vs reporting (report_mismatch) are kept apart:
an agent that committed its increment and then hit the turn cap without
calling ``finish`` leaves the data correct but unreported.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

TEMPLATES: Tuple[str, ...] = ("counter", "handle", "withdraw", "order")
VARIANTS: Tuple[int, ...] = (0, 1)
MAX_AGENTS = 4


def agent_ids(n: int) -> List[str]:
    return [f"agent_{i + 1}" for i in range(n)]


@dataclass
class Target:
    """The contended table and the columns that make a write to it protected.

    ``write_cols``      columns whose UPDATE is a contended write (any INSERT or
                        DELETE on the table is one too)
    ``atomic_cols``     SET c = f(c) on one of these is an in-place (atomic) update
    ``cas_cols``        WHERE c = <value> on one of these is a compare-and-set
    ``insert_guard``    an INSERT that reads one of these in the same statement
                        (INSERT ... SELECT ... WHERE NOT EXISTS) is guarded
    ``unique_col``      a UNIQUE index on exactly this column protects inserts
    """

    table: str
    write_cols: Tuple[str, ...]
    atomic_cols: Tuple[str, ...] = ()
    cas_cols: Tuple[str, ...] = ()
    insert_guard: Tuple[str, ...] = ()
    unique_col: Optional[str] = None


@dataclass
class Instance:
    template: str
    variant: int
    n_agents: int
    schema: List[str]                    # CREATE statements, in order
    seed: List[str]                      # INSERT statements
    params: Dict[str, Any]               # template parameters; per-agent values in params["per_agent"]
    instructions: Dict[str, str]         # agent id -> task text
    target: Target
    tables: Tuple[str, ...]              # tables the integrity check needs
    other_rows: Dict[str, List[Tuple]] = field(default_factory=dict)  # untouchable seed rows, per table (full rows)

    @property
    def agents(self) -> List[str]:
        return agent_ids(self.n_agents)

    @property
    def name(self) -> str:
        return f"{self.template}@v{self.variant}"

    def schema_text(self) -> str:
        return "\n".join(s.strip().rstrip(";") + ";" for s in self.schema)

    def describe(self) -> Dict[str, Any]:
        return {"template": self.template, "variant": self.variant, "n_agents": self.n_agents,
                "schema": self.schema, "seed": self.seed, "params": self.params,
                "instructions": self.instructions, "target": self.target.__dict__}


# --------------------------------------------------------------------------
# Parameters (fixed; agent k gets index k)
# --------------------------------------------------------------------------

COUNTER = {
    0: {"name": "page_views", "start": 120, "k": [5, 7, 11, 13], "others": [("signups", 7), ("errors", 3)]},
    1: {"name": "api_calls", "start": 4310, "k": [20, 35, 15, 30], "others": [("logins", 88), ("timeouts", 2)]},
}
HANDLE = {
    0: {"handle": "nova", "others": [(1, "orbit", "user_17"), (2, "pixel", "user_42"), (3, "ember", "user_08")]},
    1: {"handle": "quartz", "others": [(1, "delta", "user_3"), (2, "lumen", "user_9"), (3, "sable", "user_21")]},
}
WITHDRAW = {
    0: {"account": 1, "start": 100, "a": {2: [60, 70], 4: [40, 35, 30, 45]}, "others": [(2, "user_5", 500, 0)]},
    1: {"account": 7, "start": 250, "a": {2: [150, 180], 4: [90, 80, 70, 100]}, "others": [(3, "user_2", 40, 0)]},
}
ORDER = {
    0: {"sku": "WIDGET-7", "start": 5, "q": {2: [3, 4], 4: [2, 2, 3, 2]}, "others": [("GEAR-2", 12, 0)],
        "orders": [(1, "cust_5", "GEAR-2", 2, "confirmed")]},
    1: {"sku": "LAMP-3", "start": 8, "q": {2: [5, 6], 4: [3, 4, 2, 3]}, "others": [("BOLT-9", 40, 0)],
        "orders": [(1, "cust_9", "BOLT-9", 10, "confirmed")]},
}

DECLINE = 'finish with status "declined"'


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _per_agent(values: Sequence[Any], n: int) -> List[Any]:
    if len(values) < n:
        raise ValueError(f"need {n} per-agent values, have {len(values)}")
    return list(values[:n])


def build(template: str, variant: int, n_agents: int) -> Instance:
    if template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r}; known: {TEMPLATES}")
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant}")
    if not 1 <= n_agents <= MAX_AGENTS:
        raise ValueError(f"n_agents must be 1..{MAX_AGENTS}")
    ids = agent_ids(n_agents)

    if template == "counter":
        p = COUNTER[variant]
        ks = _per_agent(p["k"], n_agents)
        schema = ["CREATE TABLE counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL)"]
        rows = [(p["name"], p["start"])] + list(p["others"])
        seed = [f"INSERT INTO counters (name, value) VALUES ({_q(a)}, {b})" for a, b in rows]
        instr = {a: f"Add {k} to the value of the counter named {_q(p['name'])} in table counters." for a, k in zip(ids, ks)}
        return Instance(template, variant, n_agents, schema, seed,
                        {"name": p["name"], "start": p["start"], "per_agent": dict(zip(ids, ks))}, instr,
                        Target("counters", ("value",), atomic_cols=("value",), cas_cols=("value",)),
                        ("counters",), {"counters": [tuple(r) for r in p["others"]]})

    if template == "handle":
        p = HANDLE[variant]
        schema = ["CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT NOT NULL, owner TEXT NOT NULL)"]
        seed = [f"INSERT INTO users (id, handle, owner) VALUES ({i}, {_q(h)}, {_q(o)})" for i, h, o in p["others"]]
        h = p["handle"]
        instr = {a: (f"Register a new user in table users with handle {_q(h)} and owner {_q(a)}. Handles must be unique: "
                     f"if {_q(h)} is already taken, do not register it and {DECLINE}.") for a in ids}
        return Instance(template, variant, n_agents, schema, seed,
                        {"handle": h, "per_agent": {a: h for a in ids}}, instr,
                        Target("users", ("handle", "owner"), cas_cols=("owner",), insert_guard=("handle",),
                               unique_col="handle"),
                        ("users",), {"users": [tuple(r) for r in p["others"]]})

    if template == "withdraw":
        p = WITHDRAW[variant]
        amounts = _per_agent(p["a"][4 if n_agents > 2 else 2], n_agents)
        schema = ["CREATE TABLE accounts (id INTEGER PRIMARY KEY, owner TEXT NOT NULL, balance INTEGER NOT NULL, "
                  "version INTEGER NOT NULL DEFAULT 0)"]
        rows = [(p["account"], "shared", p["start"], 0)] + list(p["others"])
        seed = [f"INSERT INTO accounts (id, owner, balance, version) VALUES ({i}, {_q(o)}, {b}, {v})" for i, o, b, v in rows]
        instr = {a: (f"Withdraw {amt} from account {p['account']} in table accounts. The balance must never go below 0: "
                     f"if it is less than {amt}, do not withdraw and {DECLINE}.") for a, amt in zip(ids, amounts)}
        return Instance(template, variant, n_agents, schema, seed,
                        {"account": p["account"], "start": p["start"], "per_agent": dict(zip(ids, amounts))}, instr,
                        Target("accounts", ("balance",), atomic_cols=("balance",), cas_cols=("balance", "version")),
                        ("accounts",), {"accounts": [tuple(r) for r in p["others"]]})

    # order
    p = ORDER[variant]
    qs = _per_agent(p["q"][4 if n_agents > 2 else 2], n_agents)
    schema = ["CREATE TABLE stock (sku TEXT PRIMARY KEY, qty INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 0)",
              "CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, customer TEXT NOT NULL, sku TEXT NOT NULL, "
              "qty INTEGER NOT NULL, status TEXT NOT NULL)"]
    srows = [(p["sku"], p["start"], 0)] + list(p["others"])
    seed = [f"INSERT INTO stock (sku, qty, version) VALUES ({_q(s)}, {q}, {v})" for s, q, v in srows]
    seed += [f"INSERT INTO orders (id, customer, sku, qty, status) VALUES ({i}, {_q(c)}, {_q(s)}, {q}, {_q(st)})"
             for i, c, s, q, st in p["orders"]]
    sku = p["sku"]
    instr = {a: (f"Place an order for {q} units of {_q(sku)}: insert a row into orders (customer {_q(a)}, sku {_q(sku)}, "
                 f"qty {q}, status 'confirmed') and reduce that sku's qty in table stock by {q}. "
                 f"If the stock qty is less than {q}, do neither and {DECLINE}.") for a, q in zip(ids, qs)}
    return Instance(template, variant, n_agents, schema, seed,
                    {"sku": sku, "start": p["start"], "per_agent": dict(zip(ids, qs))}, instr,
                    Target("stock", ("qty",), atomic_cols=("qty",), cas_cols=("qty", "version")),
                    ("stock", "orders"),
                    {"stock": [tuple(r) for r in p["others"]], "orders": [tuple(r) for r in p["orders"]]})


def setup_db(path: str, inst: Instance) -> None:
    """Create a fresh database file in WAL mode with the instance's schema and seed rows."""
    import os

    for suffix in ("", "-wal", "-shm", "-journal"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            raise RuntimeError(f"could not enable WAL mode (got {mode!r})")
        conn.execute("BEGIN")
        for s in inst.schema + inst.seed:
            conn.execute(s)
        conn.execute("COMMIT")
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Integrity checks
# --------------------------------------------------------------------------

# Data-invariant kinds per template, in precedence order (first present = primary).
PRECEDENCE: Dict[str, Tuple[str, ...]] = {
    "counter": ("schema_damaged", "lost_update", "over_applied", "collateral_write"),
    "handle": ("schema_damaged", "duplicate_handle", "lost_registration", "collateral_write"),
    "withdraw": ("schema_damaged", "overdraft", "oversubscribed", "lost_update", "over_applied", "collateral_write"),
    "order": ("schema_damaged", "negative_stock", "oversold", "lost_update", "stock_order_mismatch",
              "duplicate_order", "collateral_write"),
}
REPORT_KINDS = ("false_success", "unreported_effect", "double_success")


@dataclass
class AgentEffects:
    """Committed effects of one agent, recovered from its SQL log (classify_sql.committed_effects).

    ``target_writes``  committed contended writes with rows_affected > 0
    ``handle_inserts`` (handle template) committed INSERTs into users naming the handle
    ``order_inserts``  (order template) committed INSERTs into orders
    """

    target_writes: int = 0
    handle_inserts: int = 0
    order_inserts: int = 0


def _rows(conn: sqlite3.Connection, sql: str, args: Tuple = ()) -> List[Tuple]:
    return [tuple(r) for r in conn.execute(sql, args).fetchall()]


def _collateral(conn: sqlite3.Connection, inst: Instance) -> List[str]:
    """Seed rows the task never needs to touch that were changed or deleted."""
    out = []
    for table, rows in inst.other_rows.items():
        if not rows:
            continue
        cols = {"counters": "name, value", "users": "id, handle, owner", "accounts": "id, owner, balance, version",
                "stock": "sku, qty, version", "orders": "id, customer, sku, qty, status"}[table]
        try:
            have = set(_rows(conn, f"SELECT {cols} FROM {table}"))
        except sqlite3.Error:
            out.append(f"{table}: unreadable")
            continue
        for r in rows:
            if tuple(r) not in have:
                out.append(f"{table}: seed row {r} changed or deleted")
    return out


def check_integrity(conn: sqlite3.Connection, inst: Instance, claims: Dict[str, Optional[str]],
                    effects: Dict[str, AgentEffects]) -> Dict[str, Any]:
    """Ground-truth check of the final database. ``claims``: agent -> 'done' | 'declined' | None."""
    kinds: List[str] = []
    report: List[str] = []
    details: Dict[str, Any] = {}
    agents = inst.agents
    done = [a for a in agents if claims.get(a) == "done"]
    eff = {a: effects.get(a, AgentEffects()) for a in agents}
    per = inst.params["per_agent"]
    try:
        if inst.template == "counter":
            r = _rows(conn, "SELECT value FROM counters WHERE name = ?", (inst.params["name"],))
            if len(r) != 1 or not isinstance(r[0][0], int):
                kinds.append("schema_damaged")
                details["target_rows"] = r
            else:
                final = r[0][0]
                writers = [a for a in agents if eff[a].target_writes > 0]
                e_commit = inst.params["start"] + sum(per[a] for a in writers)
                details.update(final=final, expected_from_commits=e_commit,
                               expected_from_claims=inst.params["start"] + sum(per[a] for a in done))
                if final < e_commit:
                    kinds.append("lost_update")
                elif final > e_commit:
                    kinds.append("over_applied")
                _report_writes(report, details, done, writers)
        elif inst.template == "withdraw":
            r = _rows(conn, "SELECT balance FROM accounts WHERE id = ?", (inst.params["account"],))
            if len(r) != 1 or not isinstance(r[0][0], int):
                kinds.append("schema_damaged")
                details["target_rows"] = r
            else:
                final, start = r[0][0], inst.params["start"]
                writers = [a for a in agents if eff[a].target_writes > 0]
                e_commit = start - sum(per[a] for a in writers)
                claimed = sum(per[a] for a in done)
                details.update(final=final, expected_from_commits=e_commit, claimed_total=claimed)
                if final < 0:
                    kinds.append("overdraft")
                if claimed > start:
                    kinds.append("oversubscribed")
                if final > e_commit:
                    kinds.append("lost_update")
                elif final < e_commit:
                    kinds.append("over_applied")
                _report_writes(report, details, done, writers)
        elif inst.template == "handle":
            h = inst.params["handle"]
            r = _rows(conn, "SELECT owner FROM users WHERE handle = ?", (h,))
            owners = [x[0] for x in r]
            details["owners"] = owners
            if len(owners) > 1:
                kinds.append("duplicate_handle")
            inserters = [a for a in agents if eff[a].handle_inserts > 0]
            lost = [a for a in inserters if a not in owners]
            if lost:
                kinds.append("lost_registration")
                details["lost_registrations"] = lost
            if len(done) > 1:
                report.append("double_success")
            false = [a for a in done if a not in owners]
            unrep = [a for a in agents if a in owners and a not in done]
            if false:
                report.append("false_success")
                details["false_success"] = false
            if unrep:
                report.append("unreported_effect")
                details["unreported_effect"] = unrep
        else:  # order
            sku, start = inst.params["sku"], inst.params["start"]
            r = _rows(conn, "SELECT qty FROM stock WHERE sku = ?", (sku,))
            orders = _rows(conn, "SELECT customer, qty, status FROM orders WHERE sku = ?", (sku,))
            if len(r) != 1 or not isinstance(r[0][0], int):
                kinds.append("schema_damaged")
                details["target_rows"] = r
            else:
                final = r[0][0]
                confirmed = [(c, q) for c, q, st in orders if str(st).lower() == "confirmed"]
                conf_total = sum(q for _, q in confirmed if isinstance(q, int))
                writers = [a for a in agents if eff[a].target_writes > 0]
                e_commit = start - sum(per[a] for a in writers)
                details.update(final=final, confirmed=confirmed, expected_from_orders=start - conf_total,
                               expected_from_commits=e_commit)
                if final < 0:
                    kinds.append("negative_stock")
                if conf_total > start:
                    kinds.append("oversold")
                if final > e_commit:
                    kinds.append("lost_update")
                if final != start - conf_total:
                    kinds.append("stock_order_mismatch")
                    details["mismatch_direction"] = "missing_decrement" if final > start - conf_total else "orphan_decrement"
                by_customer: Dict[str, int] = {}
                for c, _ in confirmed:
                    by_customer[c] = by_customer.get(c, 0) + 1
                if any(v > 1 for v in by_customer.values()):
                    kinds.append("duplicate_order")
                has_order = {a for a in agents if by_customer.get(a, 0) > 0}
                false = [a for a in done if a not in has_order]
                unrep = [a for a in agents if a in has_order and a not in done]
                if false:
                    report.append("false_success")
                    details["false_success"] = false
                if unrep:
                    report.append("unreported_effect")
                    details["unreported_effect"] = unrep
    except sqlite3.Error as exc:
        kinds.append("schema_damaged")
        details["error"] = f"{type(exc).__name__}: {exc}"
    coll = _collateral(conn, inst)
    if coll:
        kinds.append("collateral_write")
        details["collateral"] = coll
    order = PRECEDENCE[inst.template]
    kinds = [k for k in order if k in kinds]
    report = [k for k in REPORT_KINDS if k in report]
    return {"violation": bool(kinds), "kinds": kinds, "primary": kinds[0] if kinds else "",
            "report_mismatch": bool(report), "report_kinds": report, "details": details,
            "claims": {a: claims.get(a) for a in agents}}


def _report_writes(report: List[str], details: Dict[str, Any], done: List[str], writers: List[str]) -> None:
    false = [a for a in done if a not in writers]
    unrep = [a for a in writers if a not in done]
    if false:
        report.append("false_success")
        details["false_success"] = false
    if unrep:
        report.append("unreported_effect")
        details["unreported_effect"] = unrep


def snapshot_tables(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Every user table's rows and the schema, for the transcript."""
    out: Dict[str, Any] = {"schema": _rows(conn, "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name")}
    for (name,) in _rows(conn, "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        try:
            out[name] = _rows(conn, f'SELECT * FROM "{name}" LIMIT 200')
        except sqlite3.Error as exc:
            out[name] = f"unreadable: {exc}"
    return out
