"""Per-agent SQLite sessions with a full statement log.

Each agent gets its OWN ``sqlite3`` connection to the episode's database file
(WAL mode), opened with ``isolation_level=None`` so the agent alone decides
BEGIN / COMMIT (no implicit transactions), ``cached_statements=0`` so every
statement is prepared (and seen by the authorizer) afresh, and a small busy
timeout (default 200 ms) so contention surfaces as real ``database is locked``
errors, returned verbatim.

``SqlSession.run(sql)`` splits the text into statements (sqlite3's own
``complete_statement``), executes them in order on the agent's connection and
stops at the first error. Every executed statement becomes one log entry:

    agent, call, stmt, sql, t_start, t_end (seconds since episode start),
    ok, error, error_name (e.g. SQLITE_BUSY_SNAPSHOT), busy (bool),
    rows_affected (DML only), n_rows (queries), txn_before, txn_after,
    access   {"read": {table: [cols]}, "insert": [...], "update": {table: [cols]},
              "delete": [...], "ddl": [[action, arg1, arg2]], "txn": [[op, name]],
              "pragma": [[name, value]], "functions": [...]}
    unique_guard  (only when the session has a unique probe) whether a UNIQUE
                  index on exactly the probed column existed after the statement

``access`` comes from the SQLite authorizer, so table and column identity is
exact (aliases, quoting and subqueries do not matter). The authorizer denies
ATTACH/DETACH (this also blocks ``VACUUM INTO``, which writes a new file) and
``load_extension``; nothing outside the episode's database file can be
touched.

When an agent ends with a transaction open, :meth:`SqlSession.close` rolls it
back and logs a ``harness_rollback`` entry.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_BUSY_TIMEOUT_S = 0.2
MAX_ROWS_SHOWN = 50
MAX_CELL_CHARS = 500

_A = {name: getattr(sqlite3, "SQLITE_" + name) for name in (
    "READ", "INSERT", "UPDATE", "DELETE", "TRANSACTION", "SAVEPOINT", "PRAGMA", "FUNCTION", "ATTACH", "DETACH",
    "CREATE_INDEX", "CREATE_TABLE", "CREATE_TRIGGER", "CREATE_VIEW", "DROP_INDEX", "DROP_TABLE", "DROP_TRIGGER",
    "DROP_VIEW", "ALTER_TABLE", "CREATE_TEMP_INDEX", "CREATE_TEMP_TABLE", "CREATE_TEMP_TRIGGER", "CREATE_TEMP_VIEW",
    "DROP_TEMP_INDEX", "DROP_TEMP_TABLE", "DROP_TEMP_TRIGGER", "DROP_TEMP_VIEW", "REINDEX", "ANALYZE",
) if hasattr(sqlite3, "SQLITE_" + name)}
_CODE_NAME = {v: k for k, v in _A.items()}
_DDL = {k for k in _A if k.startswith(("CREATE", "DROP", "ALTER", "REINDEX", "ANALYZE"))}
DENIED_FUNCTIONS = {"load_extension"}


def split_sql(sql: str) -> List[str]:
    """Split SQL text into statements using sqlite3.complete_statement.

    A trailing fragment without a semicolon is kept (SQLite runs it or reports
    the syntax error); fragments that are only whitespace or comments are dropped.
    """
    out: List[str] = []
    buf = ""
    for ch in sql:
        buf += ch
        if ch == ";" and sqlite3.complete_statement(buf):
            stmt = buf.strip()
            if not _only_comments(stmt.rstrip(";")):
                out.append(stmt)
            buf = ""
    if buf.strip() and not _only_comments(buf):
        out.append(buf.strip())
    return out


_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)


def _only_comments(s: str) -> bool:
    return not _COMMENT_RE.sub("", s).strip().strip(";").strip()


def is_busy(error: Optional[str], error_name: Optional[str] = None) -> bool:
    if error_name and error_name.startswith("SQLITE_BUSY"):
        return True
    e = (error or "").lower()
    return "database is locked" in e or "database table is locked" in e or "busy" in e


class EpisodeClock:
    def __init__(self) -> None:
        self.t0 = time.monotonic()

    def now(self) -> float:
        return round(time.monotonic() - self.t0, 4)


class SqlLog:
    """Thread-safe, append-only log of every statement in an episode (global order = append order)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.entries: List[Dict[str, Any]] = []

    def append(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            entry["seq"] = len(self.entries)
            self.entries.append(entry)

    def for_agent(self, agent: str) -> List[Dict[str, Any]]:
        with self._lock:
            return [e for e in self.entries if e["agent"] == agent]


def _cell(v: Any) -> Any:
    if isinstance(v, bytes):
        return f"<{len(v)} bytes>"
    if isinstance(v, str) and len(v) > MAX_CELL_CHARS:
        return v[:MAX_CELL_CHARS] + "..."
    return v


class SqlSession:
    """One agent's connection. ``run`` returns the tool result (a JSON-able dict)."""

    def __init__(self, path: str, agent: str, log: SqlLog, clock: EpisodeClock,
                 busy_timeout_s: float = DEFAULT_BUSY_TIMEOUT_S, unique_probe: Optional[Tuple[str, str]] = None) -> None:
        self.agent = agent
        self.log = log
        self.clock = clock
        self.unique_probe = unique_probe
        self.conn = sqlite3.connect(path, timeout=busy_timeout_s, isolation_level=None, check_same_thread=False,
                                    cached_statements=0)
        self._collect: Optional[Dict[str, Any]] = None
        self.conn.set_authorizer(self._authorize)
        self.calls = 0
        self.closed = False

    # -- authorizer -------------------------------------------------------
    def _authorize(self, action: int, arg1: Optional[str], arg2: Optional[str], dbname: Optional[str], source: Optional[str]) -> int:
        name = _CODE_NAME.get(action)
        if name in ("ATTACH", "DETACH"):
            return sqlite3.SQLITE_DENY
        if name == "FUNCTION" and (arg2 or "").lower() in DENIED_FUNCTIONS:
            return sqlite3.SQLITE_DENY
        acc = self._collect
        if acc is None:
            return sqlite3.SQLITE_OK
        if name == "READ" and arg1 and not arg1.startswith("sqlite_"):
            acc["read"].setdefault(arg1, set()).add(arg2 or "")
        elif name == "UPDATE" and arg1 and not arg1.startswith("sqlite_"):
            acc["update"].setdefault(arg1, set()).add(arg2 or "")
        elif name == "INSERT" and arg1 and not arg1.startswith("sqlite_"):
            acc["insert"].add(arg1)
        elif name == "DELETE" and arg1 and not arg1.startswith("sqlite_"):
            acc["delete"].add(arg1)
        elif name == "TRANSACTION":
            acc["txn"].append([arg1, None])
        elif name == "SAVEPOINT":
            acc["txn"].append(["SAVEPOINT_" + (arg1 or ""), arg2])
        elif name == "PRAGMA":
            acc["pragma"].append([arg1, arg2])
        elif name == "FUNCTION":
            acc["functions"].add((arg2 or "").lower())
        elif name in _DDL:
            acc["ddl"].append([name, arg1, arg2])
        return sqlite3.SQLITE_OK

    @staticmethod
    def _new_access() -> Dict[str, Any]:
        return {"read": {}, "insert": set(), "update": {}, "delete": set(), "ddl": [], "txn": [], "pragma": [],
                "functions": set()}

    @staticmethod
    def _freeze_access(acc: Dict[str, Any]) -> Dict[str, Any]:
        ddl, seen = [], set()
        for d in acc["ddl"]:
            key = tuple(d)
            if key not in seen:
                seen.add(key)
                ddl.append(d)
        return {"read": {t: sorted(c) for t, c in sorted(acc["read"].items())},
                "insert": sorted(acc["insert"]), "update": {t: sorted(c) for t, c in sorted(acc["update"].items())},
                "delete": sorted(acc["delete"]), "ddl": ddl, "txn": acc["txn"][:4], "pragma": acc["pragma"][:4],
                "functions": sorted(acc["functions"])}

    def _unique_guard(self) -> Optional[bool]:
        if self.unique_probe is None:
            return None
        table, col = self.unique_probe
        saved, self._collect = self._collect, None
        try:
            for row in self.conn.execute(f'PRAGMA index_list("{table}")').fetchall():
                idx_name, unique = row[1], row[2]
                if not unique:
                    continue
                cols = [r[2] for r in self.conn.execute(f'PRAGMA index_info("{idx_name}")').fetchall()]
                if cols == [col]:
                    return True
            return False
        except sqlite3.Error:
            return None
        finally:
            self._collect = saved

    # -- tool -------------------------------------------------------------
    def run(self, sql: Any) -> Dict[str, Any]:
        if self.closed:
            return {"ok": False, "error": "connection closed"}
        self.calls += 1
        if not isinstance(sql, str) or not sql.strip():
            return {"ok": False, "error": "run_sql needs a non-empty 'sql' string"}
        stmts = split_sql(sql)
        if not stmts:
            return {"ok": False, "error": "no SQL statement found"}
        results: List[Dict[str, Any]] = []
        for i, stmt in enumerate(stmts):
            entry, shown = self._execute(stmt, i)
            if not entry["ok"]:
                out: Dict[str, Any] = {"ok": False, "error": entry["error"], "failed_statement": stmt}
                if results:
                    out["completed"] = results
                if i + 1 < len(stmts):
                    out["not_run"] = len(stmts) - i - 1
                return out
            results.append(shown)
        return {"ok": True, "results": results}

    def _execute(self, stmt: str, index: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        self._collect = self._new_access()
        txn_before = self.conn.in_transaction
        t_start = self.clock.now()
        entry: Dict[str, Any] = {"agent": self.agent, "call": self.calls, "stmt": index, "sql": stmt,
                                 "t_start": t_start, "txn_before": txn_before}
        shown: Dict[str, Any] = {}
        try:
            cur = self.conn.execute(stmt)
            rows = cur.fetchall() if cur.description else None
            entry["ok"] = True
            if cur.description:
                cols = [d[0] for d in cur.description]
                shown["columns"] = cols
                shown["rows"] = [[_cell(v) for v in r] for r in rows[:MAX_ROWS_SHOWN]]
                if len(rows) > MAX_ROWS_SHOWN:
                    shown["rows_truncated"] = len(rows)
                entry["n_rows"] = len(rows)
            if cur.rowcount is not None and cur.rowcount >= 0:
                entry["rows_affected"] = cur.rowcount
                shown["rows_affected"] = cur.rowcount
            if not shown:
                shown["status"] = "ok"
        except sqlite3.Error as exc:
            entry["ok"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["error_name"] = getattr(exc, "sqlite_errorname", None)
        except (ValueError, OverflowError, MemoryError) as exc:  # e.g. huge integers in results
            entry["ok"] = False
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["error_name"] = None
        entry["t_end"] = self.clock.now()
        entry["txn_after"] = self.conn.in_transaction
        acc = self._freeze_access(self._collect)
        self._collect = None
        entry["access"] = acc
        entry["busy"] = (not entry["ok"]) and is_busy(entry.get("error"), entry.get("error_name"))
        if self.unique_probe is not None and entry["ok"]:
            entry["unique_guard"] = self._unique_guard()
        self.log.append(entry)
        return entry, shown

    def close(self) -> bool:
        """Roll back an open transaction (logged as ``harness_rollback``) and close. Returns True if one was open."""
        if self.closed:
            return False
        left_open = False
        try:
            if self.conn.in_transaction:
                left_open = True
                t = self.clock.now()
                self._collect = None
                try:
                    self.conn.execute("ROLLBACK")
                    ok, err = True, None
                except sqlite3.Error as exc:
                    ok, err = False, f"{type(exc).__name__}: {exc}"
                self.log.append({"agent": self.agent, "call": None, "stmt": None, "sql": "ROLLBACK", "harness_rollback": True,
                                 "t_start": t, "t_end": self.clock.now(), "txn_before": True,
                                 "txn_after": self.conn.in_transaction, "ok": ok, "error": err, "busy": False,
                                 "access": self._freeze_access(self._new_access())})
        finally:
            self.conn.close()
            self.closed = True
        return left_open
