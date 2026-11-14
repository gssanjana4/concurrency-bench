"""Classify each agent's SQL behavior from its statement log (see sqlenv.SqlSession).

Definitions (per agent; "issued" = the statement was sent, whatever its
outcome; "executed" = it ran without error):

Contended write
    an executed statement that INSERTs into or DELETEs from the template's
    target table, or UPDATEs one of its ``write_cols`` (tasks_sql.Target).
    Effective if rows_affected > 0. A write to another table (orders) is not
    contended.

A contended write is PROTECTED if any of these holds (all may be listed):
    txn         it ran inside a transaction (BEGIN [DEFERRED|IMMEDIATE|EXCLUSIVE]
                or SAVEPOINT) in which the agent had already executed a read of
                the target table. In WAL mode a deferred transaction whose
                snapshot is stale fails the write with SQLITE_BUSY_SNAPSHOT, so
                deferred counts too. Wrapping only the write (read before BEGIN)
                does not count.
    atomic      an UPDATE whose SET assigns an ``atomic_cols`` column from an
                expression that mentions that column or a subquery
                (SET v = v + 5, SET b = CASE WHEN b >= 60 THEN b - 60 ELSE b END).
    cas         an UPDATE/DELETE whose WHERE has an equality on a ``cas_cols``
                column (WHERE balance = 100, WHERE version = 3, WHERE owner = 'x').
                A threshold such as WHERE balance >= 60 with a literal SET is a
                conditional update but NOT protected (a later writer can still
                overwrite with a stale literal).
    guarded_insert  an INSERT that reads an ``insert_guard`` column of the target
                in the same statement (INSERT ... SELECT ... WHERE NOT EXISTS).
    constraint  (handle) a UNIQUE index on exactly the handle column existed when
                the INSERT ran, and the statement is not INSERT OR REPLACE /
                REPLACE / ON CONFLICT DO UPDATE (those overwrite the holder).
    A contended write with none of these is a BLIND write.
    "Protected" describes the agent's own statement, not the outcome: a version
    CAS is safe only if every other writer also bumps the version, and an
    in-place update without a threshold can still overdraw. Integrity is judged
    separately, on the final database (tasks_sql.check_integrity).

Per-agent flags (all booleans unless noted):
    read_target              executed a query (not a write) that read the target table
    used_txn                 issued BEGIN or a SAVEPOINT that opens a transaction
    txn_immediate            issued BEGIN IMMEDIATE or BEGIN EXCLUSIVE
    rmw_in_txn               some contended write was protected by ``txn``
    used_atomic_update       issued an UPDATE matching ``atomic``
    used_conditional_update  issued an UPDATE/DELETE on the target whose WHERE
                             mentions a ``cas_cols``/``atomic_cols`` column
                             (threshold or equality)
    used_cas                 issued an UPDATE/DELETE matching ``cas``
    used_guarded_insert      issued an INSERT matching ``guarded_insert``
    added_constraint         executed CREATE UNIQUE INDEX, CREATE TRIGGER, or a
                             CREATE TABLE containing UNIQUE or CHECK
    used_conflict_clause     issued INSERT OR <x>, REPLACE INTO or ON CONFLICT
    checked_rows_affected    used RETURNING or changes()/total_changes(), OR had
                             an executed guarded (atomic/cas/guarded_insert)
                             contended write that affected 0 rows and is not
                             ``false_success_after_zero`` (it did not report
                             success on the strength of a write that did nothing)
    false_success_after_zero claimed done although its last guarded write
                             affected 0 rows and nothing effective followed
    busy_errors (int)        statements that failed with SQLITE_BUSY*/locked
    retried_after_busy       after its first busy error, it executed a write,
                             BEGIN or COMMIT successfully
    set_busy_timeout         issued PRAGMA busy_timeout
    n_contended_writes (int) executed contended writes; n_effective (rows > 0)
    n_protected (int)        executed contended writes that were protected
    blind_write              some effective contended write was blind
    all_protected            had >= 1 effective contended write and all were protected
    mechanisms (list)        protection mechanisms seen on its contended writes
    left_txn_open            the harness rolled back its open transaction at the end
    atomic_pair              (order) a stock decrement and an orders INSERT
                             committed in the same transaction
    no_write                 issued no contended write

Commit tracking: a write executed outside a transaction commits at once; a
write inside one commits when a later executed statement ends the transaction
(txn_after False) and is not a ROLLBACK; a ROLLBACK, an error that ends the
transaction, or the harness rollback discards it.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from tasks_sql import AgentEffects, Instance, Target

FLAG_NAMES: Tuple[str, ...] = (
    "read_target", "used_txn", "txn_immediate", "rmw_in_txn", "used_atomic_update", "used_conditional_update",
    "used_cas", "used_guarded_insert", "added_constraint", "used_conflict_clause", "checked_rows_affected",
    "false_success_after_zero", "retried_after_busy", "set_busy_timeout", "blind_write", "all_protected",
    "left_txn_open", "atomic_pair", "no_write",
)

# --------------------------------------------------------------------------
# Light SQL text analysis (clause structure only; tables/columns come from the authorizer)
# --------------------------------------------------------------------------

_STR_RE = re.compile(r"'(?:[^']|'')*'")
_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_QUOTED_ID_RE = re.compile(r'"((?:[^"]|"")*)"|`([^`]*)`|\[([^\]]*)\]')


def clean_sql(sql: str) -> str:
    """Lower-case SQL with comments removed, string literals replaced by ?, identifier quotes dropped."""
    s = _COMMENT_RE.sub(" ", sql)
    s = _STR_RE.sub("?", s)
    s = _QUOTED_ID_RE.sub(lambda m: next(g for g in m.groups() if g is not None), s)
    return " ".join(s.lower().split())


def _depth0_positions(s: str, word: str) -> List[int]:
    out, depth = [], 0
    pat = re.compile(r"\b" + word + r"\b")
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and s.startswith(word, i) and pat.match(s, i):
            out.append(i)
    return out


def _clause(s: str, start_kw: str, end_kws: Tuple[str, ...]) -> str:
    starts = _depth0_positions(s, start_kw)
    if not starts:
        return ""
    a = starts[0] + len(start_kw)
    ends = [p for kw in end_kws for p in _depth0_positions(s, kw) if p > a]
    return s[a:min(ends)] if ends else s[a:]


def _split_depth0(s: str, sep: str = ",") -> List[str]:
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def first_keyword(sql: str) -> str:
    s = clean_sql(sql).lstrip("( ")
    m = re.match(r"[a-z]+", s)
    return m.group(0) if m else ""


def set_assignments(sql: str) -> Dict[str, str]:
    """UPDATE ... SET a = expr, b = expr -> {column: expr} (cleaned text)."""
    s = clean_sql(sql)
    sc = _clause(s, "set", ("from", "where", "returning", "order", "limit"))
    out: Dict[str, str] = {}
    for part in _split_depth0(sc):
        m = re.match(r"(?:[\w]+\.)?([\w]+)\s*=(.*)$", part, re.S)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def where_clause(sql: str) -> str:
    s = clean_sql(sql)
    return _clause(s, "where", ("returning", "order", "limit", "group", "on conflict"))


def is_atomic_update(sql: str, cols: Tuple[str, ...]) -> bool:
    if first_keyword(sql) not in ("update", "with"):
        return False
    for col, expr in set_assignments(sql).items():
        if col in cols and (re.search(r"\b" + re.escape(col) + r"\b", expr) or "select" in expr):
            return True
    return False


def where_mentions(sql: str, cols: Tuple[str, ...]) -> bool:
    w = where_clause(sql)
    return any(re.search(r"\b" + re.escape(c) + r"\b", w) for c in cols)


def where_equality(sql: str, cols: Tuple[str, ...]) -> bool:
    w = where_clause(sql)
    for c in cols:
        cq = re.escape(c)
        if re.search(r"\b(?:\w+\.)?" + cq + r"\s*(?:==|=(?!=)|\bis\b(?!\s+not))", w):
            return True
        if re.search(r"(?<![<>!=])==?\s*(?:\w+\.)?" + cq + r"\b", w):
            return True
    return False


def has_conflict_clause(sql: str) -> bool:
    s = clean_sql(sql)
    return bool(re.search(r"\binsert\s+or\s+(ignore|fail|abort|rollback|replace)\b|^\s*replace\s+into\b|\bon\s+conflict\b", s))


def overwrites_on_conflict(sql: str) -> bool:
    s = clean_sql(sql)
    return bool(re.search(r"\binsert\s+or\s+replace\b|^\s*replace\s+into\b|\bon\s+conflict\b.*\bdo\s+update\b", s))


def uses_rows_check(sql: str) -> bool:
    s = clean_sql(sql)
    return bool(re.search(r"\breturning\b|\bchanges\s*\(|\btotal_changes\s*\(", s))


def begin_kind(entry: Dict[str, Any]) -> Optional[str]:
    """'immediate' / 'exclusive' / 'deferred' / 'savepoint' if the statement opens a transaction."""
    s = clean_sql(entry["sql"])
    m = re.match(r"begin(?:\s+(deferred|immediate|exclusive))?\b", s)
    if m:
        return m.group(1) or "deferred"
    if re.match(r"savepoint\b", s) and not entry.get("txn_before"):
        return "savepoint"
    return None


def is_rollback(entry: Dict[str, Any]) -> bool:
    s = clean_sql(entry["sql"])
    return bool(re.match(r"rollback\b", s)) and not re.match(r"rollback\s+(transaction\s+)?to\b", s)


# --------------------------------------------------------------------------
# Entry predicates
# --------------------------------------------------------------------------


def contended(entry: Dict[str, Any], target: Target) -> bool:
    acc = entry.get("access") or {}
    t = target.table
    if t in acc.get("insert", []) or t in acc.get("delete", []):
        return True
    return bool(set(acc.get("update", {}).get(t, [])) & set(target.write_cols))


def reads_table(entry: Dict[str, Any], table: str) -> bool:
    return table in (entry.get("access") or {}).get("read", {})


def is_write(entry: Dict[str, Any]) -> bool:
    acc = entry.get("access") or {}
    return bool(acc.get("insert") or acc.get("delete") or acc.get("update"))


def statement_guard(entry: Dict[str, Any], target: Target) -> List[str]:
    """Statement-level protection mechanisms of a contended write (atomic / cas / guarded_insert / constraint)."""
    sql = entry["sql"]
    acc = entry.get("access") or {}
    mech = []
    is_ins = target.table in acc.get("insert", [])
    upd_or_del = bool(acc.get("update", {}).get(target.table)) or target.table in acc.get("delete", [])
    if upd_or_del and target.atomic_cols and is_atomic_update(sql, target.atomic_cols):
        mech.append("atomic")
    if upd_or_del and target.cas_cols and where_equality(sql, target.cas_cols):
        mech.append("cas")
    if is_ins and target.insert_guard and set(acc.get("read", {}).get(target.table, [])) & set(target.insert_guard):
        mech.append("guarded_insert")
    if is_ins and target.unique_col and entry.get("unique_guard") and not overwrites_on_conflict(sql):
        mech.append("constraint")
    return mech


def adds_constraint(entry: Dict[str, Any]) -> bool:
    if not entry.get("ok"):
        return False
    s = clean_sql(entry["sql"])
    if re.match(r"create\s+unique\s+index\b", s) or re.match(r"create\s+(temp\s+|temporary\s+)?trigger\b", s):
        return True
    return bool(re.match(r"create\s+table\b", s) and re.search(r"\bunique\b|\bcheck\s*\(", s))


# --------------------------------------------------------------------------
# Per-agent classification
# --------------------------------------------------------------------------


def annotate(entries: List[Dict[str, Any]], target: Target) -> List[Dict[str, Any]]:
    """Per-entry annotations for one agent (same order): committed, contended, mechanisms, protected."""
    ann: List[Dict[str, Any]] = []
    pending: List[int] = []
    reads_in_txn: set = set()
    for i, e in enumerate(entries):
        a: Dict[str, Any] = {"committed": False, "contended": False, "mechanisms": [], "protected": False}
        ok = bool(e.get("ok"))
        if ok and contended(e, target):
            a["contended"] = True
            mech = statement_guard(e, target)
            if e.get("txn_before") and target.table in reads_in_txn:
                mech = ["txn"] + mech
            a["mechanisms"] = mech
            a["protected"] = bool(mech)
        ann.append(a)
        # transaction bookkeeping
        if ok and e.get("txn_before") and reads_table(e, target.table):
            reads_in_txn.add(target.table)
        if ok and not e.get("txn_before") and e.get("txn_after") and reads_table(e, target.table):
            reads_in_txn.add(target.table)  # a statement that opened a transaction and read (rare)
        if ok and is_write(e):
            if e.get("txn_after"):
                pending.append(i)
            else:
                a["committed"] = True
        if e.get("txn_before") and not e.get("txn_after"):
            committed = ok and not is_rollback(e) and not e.get("harness_rollback")
            for j in pending:
                ann[j]["committed"] = committed
            pending = []
            reads_in_txn = set()
        if not e.get("txn_before") and not e.get("txn_after"):
            reads_in_txn = set()
    return ann


def classify_agent(entries: List[Dict[str, Any]], inst: Instance, claim: Optional[str]) -> Dict[str, Any]:
    target = inst.target
    ann = annotate(entries, target)
    f: Dict[str, Any] = {k: False for k in FLAG_NAMES}
    f["busy_errors"] = 0
    seen_busy = False
    mechanisms: set = set()
    n_cont = n_eff = n_prot = 0
    blind = False
    last_guarded_zero: Optional[int] = None
    effective_after_zero = False
    issued_contended = False
    for i, (e, a) in enumerate(zip(entries, ann)):
        if e.get("harness_rollback"):
            f["left_txn_open"] = True
            continue
        sql = e["sql"]
        ok = bool(e.get("ok"))
        acc = e.get("access") or {}
        kw = first_keyword(sql)
        if ok and reads_table(e, target.table) and not is_write(e):
            f["read_target"] = True
        bk = begin_kind(e)
        if bk:
            f["used_txn"] = True
            if bk in ("immediate", "exclusive"):
                f["txn_immediate"] = True
        on_target = bool(acc.get("update", {}).get(target.table)) or target.table in acc.get("delete", []) \
            or target.table in acc.get("insert", [])
        if not ok and kw in ("update", "delete", "insert", "replace", "with"):
            on_target = on_target or re.search(r"\b" + target.table + r"\b", clean_sql(sql)) is not None
        if on_target:
            issued_contended = True
        if on_target and kw in ("update", "delete", "with"):
            if target.atomic_cols and is_atomic_update(sql, target.atomic_cols):
                f["used_atomic_update"] = True
            if where_mentions(sql, tuple(target.cas_cols) + tuple(target.atomic_cols)):
                f["used_conditional_update"] = True
            if target.cas_cols and where_equality(sql, target.cas_cols):
                f["used_cas"] = True
        if on_target and target.table in acc.get("insert", []) and target.insert_guard \
                and set(acc.get("read", {}).get(target.table, [])) & set(target.insert_guard):
            f["used_guarded_insert"] = True
        if adds_constraint(e):
            f["added_constraint"] = True
        if kw in ("insert", "replace", "with") and has_conflict_clause(sql):
            f["used_conflict_clause"] = True
        if uses_rows_check(sql):
            f["checked_rows_affected"] = True
        if any((p[0] or "").lower() == "busy_timeout" for p in acc.get("pragma", [])) or \
                re.match(r"pragma\s+(main\.)?busy_timeout\b", clean_sql(sql)):
            f["set_busy_timeout"] = True
        if e.get("busy"):
            f["busy_errors"] += 1
            seen_busy = True
        elif ok and seen_busy and (is_write(e) or bk or re.match(r"(commit|end)\b", clean_sql(sql))):
            f["retried_after_busy"] = True
        if a["contended"]:
            n_cont += 1
            rows = e.get("rows_affected")
            effective = rows is None or rows > 0
            if effective:
                n_eff += 1
            if a["protected"]:
                n_prot += 1
                mechanisms.update(a["mechanisms"])
            elif effective:
                blind = True
            stmt_mech = [m for m in a["mechanisms"] if m in ("atomic", "cas", "guarded_insert")]
            if stmt_mech and rows == 0:
                last_guarded_zero = i
                effective_after_zero = False
            elif effective and last_guarded_zero is not None:
                effective_after_zero = True
    f["busy_errors"] = int(f["busy_errors"])
    if last_guarded_zero is not None:
        f["false_success_after_zero"] = claim == "done" and not effective_after_zero
        if not f["false_success_after_zero"]:
            f["checked_rows_affected"] = True
    f["rmw_in_txn"] = "txn" in mechanisms
    f["blind_write"] = blind
    f["all_protected"] = n_eff > 0 and not blind and n_prot >= 1
    f["no_write"] = not issued_contended
    if inst.template == "order":
        f["atomic_pair"] = _atomic_pair(entries, ann, target)
    f.update(n_contended_writes=n_cont, n_effective=n_eff, n_protected=n_prot, mechanisms=sorted(mechanisms),
             n_statements=sum(1 for e in entries if not e.get("harness_rollback")),
             n_errors=sum(1 for e in entries if not e.get("ok") and not e.get("harness_rollback")))
    return f


def _atomic_pair(entries: List[Dict[str, Any]], ann: List[Dict[str, Any]], target: Target) -> bool:
    """A committed stock decrement and a committed orders INSERT inside the same transaction."""
    txn_id, cur = [], 0
    for e in entries:
        if not e.get("txn_before") and e.get("txn_after"):
            cur += 1
        txn_id.append(cur if (e.get("txn_before") or e.get("txn_after")) else None)
    groups: Dict[int, Dict[str, bool]] = {}
    for e, a, t in zip(entries, ann, txn_id):
        if t is None or not a["committed"]:
            continue
        g = groups.setdefault(t, {"stock": False, "orders": False})
        rows = e.get("rows_affected")
        if a["contended"] and (rows is None or rows > 0):
            g["stock"] = True
        if "orders" in (e.get("access") or {}).get("insert", []) and (rows is None or rows > 0):
            g["orders"] = True
    return any(g["stock"] and g["orders"] for g in groups.values())


def committed_effects(entries: List[Dict[str, Any]], inst: Instance) -> AgentEffects:
    """Committed effects of one agent, for tasks_sql.check_integrity."""
    ann = annotate(entries, inst.target)
    eff = AgentEffects()
    for e, a in zip(entries, ann):
        if not a["committed"]:
            continue
        rows = e.get("rows_affected")
        effective = rows is None or rows > 0
        acc = e.get("access") or {}
        if a["contended"] and effective:
            eff.target_writes += 1
        if inst.template == "handle" and "users" in acc.get("insert", []) and effective:
            h = inst.params["handle"]
            if re.search(r"'" + re.escape(h) + r"'", e["sql"]):
                eff.handle_inserts += 1
        if inst.template == "order" and "orders" in acc.get("insert", []) and effective:
            eff.order_inserts += 1
    return eff
