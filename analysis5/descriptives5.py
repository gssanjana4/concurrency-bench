#!/usr/bin/env python3
"""Pre-specified descriptive tables and figures for Study 2 (stdlib + matplotlib only; deterministic).

    python3 -I analysis5/descriptives5.py \\
        --base   study2_data/results5/study2 \\
        --results study2_data/analysis5/out_study2/results.json \\
        --numbers study2_data/analysis5/out_study2/numbers.tex \\
        --plan   src5/plan_study2.json \\
        --out    paper-concurrency/latex/study2_out \\
        --facts  paper-concurrency/latex/facts/src/study2_results_facts.md

Inputs are read only: the scored transcripts (``<base>/n2-*/transcripts``, ``<base>/probe-*/transcripts``), the spend
logs (``<base>/**/spend.jsonl``), the registered analysis (``results.json``: every registered estimate, interval, p and
claim comes from there, never recomputed here) and its ``numbers.tex`` (for the macro collision check and so that
tables can reference the registered macros), and ``src5/plan_study2.json`` for block membership (probe 0, core 1,
extension 4). Extension rows are descriptive only and enter no registered statistic; they are reported apart.

Outputs (``<out>``): ``tables/*.tex`` (booktabs, ACL widths, every value a macro), ``figures/*.pdf`` and ``.png``,
``study2_numbers.tex`` (one ``\\newcommand`` per descriptive number, prefix ``\\SiiD``; no name collides with the
registered ``numbers.tex`` or with ``latex/study2.tex``), ``study2_deviations.csv`` (the deviations skeleton the
table is built from) and ``descriptives.json`` (every computed value). The facts file lists every macro with its source.

Scope (registration, "Pre-specified descriptive (no test, no Holm)" and the checks): H1 rates per arm with the
registered Delta, primitive use per model x config x arm, outcome classes and flags, first-reply probes (H3) and the
leakage check, the exposure check, H4 rates with H4b, budget and spend, selection and exclusions, the deviations
skeleton, integrity vs ``none`` and the ``first_protective`` category under ``all_available``. No test is run here.

Determinism: sorted iteration everywhere, no timestamps, fixed RNG-free statistics, matplotlib metadata stripped.
Run twice and compare: the outputs are byte-identical.
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import os
import random
import re
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

os.environ.setdefault("SOURCE_DATE_EPOCH", "0")  # matplotlib: fixed PDF CreationDate (also stripped below)
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ---------------------------------------------------------------------------------------------------------------
# Registered identifiers (as analysis5/analyze5.py, so that macro names and short names agree)
# ---------------------------------------------------------------------------------------------------------------

QWEN = "openrouter:qwen/qwen3.6-27b-20260422"
HAIKU = "claude-haiku-4-5-20251001"
GPT = "openrouter:openai/gpt-5.5-20260423"
GEMINI = "openrouter:google/gemini-4-argon-20261013"
SONNET = "claude-sonnet-5"
FABLE = "claude-fable-5"
MODELS = (QWEN, HAIKU, SONNET, GPT, GEMINI, FABLE)  # display order: confirmatory first, then descriptive
CONFIRMATORY = (QWEN, HAIKU, SONNET)
DESCRIPTIVE = (GPT, GEMINI, FABLE)
SHORT = {QWEN: "Qwen", HAIKU: "Haiku", GPT: "Gpt", GEMINI: "Gemini", SONNET: "Sonnet", FABLE: "Fable"}
POOLED = "pooled"
# display names: the Study 1 numbers.tex macros (main.tex inputs numbers.tex) and the same strings for figures
NAME_MACRO = {QWEN: r"\ModelQwenName", HAIKU: r"\ModelHaikuName", SONNET: r"\ModelSonnetName", GPT: r"\ModelGPTName",
              GEMINI: r"\ModelGeminiName", FABLE: r"\ModelFableName"}
NAME_PLAIN = {QWEN: "Qwen3.6-27B", HAIKU: "Haiku 4.5", SONNET: "Sonnet 5", GPT: "GPT-5.5", GEMINI: "Gemini 4 Argon",
              FABLE: "Fable 5"}
PROVIDER_OF = {QWEN: "openrouter", GPT: "openrouter", HAIKU: "anthropic", SONNET: "anthropic", FABLE: "anthropic",
               GEMINI: "gemini"}
CONFIGS = ("none", "cas_available", "locks", "all_available")
CFG_SHORT = {"none": "None", "cas_available": "Cas", "locks": "Locks", "all_available": "All"}
H1_CONFIGS = ("cas_available", "locks", "all_available")
H4_CONFIGS = ("locks", "all_available")
LOCK_CONFIGS = ("locks", "all_available")
FAMILIES = ("inventory_last_unit", "transfer_shared_source", "budget_write_skew", "seat_same",
            "joint_account_write_skew", "inventory_still_valid", "ticket_same")
FAM_SHORT = {"inventory_last_unit": "Inv", "transfer_shared_source": "Xfer", "budget_write_skew": "Budget",
             "seat_same": "Seat", "joint_account_write_skew": "Joint", "inventory_still_valid": "Valid",
             "ticket_same": "Ticket"}
UPDATE_FAMILIES = ("inventory_last_unit", "inventory_still_valid", "transfer_shared_source", "budget_write_skew",
                   "joint_account_write_skew")
CLAIM_FAMILIES = ("seat_same", "ticket_same")
CONFIGS_FAMILY_ORDER = ("inventory_last_unit", "inventory_still_valid", "transfer_shared_source", "budget_write_skew",
                        "joint_account_write_skew", "seat_same", "ticket_same")  # update templates first, then claim templates
AGENT_ERROR_ENDS = ("truncated", "provider_error", "error")
REFUSAL_ENDS = ("refusal", "content_filter")
REFUSAL_STOPS = ("content_filter", "refusal")
REQUIRED_HOST = {QWEN: "alibaba"}
FLAGGED_HOST = {GPT: "openai"}
FLAG_COLS = ("missing_leg", "stale_overwrite", "lost_update", "write_skew", "guard_violation", "out_of_intent_write",
             "wrong_value", "laundered_cas")
PROVIDERS = ("anthropic", "openrouter", "gemini")
PROV_SHORT = {"anthropic": "Anthropic", "openrouter": "OpenRouter", "gemini": "Gemini"}
PROV_NAME = {"anthropic": "Anthropic (batch)", "openrouter": "OpenRouter (sync)", "gemini": "Google Gemini (batch)"}

# figures: Study 1 look (figures/make_figs.py): Okabe-Ito per model, one marker per model, no titles, ACL widths
COL_W, TEXT_W = 3.03, 6.30
# Gemini is a dark wine (not Okabe-Ito vermillion), so that it is not confused with Haiku's orange (reviews T8c C8, T7c A12)
MODEL_COLOR = {QWEN: "#0072B2", HAIKU: "#E69F00", GPT: "#009E73", GEMINI: "#882255", SONNET: "#56B4E9", FABLE: "#CC79A7"}
MODEL_MARKER = {QWEN: "o", HAIKU: "s", GPT: "^", GEMINI: "D", SONNET: "v", FABLE: "P"}
INK, MUTED, GRID = "#222222", "#666666", "#DDDDDD"
LOCK_COLOR, CAS_COLOR = "#0072B2", "#E69F00"  # validated adjacent pair (dataviz validator: deutan dE 29)

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7, "xtick.labelsize": 6, "ytick.labelsize": 6,
    "legend.fontsize": 6, "axes.edgecolor": MUTED, "axes.linewidth": 0.6, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.labelcolor": INK, "text.color": INK, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "pdf.fonttype": 42, "ps.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.02, "hatch.linewidth": 0.5,
})
PDF_META = {"CreationDate": None, "ModDate": None, "Producer": None, "Creator": None}
PNG_META = {"Software": None}


# ---------------------------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------------------------


def mean(xs: Sequence[float]) -> Optional[float]:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def share(flags: Iterable[Any]) -> Optional[float]:
    xs = [bool(x) for x in flags]
    return sum(xs) / len(xs) if xs else None


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def reply_codes(code: Any) -> Tuple[str, ...]:
    if not code or not isinstance(code, str):
        return ()
    return tuple(c for c in code.split("+") if c)


def host_norm(h: Any) -> str:
    return str(h or "").lower().replace(" ", "")


def tex_text(s: str) -> str:
    """Escape plain text for LaTeX (as make_numbers4.tex_text: underscores, ampersands, percent, hashes, dollars)."""
    out = str(s)
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_"), ("$", r"\$"),
                 ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")):
        out = out.replace(a, b)
    return out


_DIGITS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
           "8": "eight", "9": "nine"}


def macro(*parts: str) -> str:
    """``SiiD`` + capitalized parts, digits spelled out, non-letters dropped (same scheme as analyze5.macro)."""
    s = "SiiD" + "".join(p[:1].upper() + p[1:] for p in parts if p)
    s = "".join(_DIGITS.get(c, c) for c in s)
    return "".join(c for c in s if c.isalpha())


def reg_macro(*parts: str) -> str:
    """Name of a registered numbers.tex macro (analyze5.macro: ``Sii`` + parts)."""
    s = "Sii" + "".join(p[:1].upper() + p[1:] for p in parts if p)
    s = "".join(_DIGITS.get(c, c) for c in s)
    return "".join(c for c in s if c.isalpha())


def fnum(x: Optional[float], nd: int = 2) -> str:
    if x is None:
        return r"\textemdash{}"
    s = f"{x:.{nd}f}"
    if s.startswith("-") and float(s) == 0.0:
        s = s[1:]  # no negative zero
    return s.replace("-", "$-$") if s.startswith("-") else s


def fint(x: Optional[int]) -> str:
    if x is None:
        return r"\textemdash{}"
    return f"{int(x):,}".replace(",", "{,}")


def fmoney(x: Optional[float]) -> str:
    return r"\textemdash{}" if x is None else f"{x:.2f}"


def fp(p: Optional[float]) -> str:
    if p is None:
        return r"\textemdash{}"
    return "$<$0.001" if p < 0.001 else f"{p:.3f}"


# ---------------------------------------------------------------------------------------------------------------
# Loading and normalising transcripts (mirrors analyze5.normalize; extra descriptive fields)
# ---------------------------------------------------------------------------------------------------------------


def discover(base: str) -> List[str]:
    out = []
    for pat in ("n2-*", "probe-*"):
        for d in sorted(glob.glob(os.path.join(base, pat))):
            t = os.path.join(d, "transcripts")
            if os.path.isdir(t):
                out.append(t)
    return out


def reply_turns(raw: Mapping[str, Any]) -> List[List[Tuple[str, Optional[str], Optional[int]]]]:
    """Per assistant message of the transcript: the tool calls it carried as (tool, record_id, status), the status
    taken from the matching tool_result (None if the call was never executed). Used to tell whether two calls were
    sent in the same model reply (post hoc mechanism counts)."""
    pending: Dict[str, Tuple[int, int]] = {}
    turns: List[List[Tuple[str, Optional[str], Optional[int]]]] = []
    for m in raw.get("messages") or []:
        content = m.get("content")
        if m.get("role") == "assistant":
            cur: List[Tuple[str, Optional[str], Optional[int]]] = []
            turns.append(cur)
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        pending[str(c.get("id"))] = (len(turns) - 1, len(cur))
                        inp = c.get("input") or {}
                        cur.append((str(c.get("name")), inp.get("record_id") if isinstance(inp, dict) else None, None))
        elif isinstance(content, list):
            for c in content:
                if not (isinstance(c, dict) and c.get("type") == "tool_result"):
                    continue
                cc = c.get("content")
                if isinstance(cc, list):
                    cc = " ".join(x.get("text", "") for x in cc if isinstance(x, dict))
                try:
                    st = json.loads(cc).get("status") if isinstance(cc, str) else None
                except (ValueError, AttributeError):
                    st = None
                key = str(c.get("tool_use_id"))
                if key in pending:
                    ti, ci = pending[key]
                    tool, rid, _ = turns[ti][ci]
                    turns[ti][ci] = (tool, rid, st)
    return turns


def agent_view(s: Mapping[str, Any], raw: Mapping[str, Any], naive_writers: set) -> Dict[str, Any]:
    turns = raw.get("turns") or []
    pbc = s.get("protect_before_contention")
    n_sig = int(s.get("contention_signals") or 0)
    codes = reply_codes(raw.get("first_reply"))
    usage = raw.get("usage") or {}
    return {
        "final_text": str(raw.get("final_text") or ""), "reply_turns": reply_turns(raw),
        "rolled_back_agent": bool(s.get("rolled_back")), "valid_at_end": s.get("valid_at_end"),
        "reread_choice": bool(s.get("reread")), "missing_leg": bool(s.get("missing_leg")),
        # the frozen scorer's ``promote`` coordination choice: a committed conditional write-back of a record the intent
        # reads but does not write, whose new value equals its old value (score5.py; reviews T7b M-A, T8b N2)
        "promote": bool(s.get("promote")),
        "intent_text": str(raw.get("intent") or ""),
        "input_tokens": int(usage.get("input") or 0), "output_tokens": int(usage.get("output") or 0),
        "lock": bool(s.get("lock")), "lock_granted": bool(s.get("lock_granted")), "lock_effective": s.get("lock_effective"),
        "cas": bool(s.get("cas")), "fp": s.get("first_protective"), "prim": s.get("first_protective") is not None,
        "fp_call": s.get("first_protective_call"),
        "pbc": pbc, "signals": n_sig, "exposed": n_sig > 0, "at_risk": n_sig > 0 and pbc is not True,
        "reacting": n_sig > 0 and pbc is False, "lock_after": s.get("lock_after_contention") is True,
        "end": s.get("end_reason"), "fulfilled": bool(s.get("fulfilled")), "abandoned": bool(s.get("abandoned")),
        "give_up": bool(s.get("unnecessary_give_up")), "rolled_back": bool(s.get("rolled_back")),
        "turns": int(s.get("turns") or 0), "completions": int(raw.get("completions") or 0),
        "first_reply": raw.get("first_reply"), "fr_lock": "lock" in codes, "fr_cas": "cas" in codes,
        "fr_blind": "blind_write" in codes, "fr_prim": bool({"lock", "cas"} & set(codes)),
        "lock_waits": int(s.get("lock_waits") or 0), "lock_waits_423": int(s.get("lock_waits_423") or 0),
        "fenced_stale_basis": int(s.get("fenced_stale_basis") or 0), "fenced_unread_basis": int(s.get("fenced_unread_basis") or 0),
        "committed_writes": int(s.get("committed_writes") or 0), "naive": s.get("agent_id") in naive_writers,
        "last_stop": turns[-1].get("stop_reason") if turns else None, "truncated": bool(raw.get("truncated")),
        "temps": [t.get("temperature_effective") for t in turns],
        "hosts": [host_norm(t.get("served_host")) for t in turns],
        "served": [str(t.get("model_served")) for t in turns],
        "cost_usd": float(raw.get("cost_usd") or 0.0),
    }


def normalize(tr: Mapping[str, Any], path: str) -> Dict[str, Any]:
    t = tr.get("task") or {}
    factory = str(t.get("factory") or "")
    family = str(t.get("family") or factory.replace("_ctrl", ""))
    if family.endswith("_ctrl"):
        family = family[: -len("_ctrl")]
    arm = "control" if factory.endswith("_ctrl") or t.get("category") == "control" else "contended"
    sc = tr.get("score") or {}
    raw_agents = tr.get("agents") or {}
    # unprotected committed value-changing writes: neither expected_version nor a fencing token (ledger effects)
    naive_writers = set()
    for e in (tr.get("ledger") or {}).get("effects") or []:
        args = e.get("args") or {}
        if e.get("old_value") != e.get("new_value") and "expected_version" not in args and args.get("fencing_token") is None:
            naive_writers.add(e.get("agent_id"))
    agents = {a: agent_view(s, raw_agents.get(a) or {}, naive_writers) for a, s in sorted((sc.get("agents") or {}).items())}
    inter = sc.get("interleaving") or {}
    totals = tr.get("totals") or {}
    run_info = tr.get("run_info") or {}
    rec: Dict[str, Any] = {
        "id": tr.get("episode_id"), "path": path, "model": tr.get("model"), "config": tr.get("config"),
        "aware": int(bool(tr.get("concurrency_aware_prompt"))), "probe": bool(tr.get("probe")), "study": tr.get("study"),
        "dry_run": bool(tr.get("dry_run")), "n_agents": tr.get("n_agents"), "family": family, "arm": arm,
        "instance": int(t.get("instance", -1)), "seed": int(tr.get("seed", 0) or 0), "provider_family": tr.get("provider_family"),
        "fs": int(bool(sc.get("fs_nonserializable"))), "basis": int(bool(sc.get("dsg_basis_cycle"))),
        "dsg": int(bool(sc.get("dsg_cycle"))), "outcome": sc.get("outcome"), "stratum": sc.get("outcome_stratum"),
        "primary_label": sc.get("primary_label"), "cap_truncated": bool(sc.get("cap_truncated")),
        "flags": dict(sc.get("flags") or {}), "deadlock": bool(sc.get("deadlock")), "cap_endings": int(sc.get("cap_endings") or 0),
        "agent_errors": int(sc.get("agent_errors") or 0), "cross_agent_edges": int(sc.get("cross_agent_edges") or 0),
        "reads_overlap": inter.get("reads_overlap"), "rounds": int(sc.get("rounds") or 0), "stall": bool(sc.get("stall")),
        "cost_usd": float(totals.get("cost_usd") or 0.0), "completions": int(totals.get("completions") or 0),
        "order_key": (str(run_info.get("started_utc") or ""), os.path.basename(path)), "agents": agents,
        # slim ledger for the post hoc mechanism counts (every field is read, never recomputed)
        "wording": int(t.get("wording", 0) or 0), "intents": dict(t.get("intents") or {}),
        "committed_agents": list(sc.get("committed_agents") or []),
        "stale_overwrite_seqs": list(sc.get("stale_overwrite_seqs") or []),
        "fenced_stale_basis_seqs": list(sc.get("fenced_stale_basis_seqs") or []),
        "dsg_committed": int(bool(sc.get("dsg_cycle_committed"))), "dsg_g1c": int(bool(sc.get("dsg_g1c"))),
        "calls": [{"agent_id": c.get("agent_id"), "own_call": c.get("own_call"), "tool": c.get("tool"),
                   "record_id": c.get("record_id"), "status": c.get("status"), "reason": c.get("reason"),
                   "committed": bool(c.get("committed")), "effect_seq": c.get("effect_seq"),
                   "fencing_token": c.get("fencing_token"), "waited_rounds": int(c.get("waited_rounds") or 0),
                   "lease": (c.get("args") or {}).get("lease_calls") if c.get("tool") == "acquire_lock" else None,
                   "value": (c.get("response") or {}).get("value") if isinstance(c.get("response"), dict) else None,
                   "ver_body": isinstance(c.get("response"), dict) and "current_version" in c.get("response"),
                   # list_effects: the record ids of the effects the response listed (None for any other tool; review T6b N1)
                   "listed": ([str((x or {}).get("record_id")) for x in ((c.get("response") or {}).get("effects") or [])]
                              if c.get("tool") == "list_effects" and isinstance(c.get("response"), dict) else None)}
                  for c in (tr.get("ledger") or {}).get("calls") or []],
        "effect_agents": sorted({e.get("agent_id") for e in (tr.get("ledger") or {}).get("effects") or []}),
        # slim committed effects (ledger order): who wrote which record, whether the write changed the value, and whether
        # it carried expected_version (a no-op conditional write-back is the scorer's promotion)
        "effects": [{"agent_id": e.get("agent_id"), "record_id": e.get("record_id"), "seq": e.get("seq"),
                     "noop": e.get("old_value") == e.get("new_value"),
                     "cas": "expected_version" in (e.get("args") or {}), "new_value": e.get("new_value")}
                    for e in (tr.get("ledger") or {}).get("effects") or []],
        "initial": dict(t.get("initial") or {}),
        "final": {k: (v.get("value") if isinstance(v, dict) else v) for k, v in (tr.get("final_store") or {}).items()},
    }
    trig = []
    for a, av in agents.items():
        if av["end"] in AGENT_ERROR_ENDS or av["end"] in REFUSAL_ENDS or av["truncated"]:
            trig.append(f"{a}:{av['end'] if av['end'] in AGENT_ERROR_ENDS + REFUSAL_ENDS else 'truncated'}")
        if av["last_stop"] in REFUSAL_STOPS:
            trig.append(f"{a}:{av['last_stop']}")
    rec["exclusion_trigger"] = ";".join(sorted(set(trig))) or None
    hosts = sorted({h for av in agents.values() for h in av["hosts"]})
    rec["hosts"] = hosts
    rec["host_bad"] = rec["model"] in REQUIRED_HOST and any(not h.startswith(REQUIRED_HOST[rec["model"]]) for h in hosts)
    rec["host_flag"] = rec["model"] in FLAGGED_HOST and any(not h.startswith(FLAGGED_HOST[rec["model"]]) for h in hosts)
    return rec


def block_priority(rec: Mapping[str, Any], plan: Mapping[str, Any]) -> Optional[int]:
    """Lowest priority of a plan block that contains the row (0 probe, 1 core, 4 extension), or None (analyze5)."""
    best = None
    for b in plan.get("blocks", []):
        if b.get("model") != rec["model"] or (b.get("mode") == "probe") != rec["probe"]:
            continue
        if rec["config"] not in b.get("configs", []) or bool(rec["aware"]) not in [bool(x) for x in b.get("aware", [])]:
            continue
        if rec["family"] not in b.get("families", []) or not 0 <= rec["instance"] < int(b.get("instances", 0)):
            continue
        if not 0 <= rec["seed"] < int(b.get("schedules", 1)):
            continue
        if int(b.get("n", 2)) != rec["n_agents"]:
            continue
        best = int(b["priority"]) if best is None else min(best, int(b["priority"]))
    return best


def pair_key(rec: Mapping[str, Any], arm: Optional[str] = None) -> Tuple[Any, ...]:
    return (rec["model"], rec["config"], rec["aware"], rec["family"], rec["instance"], rec["seed"], rec["probe"], arm or rec["arm"])


def other_arm(arm: str) -> str:
    return "control" if arm == "contended" else "contended"


def select(recs: Sequence[Dict[str, Any]], plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Never-data rules, block membership, duplicates and the registered exclusion rule (analyze5.select)."""
    log: Dict[str, Any] = {"never_data": {}, "block": {}, "block_by_model": {}, "counts": {}, "excluded": []}

    def bump(d: Dict[str, int], k: str, n: int = 1) -> None:
        d[k] = d.get(k, 0) + n

    groups: Dict[str, List[Dict[str, Any]]] = {}
    ext: Dict[str, List[Dict[str, Any]]] = {}
    for r in recs:
        why = None
        if r["study"] not in (2, "2"):
            why = "not_study2"
        elif r["dry_run"]:
            why = "dry_run"
        elif r["config"] not in CONFIGS:
            why = f"unregistered_config:{r['config']}"
        elif r["model"] not in MODELS:
            why = "unregistered_model"
        elif r["n_agents"] != 2:
            why = "n_agents"
        if why:
            bump(log["never_data"], why)
            continue
        pr = block_priority(r, plan)
        r["priority"] = pr
        bump(log["block"], "unplanned" if pr is None else f"priority_{pr}")
        bump(log["block_by_model"], f"{SHORT[r['model']]}|{'unplanned' if pr is None else f'priority_{pr}'}")
        if pr in (0, 1):
            groups.setdefault(r["id"], []).append(r)
        elif pr == 4:
            ext.setdefault(r["id"], []).append(r)

    main: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    excluded: Dict[Tuple[Any, ...], str] = {}
    for eid in sorted(groups):
        tries = sorted(groups[eid], key=lambda r: r["order_key"])
        chosen = tries[0]
        if len(tries) > 1:
            bump(log["counts"], "duplicate_transcripts_ignored", len(tries) - 1)
        why = "wrong_host" if chosen["host_bad"] else ("agent_error_or_refusal" if chosen["exclusion_trigger"] else None)
        if why:
            excluded[pair_key(chosen)] = why
            bump(log["counts"], why)
        else:
            main[pair_key(chosen)] = chosen
    for k, why in sorted(excluded.items(), key=lambda kv: str(kv[0])):
        pk = k[:-1] + (other_arm(k[-1]),)
        if pk in main:
            main.pop(pk)
            excluded[pk] = f"partner_of:{why}"
            bump(log["counts"], "partner_excluded")
    log["excluded"] = [{"key": list(map(str, k)), "reason": v} for k, v in sorted(excluded.items(), key=lambda kv: str(kv[0]))]
    extension = {}
    for eid in sorted(ext):
        extension[pair_key(sorted(ext[eid], key=lambda r: r["order_key"])[0])] = sorted(ext[eid], key=lambda r: r["order_key"])[0]
    return {"main": main, "extension": extension, "log": log}


class Data:
    """Index of selected episodes and probes (analyze5.Data)."""

    def __init__(self, sample: Mapping[Tuple[Any, ...], Dict[str, Any]]):
        self.ep: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        self.pr: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for k, r in sorted(sample.items(), key=lambda kv: str(kv[0])):
            if r["probe"]:
                self.pr[(r["model"], r["config"], r["aware"], r["family"], r["instance"], r["arm"])] = r
            else:
                self.ep[(r["model"], r["config"], r["aware"], r["family"], r["instance"], r["seed"], r["arm"])] = r

    def clusters(self, model: str, config: str, aware: int = 0) -> List[Tuple[str, int]]:
        return sorted({(k[3], k[4]) for k in self.ep if k[0] == model and k[1] == config and k[2] == aware})

    def seeds(self, model: str, config: str, aware: int, fam: str, inst: int) -> List[int]:
        return sorted({k[5] for k in self.ep if k[:5] == (model, config, aware, fam, inst)})

    def pairs(self, model: str, config: str, fam: str, inst: int, aware: int = 0) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        out = []
        for s in self.seeds(model, config, aware, fam, inst):
            c = self.ep.get((model, config, aware, fam, inst, s, "contended"))
            k = self.ep.get((model, config, aware, fam, inst, s, "control"))
            if c is not None and k is not None:
                out.append((c, k))
        return out

    def episodes(self, model: str, config: str, aware: int, arm: str) -> List[Dict[str, Any]]:
        return [r for k, r in sorted(self.ep.items(), key=lambda kv: str(kv[0]))
                if k[0] == model and k[1] == config and k[2] == aware and k[6] == arm]

    def has_cell(self, model: str, config: str, aware: int) -> bool:
        return any(k[0] == model and k[1] == config and k[2] == aware for k in self.ep)


def agent_rate(eps: Sequence[Mapping[str, Any]], outcome: str) -> Optional[float]:
    vals = [bool(a[outcome]) for e in eps for a in e["agents"].values()]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------------------------------------------


def cluster_arm_rates(D: Data, model: str, config: str, aware: int, metric: str = "fs",
                      level: str = "episode") -> Dict[Tuple[str, int], Tuple[float, float]]:
    """Per cluster (family, instance): (contended rate, control rate) over its complete pairs; episode metric
    (0/1 per episode) or agent-level share (``level='agent'``). The registered Delta is the mean of the differences."""
    out = {}
    for fam, inst in D.clusters(model, config, aware):
        p = D.pairs(model, config, fam, inst, aware)
        if not p:
            continue
        if level == "episode":
            rc, rk = mean([c[metric] for c, _ in p]), mean([k[metric] for _, k in p])
        else:
            rc, rk = agent_rate([c for c, _ in p], metric), agent_rate([k for _, k in p], metric)
        if rc is not None and rk is not None:
            out[(fam, inst)] = (rc, rk)
    return out


def cell_rates(cl: Mapping[Tuple[str, int], Tuple[float, float]]) -> Dict[str, Any]:
    if not cl:
        return {"cont": None, "ctrl": None, "delta": None, "clusters": 0}
    c = mean([v[0] for v in cl.values()])
    k = mean([v[1] for v in cl.values()])
    return {"cont": c, "ctrl": k, "delta": mean([v[0] - v[1] for v in cl.values()]), "clusters": len(cl)}


def pooled_rates(per_model: Mapping[str, Mapping[Tuple[str, int], Tuple[float, float]]]) -> Dict[str, Any]:
    """Equal-weight pooled cluster values on the clusters that enter for every pooled model (analyze5.intersect)."""
    models = sorted(per_model)
    if not models:
        return {"cont": None, "ctrl": None, "delta": None, "clusters": 0, "models": []}
    keys = set(per_model[models[0]])
    for m in models[1:]:
        keys &= set(per_model[m])
    cl = {k: (mean([per_model[m][k][0] for m in models]), mean([per_model[m][k][1] for m in models])) for k in sorted(keys)}
    r = cell_rates(cl)
    r["models"] = [SHORT[m] for m in models]
    return r


def primitive_use(eps: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Agent shares and episode counts for one cell and arm (every kept episode of the cell)."""
    agents = [a for e in eps for a in e["agents"].values()]
    n = len(agents)
    eff = [a["lock_effective"] for a in agents if a["lock_effective"] is not None]
    fp = {c: sum(1 for a in agents if a["fp"] == c) for c in ("lock", "cas")}
    fp["none"] = sum(1 for a in agents if a["fp"] is None)
    return {
        "episodes": len(eps), "agents": n,
        "lock": share(a["lock"] for a in agents), "lock_granted": share(a["lock_granted"] for a in agents),
        "lock_effective": share(eff) if eff else None, "lock_effective_n": len(eff),
        "cas": share(a["cas"] for a in agents), "prim": share(a["prim"] for a in agents),
        "naive": share(a["naive"] for a in agents),
        "fp_lock": fp["lock"] / n if n else None, "fp_cas": fp["cas"] / n if n else None, "fp_none": fp["none"] / n if n else None,
        "preemptive": share(a["pbc"] is True for a in agents), "reactive": share(a["pbc"] is False for a in agents),
        "never": share(a["pbc"] is None for a in agents), "lock_after_n": sum(1 for a in agents if a["lock_after"]),
        "lock_after": share(a["lock_after"] for a in agents),
        "exposed": share(a["exposed"] for a in agents), "at_risk": share(a["at_risk"] for a in agents),
        "at_risk_n": sum(1 for a in agents if a["at_risk"]), "reacting_n": sum(1 for a in agents if a["reacting"]),
        "fulfilled": share(a["fulfilled"] for a in agents), "abandoned_n": sum(1 for a in agents if a["abandoned"]),
        "abandoned": share(a["abandoned"] for a in agents), "give_up_n": sum(1 for a in agents if a["give_up"]),
        "completions": mean([a["completions"] for a in agents]),
        "turns": mean([a["turns"] for a in agents]),
        "lock_waits_423": sum(a["lock_waits_423"] for a in agents), "lock_waits": sum(a["lock_waits"] for a in agents),
        "fenced_stale_basis_agents": sum(1 for a in agents if a["fenced_stale_basis"] > 0),
        "fenced_unread_basis_agents": sum(1 for a in agents if a["fenced_unread_basis"] > 0),
        "cap_truncated": sum(1 for e in eps if e["cap_truncated"]), "cap_endings": sum(e["cap_endings"] for e in eps),
        "deadlock": sum(1 for e in eps if e["deadlock"]), "agent_errors": sum(e["agent_errors"] for e in eps),
        "refusals": sum(1 for a in agents if a["end"] in REFUSAL_ENDS),
        "not_returned": sum(1 for a in agents if a["end"] != "returned"),
        "cost_usd": sum(e["cost_usd"] for e in eps),
    }


def outcome_classes(eps: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    n = len(eps)
    out: Dict[str, Any] = {"episodes": n}
    for c in ("clean", "compensated", "failed"):
        out[c] = (sum(1 for e in eps if e["outcome"] == c) / n) if n else None
        out[c + "_n"] = sum(1 for e in eps if e["outcome"] == c)
    for f in FLAG_COLS + ("compensated_after_violation", "ever_violated", "violated_at_end", "fenced_stale_basis"):
        out["flag_" + f] = (sum(1 for e in eps if e["flags"].get(f)) / n) if n else None
        out["flag_" + f + "_n"] = sum(1 for e in eps if e["flags"].get(f))
    out["fs"] = mean([e["fs"] for e in eps])
    out["basis"] = mean([e["basis"] for e in eps])
    out["dsg"] = mean([e["dsg"] for e in eps])
    out["cap_truncated_n"] = sum(1 for e in eps if e["cap_truncated"])
    out["deadlock_n"] = sum(1 for e in eps if e["deadlock"])
    out["agent_errors_n"] = sum(e["agent_errors"] for e in eps)
    agents = [a for e in eps for a in e["agents"].values()]
    out["refusal_n"] = sum(1 for a in agents if a["end"] in REFUSAL_ENDS)
    out["fulfilled"] = share(a["fulfilled"] for a in agents)
    out["reads_overlap"] = share(e["reads_overlap"] for e in eps if e["reads_overlap"] is not None)
    labels: Dict[str, int] = {}
    for e in eps:
        if e["outcome"] == "failed":
            labels[str(e["primary_label"])] = labels.get(str(e["primary_label"]), 0) + 1
    out["primary_labels"] = dict(sorted(labels.items()))
    return out


def probe_cell(D: Data, model: str, config: str, aware: int) -> Dict[str, Any]:
    """First-reply codes of the probes of one (model, config, aware) cell: a0 contended, a1 contended, a1 control."""
    units = sorted({(k[3], k[4]) for k in D.pr if k[0] == model and k[1] == config and k[2] == aware})
    a0c, a1c, a1k, a0cas, a0blind, both = [], [], [], [], [], 0
    for fam, inst in units:
        c = D.pr.get((model, config, aware, fam, inst, "contended"))
        k = D.pr.get((model, config, aware, fam, inst, "control"))
        if c and "a0" in c["agents"]:
            a0c.append(c["agents"]["a0"]["fr_lock"])
            a0cas.append(c["agents"]["a0"]["fr_cas"])
            a0blind.append(c["agents"]["a0"]["fr_blind"])
        if c and "a1" in c["agents"]:
            a1c.append(c["agents"]["a1"]["fr_lock"])
        if k and "a1" in k["agents"]:
            a1k.append(k["agents"]["a1"]["fr_lock"])
        if c and k and "a1" in c["agents"] and "a1" in k["agents"]:
            both += 1
    return {"units": len(units), "a0_lock": share(a0c), "a0_cas": share(a0cas), "a0_blind": share(a0blind),
            "a1_cont_lock": share(a1c), "a1_ctrl_lock": share(a1k), "a1_pairs": both, "a0_n": len(a0c)}


# ---------------------------------------------------------------------------------------------------------------
# Registered analysis (results.json, numbers.tex)
# ---------------------------------------------------------------------------------------------------------------


def load_registered(results_path: str, numbers_path: str) -> Dict[str, Any]:
    res = json.load(open(results_path))
    tests = {t["id"]: t for t in res["tests"]}
    names = set()
    with open(numbers_path) as f:
        for line in f:
            m = re.match(r"\\newcommand\{\\([A-Za-z]+)\}", line)
            if m:
                names.add(m.group(1))
    return {"res": res, "tests": tests, "macros": names, "results_sha256": sha256_file(results_path),
            "numbers_sha256": sha256_file(numbers_path)}


def short_claim(t: Optional[Mapping[str, Any]], kind: str) -> str:
    """Registered claim words for a table cell (the numbers stay in the registered macros)."""
    if t is None:
        return "not run"
    st = t.get("status")
    if st == "descriptive":
        return "descriptive"
    cl = str(t.get("claim") or "")
    if kind == "H1":
        if cl.startswith("Contention added integrity failures, by less than"):
            return "added failures, by less than $\\delta$"
        if cl.startswith("Contention added integrity failures"):
            return "added failures"
        if cl.startswith("Contention did not add"):
            return "at most $\\pm\\delta$"
        if cl.startswith("Inconclusive"):
            return "inconclusive"
    if kind == "H4":
        if "uninformative" in cl:
            return "inconclusive ($q\\leq\\delta$, uninformative)"
        if cl.startswith("Contention added primitive uptake, by less than"):
            return "added uptake, by less than $\\delta$"
        if cl.startswith("Contention added primitive uptake"):
            return "added uptake"
        if cl.startswith("Contention did not add"):
            return "at most $\\pm\\delta$"
        if cl.startswith("Inconclusive"):
            return "inconclusive"
    if kind == "H3":
        if cl.startswith("The notice raised"):
            return "raised first-reply lock use"
        if cl.startswith("No claim"):
            return "no claim"
    return tex_text(cl) if cl else st.replace("_", " ")


# ---------------------------------------------------------------------------------------------------------------
# Spend logs and run-log facts
# ---------------------------------------------------------------------------------------------------------------


def spend_by_provider(base: str) -> Dict[str, Any]:
    """Every Study 2 spend.jsonl under base (lanes and preflight): cost per provider family, per model, per lane."""
    prov: Dict[str, float] = {}
    model: Dict[str, float] = {}
    lane: Dict[str, float] = {}
    n = 0
    for sp in sorted(glob.glob(os.path.join(base, "**", "spend.jsonl"), recursive=True)):
        if os.sep + "dry_run" + os.sep in sp or os.path.basename(os.path.dirname(sp)) == "rehearsal":
            continue
        ln = os.path.relpath(os.path.dirname(sp), base)
        with open(sp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                c = float(e.get("cost_usd") or 0.0)
                n += 1
                prov[e.get("provider_family") or "?"] = prov.get(e.get("provider_family") or "?", 0.0) + c
                model[e.get("model") or "?"] = model.get(e.get("model") or "?", 0.0) + c
                lane[ln] = lane.get(ln, 0.0) + c
    return {"provider": dict(sorted(prov.items())), "model": dict(sorted(model.items())), "lane": dict(sorted(lane.items())),
            "entries": n}


def provider_failure_episodes(base: str) -> int:
    """Distinct episode ids with at least one failed attempt (failures.jsonl lines, all lanes)."""
    ids = set()
    for p in sorted(glob.glob(os.path.join(base, "n2-*", "failures.jsonl")) + glob.glob(os.path.join(base, "probe-*", "failures.jsonl"))):
        with open(p) as f:
            for line in f:
                try:
                    ids.add(json.loads(line).get("episode_id", "?"))
                except ValueError:
                    pass
    return len(ids)


def provider_failures(base: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for p in sorted(glob.glob(os.path.join(base, "n2-*", "failures.jsonl")) + glob.glob(os.path.join(base, "probe-*", "failures.jsonl"))):
        with open(p) as f:
            for line in f:
                try:
                    eid = json.loads(line).get("episode_id", "?")
                except ValueError:
                    eid = "?"
                parts = str(eid).split("__")
                k = "|".join(parts[:2]) if len(parts) >= 2 else "unparsed"
                out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------------------------------------------
# Deviations table (from paper-concurrency/STUDY2_RUN_LOG.md, the transcripts and results.json; completed after the
# T5 to T8 reviews, 2026-11-09). Placeholders in braces are filled from the data by main(). Rows marked "note" in the
# first cell are not departures from the registration text; they are listed because the registration's reporting rules
# ask for them (provider failures per cell, extension blocks apart, every registered item reported or listed as not done).
# ---------------------------------------------------------------------------------------------------------------

DEVIATIONS = [
    {
        "deviation": "Text error in the registration's Declared confounds: 'Haiku applies [temperature 0]'. The Anthropic API rejected "
                     "the temperature parameter for claude-haiku-4-5-20251001 in the batch path (invalid_request_error: 'temperature: "
                     "Extra inputs are not permitted'), as it did for claude-sonnet-5 and claude-fable-5 and for all three Claude models "
                     "in Study 1. The frozen driver's registered handling applied: after the first rejection the requests were resent "
                     "without the parameter and temperature_effective is logged null.",
        "reason": "Provider behaviour: the API refuses the parameter for these models. No procedure changed.",
        "before_after": "First Haiku probe batch (2026-11-09 18:46 UTC), before any result existed; the handling is the frozen driver's "
                        "rule, not a decision.",
        "effect": "Text only. All three Claude models ran at the provider default: temperature_effective is null in every one of the "
                  "{HaikuNull} Haiku, {SonnetNull} Sonnet and {FableNull} Fable completions, and no completion carries the value 0. The "
                  "run log's note that early Haiku probe batches mixed both settings is not supported by the transcripts: the first paid "
                  "Haiku batch errored in full (66 of 66 requests) and was resent without the parameter, and the stored record cannot "
                  "distinguish a request sent with the parameter from one sent without it, so every Claude completion is reported at "
                  "the provider default. Analysis unchanged.",
        "registered_result": "Not available: the API does not accept the parameter. The confound entry should read 'all three Claude "
                             "models reject it and run at the provider default (Study 1 found the same)'.",
    },
    {
        "deviation": "Analyst exposure, declared: while diagnosing the errored Anthropic requests, the AI assistant printed the first "
                     "record of probe-anthropic/batch_state/.../responses.jsonl, which showed the opening sentence of one Haiku a1 probe "
                     "reply (episode claude-haiku-4-5-20251001__all_available__inventory_last_unit_ctrl@i0, a control probe). No outcome, "
                     "label or score was read; later inspections were filtered to error objects and metadata.",
        "reason": "Debugging the temperature rejection in the first probe batches.",
        "before_after": "During the probe block, before eligibility.json was computed and before any episode result was opened.",
        "effect": "None on data or analysis: the analysis code was frozen before any spend, and the eligibility step reads probes by "
                  "rule from the frozen script.",
        "registered_result": "Not applicable.",
    },
    {
        "deviation": "Note (not a departure): timing of the eligibility step. eligibility.json was computed at 2026-11-09 22:22 UTC from "
                     "the {ProbeFiles} probe transcripts, after every probe block had ended, and posted to the OSF project at 23:08 UTC "
                     "(sha256 f4ad4f07...), while the core blocks were already running because the runner executes blocks back to back. "
                     "The registration says the file is posted when the probe block ends, which it was.",
        "reason": "The lanes run probes and core episodes without a pause; no lane was stopped.",
        "before_after": "Before any episode result was opened (STUDY2_RUN_LOG.md): the file is produced by the frozen script without "
                        "change, and the analysis refused to run without its posted sha256. The registered analysis ran after the whole "
                        "run had ended (2026-11-10 04:12 UTC) and the results were first opened after that.",
        "effect": "None: the eligibility rates depend on probes only.",
        "registered_result": "As registered.",
    },
    {
        "deviation": "Note (not a departure): registration-to-first-call interval. The registration was filed at 2026-11-09 18:35:24 "
                     "UTC; the queued job on the author's machine started the run script at 18:36 UTC (freeze check, validity gate "
                     "and preflight) and the three lanes started at 18:40 UTC.",
        "reason": "The run was queued to start once the registration existed; the frozen plan, hashes and analysis were fixed before "
                  "filing.",
        "before_after": "Before any paid call.",
        "effect": "None.",
        "registered_result": "As registered.",
    },
    {
        "deviation": "Note (not a departure): provider failures, reported per cell as the Data inclusion rules require. {ProvFailTotal} "
                     "failed attempts on {ProvFailEpisodes} GPT-5.5 episode ids (none / locks / all_available: {ProvFailNone} / "
                     "{ProvFailLocks} / {ProvFailAll}), all OpenRouter 502 provider_unavailable between 23:23 and 23:34 UTC; the lane "
                     "stopped after three consecutive failures, waited and re-ran. Every affected episode was written later as a fresh run "
                     "(retried_requests null), never replaced. No other model had a provider failure.",
        "reason": "Provider outage; the registered retry rule operated.",
        "before_after": "During the run; no result was read.",
        "effect": "None on the data: aborted attempts are in the spend log, not in the transcripts. GPT-5.5 is descriptive.",
        "registered_result": "As registered.",
    },
    {
        "deviation": "Note (not a departure): GPT-5.5 completions from a non-OpenAI host. The host was not pinned, as registered; "
                     "{GptAzureEpisodes} core episodes ({GptAzureCompletions} completions over all blocks) were served through Azure. They "
                     "are kept and flagged, and sensitivity 5 drops them.",
        "reason": "OpenRouter routing (declared confound 'Provider routing').",
        "before_after": "During the run; flagged by the registered analysis.",
        "effect": "No registered verdict exists for GPT-5.5. Its descriptive calibration estimate under none moves from "
                  "{GptCalNoneEst} to {GptCalNoneEstSFive} ({GptClusters} clusters) and its H2c estimate from {GptHtwoCEst} to "
                  "{GptHtwoCEstSFive} when the three episodes are dropped; the sensitivity changed {SensFiveChanged} verdicts.",
        "registered_result": "The flagged episodes stay in every descriptive table; the dropped-host values are listed here.",
    },
    {
        "deviation": "Note (not a departure): extension blocks. The planner's priority-4 blocks ran while money was left: {ExtFiles} "
                     "episodes beyond the registered core table ({GptExt} GPT-5.5: instance 2 of the three common families and the "
                     "seat_same family; {FableExt} Fable 5: more instances, schedules and families). They enter no registered statistic "
                     "and are reported apart (extension table in the appendix).",
        "reason": "Registered: 'Priority-4 extension blocks run only while money is left. They are descriptive and never enter a "
                  "statistic of H1 to H4.'",
        "before_after": "During the run.",
        "effect": "None on any registered number.",
        "registered_result": "As registered.",
    },
    {
        "deviation": "Tool-text inaccuracies frozen into the transcripts (the registration governs where code and text disagree, and "
                     "every frozen text is data). (a) The acquire_lock description says 'writes to the record are accepted only if "
                     "they carry this fencing_token (writes without it get 423)'; the implementation returns 423 only to a non-holder "
                     "while a lock is live, 428 to the holder without its token, and accepts a tokenless write on an unlocked record, so "
                     "the sentence reads as if every write under locks needed a token. (b) The lease_expired text 'your lock on X has "
                     "ended' is also returned to a non-holder that presents the latest ended token of a record. (c) Under all_available "
                     "the 423 body carries 'current version is N' ({LockedWithVersion} such responses), the one rejection that reveals "
                     "a version, against the neutral-rejection principle of the 409 text.",
        "reason": "Found in the pre-spend review V1b (a, b) and in review T5 (c) after the run; frozen before the run.",
        "before_after": "Frozen before any paid call; found after. No frozen file changed.",
        "effect": "(a) applies equally to both arms, so H4 and the leakage check are unaffected; it inflates absolute lock use under "
                  "locks and all_available for agents that read the sentence as a requirement, which bears on H2a to H2c and on the "
                  "Study 1 to Study 2 comparison of lock rates (which the registration forbids anyway). (b) fired once in the study "
                  "(one lease_expired 409). (c) names a version to {LockedWithVersion} agents' rejected writes.",
        "registered_result": "Not available without a new run; stated as a limitation and as a confound of the lock-use rates.",
    },
    {
        "deviation": "Registered items reported outside the frozen analysis or not done. Reported by the descriptive script "
                     "(descriptives5.py, not frozen): the reads_overlap share per cell and arm; the percentile-count bootstrap p, exact "
                     "sign test, 90 % and 95 % intervals, bootstrap-t and Holm-consistent intervals and the template-level sensitivity "
                     "for every test (all read from results.json); the three graph verdicts; the per-family breakdown of the primary "
                     "measure and of exposure and the per-wording breakdown of the primary measure (not of every measure); lease-length, "
                     "lock-wait, deadlock, within-prompt-variance, cost, token, turn, reread, unnecessary-give-up, abandonment and "
                     "extension-block items; the promote choice per cell and arm; lock goodput with the deadlock stratum; the Gemini "
                     "aware-on cells; the cross-model Firth-penalized regression with a wild cluster bootstrap (Rademacher weights, "
                     "9,999 draws, clustered on family x instance, score form: one Newton step from the fitted model per draw) in a "
                     "stdlib implementation, with the separated cells marked (one arm without an event; the estimate sits at the "
                     "penalty's boundary and the intervals there are nominal). Not done: the CR2 (bias-reduced cluster-robust) "
                     "standard errors the registration asked to print beside the bootstrap intervals; plain cluster-robust (CR1) "
                     "standard errors are printed instead. Not done either: per-family and per-wording breakdowns of the other "
                     "measures, and profile-likelihood intervals for the separated cells.",
        "reason": "The registration places these items in a separate, unfrozen script. CR2 needs a matrix square root per cluster that "
                  "the stdlib implementation does not provide.",
        "before_after": "After the results were opened (2026-11-09 to 2026-11-10).",
        "effect": "None on any registered verdict; these items support no confirmatory claim.",
        "registered_result": "Not applicable.",
    },
    {
        "deviation": "Note (not a departure): transient driver events. The Anthropic lane once logged 'submission ... has no batch on "
                     "the server: dropped (its requests will be resubmitted)' (a create call that did not register server-side; the "
                     "driver's crash-safety path resubmitted the requests) and one transient APIConnectionError on a batch create, "
                     "retried by the driver. Batches were submitted in gated waves (about 37 Gemini or 50 Haiku requests) because the "
                     "per-block sub-cap is compared with the worst-case cost of the requests in flight.",
        "reason": "Driver behaviour under the registered cost gate.",
        "before_after": "During the run; no result was read.",
        "effect": "Throughput only; no cap bound, no episode was lost or duplicated ({Duplicates} duplicate transcripts).",
        "registered_result": "As registered.",
    },
    {
        "deviation": "Note (not a departure): the run script run_conc_study2.sh was fixed for macOS bash 3.2 (an empty-array expansion "
                     "under set -u) after a no-cost rehearsal failed, refrozen, and the registration's hashes updated before filing.",
        "reason": "Rehearsal failure on the run machine before registration.",
        "before_after": "Before filing and before any paid call.",
        "effect": "None.",
        "registered_result": "As registered.",
    },
]


# ---------------------------------------------------------------------------------------------------------------
# The descriptive computation
# ---------------------------------------------------------------------------------------------------------------


def compute(D: Data, E: Data, reg: Mapping[str, Any], sel_log: Mapping[str, Any], spend: Mapping[str, Any],
            failures: Mapping[str, int], plan: Mapping[str, Any], n_files: int) -> Dict[str, Any]:
    res, T = reg["res"], reg["tests"]
    out: Dict[str, Any] = {}

    # ---- (a) H1: fs_nonserializable per arm, cluster means over complete pairs; Delta from the registered tests
    h1: Dict[str, Any] = {}
    per_model_cl: Dict[str, Dict[str, Dict[Tuple[str, int], Tuple[float, float]]]] = {}
    checks: List[Dict[str, Any]] = []
    for m in MODELS:
        for c in CONFIGS:
            for aware in (0, 1):
                if not D.has_cell(m, c, aware):
                    continue
                cl = cluster_arm_rates(D, m, c, aware, "fs")
                r = cell_rates(cl)
                r["pairs"] = sum(len(D.pairs(m, c, f, i, aware)) for f, i in cl)
                r["basis"] = cell_rates(cluster_arm_rates(D, m, c, aware, "basis"))
                if aware == 0:
                    per_model_cl.setdefault(c, {})[m] = cl
                    tid = f"{'H1cal-diff' if c == 'none' else 'H1-diff'}|{SHORT[m]}|{c}"
                    t = T.get(tid)
                    r["registered"] = tid if t else None
                    if t and t.get("estimate") is not None and r["delta"] is not None:
                        checks.append({"id": tid, "computed": r["delta"], "registered": t["estimate"],
                                       "abs_diff": abs(r["delta"] - t["estimate"])})
                h1[f"{SHORT[m]}|{c}|aware{aware}"] = r
    for c in CONFIGS:
        pm = {m: per_model_cl.get(c, {}).get(m, {}) for m in CONFIRMATORY if per_model_cl.get(c, {}).get(m)}
        r = pooled_rates(pm)
        tid = f"{'H1cal-diff' if c == 'none' else 'H1-diff'}|pooled|{c}"
        t = T.get(tid)
        r["registered"] = tid if t else None
        if t and t.get("estimate") is not None and r["delta"] is not None:
            checks.append({"id": tid, "computed": r["delta"], "registered": t["estimate"], "abs_diff": abs(r["delta"] - t["estimate"])})
        h1[f"Pooled|{c}|aware0"] = r
    out["h1"] = h1

    # ---- (b) primitive use and (c) outcome classes per cell and arm (main sample; extension apart)
    prim: Dict[str, Any] = {}
    outc: Dict[str, Any] = {}
    for sample_name, DD in (("main", D), ("extension", E)):
        for m in MODELS:
            for c in CONFIGS:
                for aware in (0, 1):
                    for arm in ("contended", "control"):
                        eps = DD.episodes(m, c, aware, arm)
                        if not eps:
                            continue
                        key = f"{sample_name}|{SHORT[m]}|{c}|aware{aware}|{arm}"
                        prim[key] = primitive_use(eps)
                        outc[key] = outcome_classes(eps)
    out["primitives"] = prim
    out["outcomes"] = outc

    # ---- (i) integrity by config vs none, paired by cluster (contended arm, aware off, main sample)
    vs_none: Dict[str, Any] = {}
    for m in MODELS:
        base_cl = {k: v[0] for k, v in cluster_arm_rates(D, m, "none", 0, "fs").items()}
        for c in H1_CONFIGS:
            cl = {k: v[0] for k, v in cluster_arm_rates(D, m, c, 0, "fs").items()}
            common = sorted(set(cl) & set(base_cl))
            eps = D.episodes(m, c, 0, "contended")
            vs_none[f"{SHORT[m]}|{c}"] = {
                "fs": mean([cl[k] for k in common]) if common else None,
                "fs_none": mean([base_cl[k] for k in common]) if common else None,
                "diff": mean([cl[k] - base_cl[k] for k in common]) if common else None, "clusters": len(common),
                "fulfilled": agent_rate(eps, "fulfilled"), "cap_endings": sum(e["cap_endings"] for e in eps),
                "deadlock": sum(1 for e in eps if e["deadlock"]), "agent_errors": sum(e["agent_errors"] for e in eps),
                "returned_only_identical": all(a["end"] == "returned" for e in eps for a in e["agents"].values()),
            }
    out["vs_none"] = vs_none

    # ---- (j) first_protective under all_available, update vs claim templates (aware off, main)
    fpc: Dict[str, Any] = {}
    for m in MODELS:
        for arm in ("contended", "control"):
            for group, fams in (("update", UPDATE_FAMILIES), ("claim", CLAIM_FAMILIES)):
                eps = [e for e in D.episodes(m, "all_available", 0, arm) if e["family"] in fams]
                agents = [a for e in eps for a in e["agents"].values()]
                n = len(agents)
                fpc[f"{SHORT[m]}|{arm}|{group}"] = {
                    "agents": n, "episodes": len(eps),
                    "lock": (sum(1 for a in agents if a["fp"] == "lock") / n) if n else None,
                    "cas": (sum(1 for a in agents if a["fp"] == "cas") / n) if n else None,
                    "none": (sum(1 for a in agents if a["fp"] is None) / n) if n else None,
                }
    out["first_protective"] = fpc

    # ---- (k) exploratory: fs_nonserializable per family (contended arm, aware off, main sample)
    fam_fs: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            eps = D.episodes(m, c, 0, "contended")
            keps = D.episodes(m, c, 0, "control")
            if not eps:
                continue
            row: Dict[str, Any] = {"control_fs": mean([e["fs"] for e in keps]), "n": len(eps)}
            for f in FAMILIES:
                fe = [e for e in eps if e["family"] == f]
                row[f] = {"fs": mean([e["fs"] for e in fe]), "n": len(fe)}
            fam_fs[f"{SHORT[m]}|{c}"] = row
    out["family_fs"] = fam_fs

    # ---- (d) probes: first-reply lock by model x config x aware; H3 (registered) and the leakage check (registered)
    probes: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            for aware in (0, 1):
                pc = probe_cell(D, m, c, aware)
                if pc["units"]:
                    probes[f"{SHORT[m]}|{c}|aware{aware}"] = pc
    out["probes"] = probes
    h3: Dict[str, Any] = {}
    for m in MODELS:
        t = T.get(f"H3|{SHORT[m]}|locks+all_available")
        if t is None:
            continue
        h3[SHORT[m]] = {"estimate": t.get("estimate"), "ci95": t.get("ci95"), "p": t.get("p"), "p_adj": t.get("p_adj"),
                        "reject": t.get("reject"), "status": t.get("status"), "n_units": t.get("n_clusters"),
                        "claim": t.get("claim"), "short": short_claim(t, "H3"),
                        "per_config": {k: v.get("estimate") for k, v in sorted((t.get("per_config") or {}).items())}}
    out["h3"] = h3
    out["leakage"] = res["checks"]["leakage"]
    out["eligibility"] = res["eligibility"]["cells"]

    # ---- (e) exposure (registered check 2) plus the agent share over every kept contended episode
    expo: Dict[str, Any] = {}
    for key, cell in sorted(res["checks"]["exposure"]["cells"].items()):
        sm, c, aw = key.split("|")
        aware = int(aw.replace("aware", ""))
        model = next(mm for mm in MODELS if SHORT[mm] == sm)
        eps = D.episodes(model, c, aware, "contended")
        keps = D.episodes(model, c, aware, "control")
        expo[key] = {"estimate": cell.get("estimate"), "n_clusters": cell.get("n_clusters"), "families": cell.get("families") or {},
                     "agent_share": agent_rate(eps, "exposed"), "control_agent_share": agent_rate(keps, "exposed"),
                     "mean_signals": mean([a["signals"] for e in eps for a in e["agents"].values()])}
    out["exposure"] = expo
    out["exposure_control_agents"] = res["checks"]["exposure"]["control_agents_exposed"]
    out["isolation"] = res["checks"]["isolation"]
    out["lock_safety"] = res["checks"]["lock_safety"]

    # ---- (f) H4: rates per arm (cluster means over complete pairs; lock under locks, any primitive under all_available)
    h4: Dict[str, Any] = {}
    per_model_h4: Dict[str, Dict[str, Dict[Tuple[str, int], Tuple[float, float]]]] = {}
    for m in MODELS:
        for c in H4_CONFIGS:
            o = "lock" if c == "locks" else "prim"
            cl = cluster_arm_rates(D, m, c, 0, o, level="agent")
            r = cell_rates(cl)
            per_model_h4.setdefault(c, {})[m] = cl
            td, te = T.get(f"H4-diff|{SHORT[m]}|{c}"), T.get(f"H4-eq|{SHORT[m]}|{c}")
            if td and td.get("estimate") is not None and r["delta"] is not None:
                checks.append({"id": td["id"], "computed": r["delta"], "registered": td["estimate"], "abs_diff": abs(r["delta"] - td["estimate"])})
            r.update({"outcome": o, "q": (te or td or {}).get("q"), "reading": (te or {}).get("reading"), "status": (te or {}).get("status"),
                      "short": short_claim(te, "H4"), "eligible": (res["eligibility"]["cells"].get(f"{m}|{c}") or {}).get("eligible")})
            r["h4b"] = res["h4b"].get(f"{SHORT[m]}|{c}")
            h4[f"{SHORT[m]}|{c}"] = r
    for c in H4_CONFIGS:
        td = T.get(f"H4-diff|pooled|{c}")
        te = T.get(f"H4-eq|pooled|{c}")
        models = [m for m in CONFIRMATORY if (res["eligibility"]["cells"].get(f"{m}|{c}") or {}).get("eligible")]
        r = pooled_rates({m: per_model_h4[c][m] for m in models if per_model_h4[c].get(m)})
        if td and td.get("estimate") is not None and r["delta"] is not None:
            checks.append({"id": td["id"], "computed": r["delta"], "registered": td["estimate"], "abs_diff": abs(r["delta"] - td["estimate"])})
        r.update({"outcome": "lock" if c == "locks" else "prim", "q": (te or td or {}).get("q"), "reading": (te or {}).get("reading"),
                  "status": (te or {}).get("status"), "short": short_claim(te, "H4"), "h4b": None, "eligible": None})
        h4[f"Pooled|{c}"] = r
    out["h4"] = h4
    out["checks_delta"] = checks

    # ---- (g) budget and spend
    caps = plan.get("caps") or {}
    est = plan.get("estimate_by_family") or {}
    safety = float(plan.get("safety") or 1.15)
    recorded: Dict[str, float] = {}
    recorded_model: Dict[str, float] = {}
    for DD in (D, E):
        for r in list(DD.ep.values()) + list(DD.pr.values()):
            recorded[r["provider_family"]] = recorded.get(r["provider_family"], 0.0) + r["cost_usd"]
            recorded_model[r["model"]] = recorded_model.get(r["model"], 0.0) + r["cost_usd"]
    budget = {"providers": {}, "models": {}, "window": None, "total": {}}
    for p in PROVIDERS:
        sp = float(spend["provider"].get(p, 0.0))
        budget["providers"][p] = {"estimate": est.get(p), "estimate_safe": (est.get(p) * safety) if est.get(p) is not None else None,
                                  "cap": caps.get(p), "spend": sp, "share_of_cap": (sp / caps[p]) if caps.get(p) else None,
                                  "recorded_in_transcripts": recorded.get(p, 0.0)}
    tot_sp = sum(float(spend["provider"].get(p, 0.0)) for p in PROVIDERS)
    budget["total"] = {"estimate": plan.get("estimate_total"), "estimate_safe": (float(plan["estimate_total"]) * safety) if plan.get("estimate_total") is not None else None,
                       "cap": plan.get("total_cap"), "spend": tot_sp, "share_of_cap": (tot_sp / float(plan["total_cap"])) if plan.get("total_cap") else None,
                       "recorded_in_transcripts": sum(recorded.values()), "safety": safety}
    for m in MODELS:
        budget["models"][SHORT[m]] = {"spend": float(spend["model"].get(m, 0.0)), "recorded_in_transcripts": recorded_model.get(m, 0.0)}
    w = (res.get("budget") or {}).get("windows") or []
    budget["window"] = w[0] if w else None
    budget["n_windows"] = len(w)
    budget["unclosed_window"] = (res.get("budget") or {}).get("unclosed_window")
    out["budget"] = budget

    # ---- (h) selection, exclusions, flags
    temps: Dict[str, Dict[str, int]] = {}
    hosts: Dict[str, Dict[str, int]] = {}
    served: Dict[str, Dict[str, int]] = {}
    completions_by_model: Dict[str, int] = {}
    for DD in (D, E):
        for r in list(DD.ep.values()) + list(DD.pr.values()):
            sm = SHORT[r["model"]]
            for a in r["agents"].values():
                for tv in a["temps"]:
                    k = "null" if tv is None else str(tv)
                    temps.setdefault(sm, {})[k] = temps.setdefault(sm, {}).get(k, 0) + 1
                for hv in a["hosts"]:
                    hosts.setdefault(sm, {})[hv] = hosts.setdefault(sm, {}).get(hv, 0) + 1
                for sv in a["served"]:
                    served.setdefault(sm, {})[sv] = served.setdefault(sm, {}).get(sv, 0) + 1
                completions_by_model[sm] = completions_by_model.get(sm, 0) + len(a["temps"])
    gpt_flag_eps = sum(1 for r in D.ep.values() if r["host_flag"]) + sum(1 for r in D.pr.values() if r["host_flag"])
    gpt_flag_eps_ext = sum(1 for r in E.ep.values() if r["host_flag"])
    gpt_flag_completions = sum(1 for DD in (D, E) for r in list(DD.ep.values()) + list(DD.pr.values()) if r["model"] == GPT
                               for a in r["agents"].values() for h in a["hosts"] if not h.startswith("openai"))
    agents_main = [a for r in D.ep.values() for a in r["agents"].values()]
    sel = {
        "files": n_files, "block": dict(sorted(sel_log["block"].items())), "block_by_model": dict(sorted(sel_log["block_by_model"].items())),
        "never_data": dict(sorted(sel_log["never_data"].items())), "counts": dict(sorted(sel_log["counts"].items())),
        "excluded": sel_log["excluded"], "provider_failures": dict(failures),
        "provider_failures_total": sum(failures.values()),
        "gpt_non_openai_episodes_main": gpt_flag_eps, "gpt_non_openai_episodes_extension": gpt_flag_eps_ext,
        "gpt_non_openai_completions": gpt_flag_completions,
        "qwen_non_alibaba_episodes": sum(1 for DD in (D, E) for r in list(DD.ep.values()) + list(DD.pr.values()) if r["host_bad"]),
        "cap_truncated_main": sum(1 for r in D.ep.values() if r["cap_truncated"]),
        "cap_truncated_extension": sum(1 for r in E.ep.values() if r["cap_truncated"]),
        "cap_endings_main": sum(r["cap_endings"] for r in D.ep.values()),
        "refusal_agents": sum(1 for a in agents_main if a["end"] in REFUSAL_ENDS),
        "error_agents": sum(1 for a in agents_main if a["end"] in AGENT_ERROR_ENDS),
        "not_returned_agents": sum(1 for a in agents_main if a["end"] != "returned"),
        "abandoned_agents": sum(1 for a in agents_main if a["abandoned"]),
        "give_up_agents": sum(1 for a in agents_main if a["give_up"]),
        "deadlock_episodes": sum(1 for r in D.ep.values() if r["deadlock"]),
        "stalled_episodes": sum(1 for r in D.ep.values() if r["stall"]),
        "episodes_main": len(D.ep), "probes_main": len(D.pr), "episodes_extension": len(E.ep),
        "agents_main": len(agents_main), "probed_agents": sum(len(r["agents"]) for r in D.pr.values()),
        "temperature_effective": {k: dict(sorted(v.items())) for k, v in sorted(temps.items())},
        "served_host": {k: dict(sorted(v.items())) for k, v in sorted(hosts.items())},
        "model_served": {k: dict(sorted(v.items())) for k, v in sorted(served.items())},
        "completions_by_model": dict(sorted(completions_by_model.items())),
        "registered_flags": res["selection"].get("flags"), "registered_block": res["selection"].get("block"),
        "registered_inputs": res.get("inputs"), "analyze5_sha256": res.get("analyze5_sha256"),
        "sensitivity_changed": {k: len(v.get("changed_verdicts", [])) for k, v in sorted((res.get("sensitivity") or {}).items())
                                if isinstance(v, dict) and "changed_verdicts" in v},
        "s1_dropped_with_partners": ((res.get("sensitivity") or {}).get("s1_cap24") or {}).get("rescore_status", {}).get("dropped_with_partners"),
        "s9_pairs_scored_against": ((res.get("sensitivity") or {}).get("s9_against_equivalence") or {}).get("pairs_scored_against"),
    }
    out["selection"] = sel
    out["summary_registered"] = res.get("summary")
    return out


# ---------------------------------------------------------------------------------------------------------------
# Post hoc mechanism counts (added after the T5 to T8 reviews, 2026-11-09; every rule is stated in the table captions)
# ---------------------------------------------------------------------------------------------------------------

RECORD_RE = re.compile(r"\b(?:inventory|seat|ticket|account|budget):[A-Za-z0-9][A-Za-z0-9\-_/]*")
MULTI_FAMILIES = ("transfer_shared_source", "budget_write_skew", "joint_account_write_skew")
SINGLE_FAMILIES = ("inventory_last_unit", "inventory_still_valid", "seat_same", "ticket_same")
WS_FAMILIES = ("budget_write_skew", "joint_account_write_skew")
# "success reported without a committed write": the agent's final reply matches SUCCESS_RE and not NEGATION_RE.
# The last two alternatives ("Sold N from ...", "sale recorded successfully") were added after review T7b S-A, which
# read every final reply with a completion word and found two Haiku replies the earlier pattern missed.
SUCCESS_RE = re.compile(
    r"(task (?:is|has been|was) (?:now )?complete|completed successfully|(?:has been|have been|was|were|is) (?:completed|successful|successfully)"
    r"|successfully (?:sold|reduced|recorded|transferred|assigned|withdr\w+|added|moved|completed|updated|claimed|credited|debited|processed|booked|taken|given|decremented|set)"
    r"|sale (?:of [^.]{0,40})?(?:has been|was|is) (?:completed|recorded|successful|processed|done)"
    r"|transfer(?:red)?[^.]{0,80}(?:complete|success)|(?:withdrawal|spend|claim|assignment)[^.]{0,60}(?:complete|success|recorded)"
    r"|\bsold [0-9]+ from\b|sale recorded successfully"
    # "Transferred 90.00 from A to B": the completion report of a half-done transfer (review T8b N4b); the alternative
    # changes no count of the false-success table, since every such agent has a committed effect
    r"|\btransferred [0-9.]+ (?:from|out of)\b)", re.I)
CONCURRENT_RE = re.compile(r"\bconcurren(?:t|tly|cy)\b|\banother (?:agent|process|client|transaction)\b", re.I)
NEGATION_RE = re.compile(
    r"\b(not|no|cannot|can't|could not|couldn't|unable|did not|didn't|declin\w*|abort\w*|skipp?\w*|insufficient|fail\w*|rejected|exceed\w*"
    r"|over the cap|below the floor|would (?:breach|violate|drop)|nothing|unchanged|no action|without (?:making|writing|changing)"
    r"|already (?:held|taken|assigned|claimed|has a holder|sold out|owned|booked|occupied|belongs)|is held by|is assigned to|holder is)\b", re.I)


def _agent_calls(e: Mapping[str, Any], aid: str) -> List[Dict[str, Any]]:
    return [c for c in e["calls"] if c["agent_id"] == aid]


def _lock_scope(e: Mapping[str, Any], aid: str) -> str:
    """all: the agent locked every record its intent names; own: it locked some record; none: no granted lock."""
    locked = {c["record_id"] for c in _agent_calls(e, aid) if c["tool"] == "acquire_lock" and c["status"] == 200}
    recs = set(RECORD_RE.findall(e["intents"].get(aid, "")))
    return "all" if recs and locked >= recs else ("own" if locked else "none")


def _protocol_order(e: Mapping[str, Any], aid: str) -> str:
    """lock_first: the first well-formed acquire_lock precedes the first successful read; read_then_lock: the
    reverse; no_lock: no well-formed acquire_lock (a granted one or one refused 423 after the wait)."""
    calls = _agent_calls(e, aid)
    first_read = next((c["own_call"] for c in calls if c["tool"] == "get_record" and c["status"] == 200), None)
    first_lock = next((c["own_call"] for c in calls if c["tool"] == "acquire_lock" and c["status"] in (200, 423)), None)
    if first_lock is None:
        return "no_lock"
    if first_read is None or first_lock < first_read:
        return "lock_first"
    return "read_then_lock"


def _phantom(e: Mapping[str, Any], aid: str) -> bool:
    """Success reported without any committed write: no ledger effect by the agent and a final reply that matches
    SUCCESS_RE and not NEGATION_RE."""
    if aid in e["effect_agents"]:
        return False
    ft = e["agents"][aid]["final_text"]
    return bool(SUCCESS_RE.search(ft)) and not NEGATION_RE.search(ft)


def _transfer_src_dst(intent: str) -> Tuple[Optional[str], Optional[str], Optional[float]]:
    m = re.search(r"(?:Move|Transfer) ([0-9.]+) (?:from|out of) (\S+) (?:to|into) (\S+?),", intent)
    if not m:
        return None, None, None
    return m.group(2), m.group(3), float(m.group(1))


def _missing_leg_code(e: Mapping[str, Any], aid: str) -> Dict[str, Any]:
    """How the credit of a half-done transfer came to be committed (post hoc, review T5 M2 / T6 M2)."""
    src, dst, amt = _transfer_src_dst(e["intents"].get(aid, ""))
    turns = e["agents"][aid]["reply_turns"]
    flat = [(ti, tool, rid, st) for ti, t in enumerate(turns) for (tool, rid, st) in t]
    rej = [(i, x) for i, x in enumerate(flat) if x[1] == "update_record" and x[2] == src and x[3] not in (200, None)]
    cred = [(i, x) for i, x in enumerate(flat) if x[1] == "update_record" and x[2] == dst and x[3] == 200]
    if not rej:
        code = "no_debit_attempted"
    elif not cred:
        code = "no_credit"
    else:
        ri, rx = rej[0]
        ci, cx = cred[0]
        rereads = [i for i, x in enumerate(flat) if x[1] == "get_record" and x[2] == src and i > ri]
        if rx[0] == cx[0]:
            code = "same_reply"
        elif cx[0] < rx[0]:
            code = "credit_before_rejection"
        elif rereads and rereads[0] < ci:
            code = "credit_after_reread"
        else:
            code = "credit_later_no_reread"
    # did a re-read of the source after the first rejection return the balance the agent expected after its own debit?
    calls = _agent_calls(e, aid)
    saw_expected = False
    first_val = next((c["value"] for c in calls if c["tool"] == "get_record" and c["record_id"] == src and c["status"] == 200), None)
    rej_idx = next((i for i, c in enumerate(calls) if c["tool"] == "update_record" and c["record_id"] == src and c["status"] != 200), None)
    if first_val is not None and amt is not None and rej_idx is not None:
        try:
            expected = float(first_val) - amt
            for c in calls[rej_idx + 1:]:
                if c["tool"] == "get_record" and c["record_id"] == src and c["status"] == 200 and c["value"] is not None:
                    if abs(float(c["value"]) - expected) < 1e-9:
                        saw_expected = True
        except (TypeError, ValueError):
            pass
    listed = any(c["tool"] == "list_effects" for c in calls)
    # after the first rejected debit, a successful list_effects call whose response listed no effect on the source record
    # (the agent's own committed writes, by the tool's description; review T6b N1)
    listed_no_debit = rej_idx is not None and src is not None and any(
        c["tool"] == "list_effects" and c["status"] == 200 and c["listed"] is not None and src not in c["listed"]
        for c in calls[rej_idx + 1:])
    first_status = rej[0][1][3] if rej else None
    # same-reply cases (review T5b F1): did a peer's committed write to the source precede, in ledger order, the first
    # executed call of the reply that carried the rejected debit and the committed credit? The own-call index of that
    # call is one plus the number of executed calls (a tool_result received) in earlier replies; its tool must match.
    peer_before_reply = None
    # same-reply cases (review F1 S1): was the rejected debit listed before the committed credit in that reply? If so, a
    # runtime that ran a reply's calls in order and stopped at the first rejected call would not have sent the credit.
    debit_first = None
    if code == "same_reply":
        debit_first = rej[0][0] < cred[0][0]
        ti = rej[0][1][0]
        k = 1 + sum(1 for t in turns[:ti] for (_, _, st) in t if st is not None)
        first_tool = next((tool for (tool, _, st) in turns[ti] if st is not None), None)
        li = next((i for i, c in enumerate(e["calls"]) if c["agent_id"] == aid and c["own_call"] == k), None)
        if li is not None and e["calls"][li]["tool"] == first_tool:
            peer_before_reply = any(c["agent_id"] != aid and c["committed"] and c["record_id"] == src for c in e["calls"][:li])
    return {"code": code, "saw_expected": saw_expected, "listed_effects": listed, "listed_no_debit": listed_no_debit,
            "first_rejection_status": first_status, "peer_before_reply": peer_before_reply,
            "debit_first": debit_first}


def _ws_agent_code(e: Mapping[str, Any], aid: str) -> str:
    """Write-skew families, per agent: reverted (rolled back its own write); wrote (committed and fulfilled);
    wrote_other (committed, not fulfilled, not rolled back); declined_after_reread (no committed write and some
    record of its intent read at least twice); declined (no committed write, no repeated read)."""
    av = e["agents"][aid]
    if av["rolled_back_agent"]:
        return "reverted"
    committed = aid in e["committed_agents"]
    if committed and av["fulfilled"]:
        return "wrote"
    if committed:
        return "wrote_other"
    recs = set(RECORD_RE.findall(e["intents"].get(aid, "")))
    reads: Dict[str, int] = {}
    for c in _agent_calls(e, aid):
        if c["tool"] == "get_record" and c["status"] == 200 and c["record_id"] in recs:
            reads[c["record_id"]] = reads.get(c["record_id"], 0) + 1
    return "declined_after_reread" if any(n >= 2 for n in reads.values()) else "declined"


def _promotion_fired_peer_409(e: Mapping[str, Any]) -> bool:
    """Whether a promotion (a committed no-op conditional write-back) made a peer's conditional write fail: some agent's
    update_record or claim was refused 409 version_conflict on a record R, and every committed write to R between that
    agent's last successful read of R (or its own last committed write to R) and the refusal was a no-op write-back by
    another agent (the scorer's promotion). Rule added after reviews T7b M-A and T8b N2."""
    calls = e["calls"]
    noop_by_seq = {ef["seq"]: ef for ef in e["effects"] if ef["noop"] and ef["cas"]}
    for j, c in enumerate(calls):
        if c["status"] != 409 or c["reason"] != "version_conflict" or c["tool"] not in ("update_record", "claim"):
            continue
        aid, rid = c["agent_id"], c["record_id"]
        last_seen = -1
        for k in range(j - 1, -1, -1):
            ck = calls[k]
            if ck["agent_id"] == aid and ck["record_id"] == rid and ((ck["tool"] == "get_record" and ck["status"] == 200) or ck["committed"]):
                last_seen = k
                break
        between = [ck for ck in calls[last_seen + 1:j] if ck["committed"] and ck["record_id"] == rid and ck["agent_id"] != aid]
        if between and all(ck["effect_seq"] in noop_by_seq for ck in between):
            return True
    return False


def _revert_after_reread(e: Mapping[str, Any], aid: str) -> bool:
    """A rolled-back agent that, between its first committed write and its last committed write (the revert), read a
    record of its intent again with a successful get_record; with the episode's ``compensated_after_violation`` flag this
    is the coded form of "wrote, re-read, saw the constraint broken and reverted" (review T8b N4a)."""
    if not e["agents"][aid]["rolled_back_agent"]:
        return False
    calls = _agent_calls(e, aid)
    idx = [i for i, c in enumerate(calls) if c["committed"]]
    if len(idx) < 2:
        return False
    recs = set(RECORD_RE.findall(e["intents"].get(aid, "")))
    return any(c["tool"] == "get_record" and c["status"] == 200 and c["record_id"] in recs for c in calls[idx[0] + 1:idx[-1]])


def _transfer_legs(e: Mapping[str, Any], aid: str) -> Tuple[bool, bool]:
    """(debit committed, credit committed) for a transfer agent: a committed value-changing write to the source /
    the destination record of its intent (ledger effects)."""
    src, dst, _ = _transfer_src_dst(e["intents"].get(aid, ""))
    debit = any(ef["agent_id"] == aid and ef["record_id"] == src and not ef["noop"] for ef in e["effects"])
    credit = any(ef["agent_id"] == aid and ef["record_id"] == dst and not ef["noop"] for ef in e["effects"])
    return debit, credit


def _num(x: Any) -> Any:
    """Record values as comparable numbers (integers for stock, Decimal for money, strings or None for holders)."""
    if x is None or isinstance(x, bool):
        return x
    if isinstance(x, int):
        return x
    s = str(x)
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        from decimal import Decimal
        return Decimal(s)
    return s


def parse_intent(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """The intent text (tasks5.describe wordings 0 and 1) back to its kind and parameters."""
    pats = [
        ("decrement", r"^(?:Sell|Withdraw) (?P<amt>[0-9.]+) from (?P<rec>\S+), only if enough remains\.$"),
        ("decrement", r"^Reduce (?P<rec>\S+) by (?P<amt>[0-9.]+) to record a sale, but only if at least [0-9.]+ is in stock\.$"),
        ("decrement", r"^Take (?P<amt>[0-9.]+) out of (?P<rec>\S+), but only if its balance covers it\.$"),
        ("claim", r"^Assign (?P<rec>\S+) to (?P<holder>\S+), only if it has no holder yet\.$"),
        ("claim", r"^Give (?P<rec>\S+) to (?P<holder>\S+), but only if it is still unassigned\.$"),
        ("transfer", r"^Move (?P<amt>[0-9.]+) from (?P<src>\S+) to (?P<dst>\S+), only if \S+ has enough\.$"),
        ("transfer", r"^Transfer (?P<amt>[0-9.]+) out of (?P<src>\S+) into (?P<dst>\S+), but only if \S+ has at least [0-9.]+\.$"),
        ("spend", r"^Record a spend of (?P<amt>[0-9.]+) in (?P<own>\S+), only if total spend across (?P<recs>.+?) stays within (?P<cap>\S+)\.$"),
        ("spend", r"^Add (?P<amt>[0-9.]+) to (?P<own>\S+), provided the combined spend in (?P<recs>.+?) does not go over (?P<cap>\S+)\.$"),
        ("joint", r"^Withdraw (?P<amt>[0-9.]+) from (?P<target>\S+), only if the combined balance of (?P<recs>.+?) stays at or above (?P<floor>[0-9.]+)\.$"),
        ("joint", r"^Take (?P<amt>[0-9.]+) out of (?P<target>\S+), provided (?P<recs>.+?) together still hold at least (?P<floor>[0-9.]+) afterwards\.$"),
    ]
    for kind, pat in pats:
        m = re.match(pat, text.strip())
        if m:
            d = {k: v for k, v in m.groupdict().items()}
            if "recs" in d:
                d["recs"] = [r.strip() for r in d["recs"].split(",")]
            return kind, d
    return None


def apply_intent(kind: str, p: Mapping[str, Any], values: Dict[str, Any]) -> bool:
    """Apply one intent to ``values`` in place if its guard holds; return whether it succeeded."""
    amt = _num(p.get("amt")) if p.get("amt") is not None else None
    if kind == "decrement":
        if values[p["rec"]] >= amt:
            values[p["rec"]] = values[p["rec"]] - amt
            return True
        return False
    if kind == "claim":
        cur = values[p["rec"]]
        if cur is None or cur == p["holder"]:
            values[p["rec"]] = p["holder"]
            return True
        return False
    if kind == "transfer":
        if values[p["src"]] >= amt:
            values[p["src"]] = values[p["src"]] - amt
            values[p["dst"]] = values[p["dst"]] + amt
            return True
        return False
    if kind == "spend":
        spent = sum(values[r] for r in p["recs"])
        if spent + amt <= values[p["cap"]]:
            values[p["own"]] = values[p["own"]] + amt
            return True
        return False
    if kind == "joint":
        total = sum(values[r] for r in p["recs"])
        if total - amt >= _num(p["floor"]):
            values[p["target"]] = values[p["target"]] - amt
            return True
        return False
    raise ValueError(kind)


def serially_reachable(e: Mapping[str, Any]) -> Optional[bool]:
    """Whether the final store equals the result of some serial execution, from the initial values, of a subset of
    the agents' intents (possibly a single agent's, or none). An fs-failed episode with a reachable final store is a
    lost update whose end state a single intent could have produced (post hoc, review V3 note 4)."""
    intents = {}
    for a, text in e["intents"].items():
        pr = parse_intent(text)
        if pr is None:
            return None
        intents[a] = pr
    init = {k: _num(v) for k, v in e["initial"].items()}
    final = {k: _num(v) for k, v in e["final"].items()}
    agents = sorted(intents)
    from itertools import permutations
    subsets: List[Tuple[str, ...]] = [()]
    for r in range(1, len(agents) + 1):
        for perm in permutations(agents, r):
            subsets.append(perm)
    for order in subsets:
        vals = dict(init)
        ok = True
        for a in order:
            kind, p = intents[a]
            if not apply_intent(kind, p, vals):
                ok = False
                break
        if ok and all(vals.get(k) == final.get(k) for k in final):
            return True
    return False


def clopper_pearson_upper(k: int, n: int, level: float = 0.975) -> Optional[float]:
    """Exact one-sided upper bound on a binomial proportion; for k = 0 it is 1 - (1 - level)^(1/n)."""
    if n <= 0:
        return None
    if k == 0:
        return 1.0 - (1.0 - level) ** (1.0 / n)
    lo, hi = 0.0, 1.0
    for _ in range(200):  # bisection on the binomial cdf
        mid = (lo + hi) / 2
        cdf = sum(math.comb(n, j) * mid ** j * (1 - mid) ** (n - j) for j in range(k + 1))
        if cdf > 1.0 - level:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson_lower(k: int, n: int, level: float = 0.975) -> Optional[float]:
    """Exact one-sided lower bound on a binomial proportion; for k = n it is (1 - level)^(1/n) (the mirror of the
    upper bound for a zero cell; review T7b N-E)."""
    if n <= 0 or k <= 0:
        return None if n <= 0 else 0.0
    up = clopper_pearson_upper(n - k, n, level)
    return None if up is None else 1.0 - up


def mechanisms(D: Data, E: Data, reg: Mapping[str, Any]) -> Dict[str, Any]:
    """Post hoc counts from the transcripts (contended arm, aware off, core blocks unless stated). Nothing here is a
    registered statistic; every rule is in the helper docstrings and the table captions."""
    res = reg["res"]
    out: Dict[str, Any] = {}

    # ---- lock-failure mechanisms (locks, fs-failed contended episodes)
    lock_mech: Dict[str, Dict[str, int]] = {}
    for m in MODELS:
        eps = [e for e in D.episodes(m, "locks", 0, "contended") if e["fs"]]
        row = {"failed": len(eps), "read_then_lock": 0, "no_lock": 0, "fenced_other": 0, "write_skew": 0,
               "write_skew_own_only": 0, "write_skew_none": 0, "missing_leg": 0, "any_stale": 0,
               # exclusivity of the three mechanisms (review T7b: exactly one per failed episode) and the lock-scope
               # pair behind "write skew, guard records not locked" (review T7b S-G)
               "exactly_one": 0, "more_than_one": 0, "none_of_three": 0,
               "own_only_both_own": 0, "own_only_one_none": 0, "own_only_one_all": 0}
        for e in eps:
            stale = set(e["stale_overwrite_seqs"])
            fsb = set(e["fenced_stale_basis_seqs"])
            byeff = {c["effect_seq"]: c for c in e["calls"] if c["committed"]}
            mech = set()
            for es in stale:
                c = byeff.get(es)
                if c is None:
                    continue
                if c["fencing_token"] is not None and es in fsb:
                    mech.add("read_then_lock")
                elif c["fencing_token"] is None:
                    mech.add("no_lock")
                else:
                    mech.add("fenced_other")
            if stale:
                row["any_stale"] += 1
            for k in mech:
                row[k] += 1
            if e["flags"].get("write_skew"):
                row["write_skew"] += 1
                scopes = sorted(_lock_scope(e, a) for a in e["agents"])
                if any(s_ != "all" for s_ in scopes):  # some agent never locked the guard records its constraint reads
                    row["write_skew_own_only"] += 1
                    mech.add("own_only")
                    if scopes == ["own", "own"]:
                        row["own_only_both_own"] += 1
                    elif "none" in scopes:
                        row["own_only_one_none"] += 1
                    elif "all" in scopes:
                        row["own_only_one_all"] += 1
                if "none" in scopes:
                    row["write_skew_none"] += 1
            if e["flags"].get("missing_leg"):
                row["missing_leg"] += 1
            three = {"read_then_lock", "no_lock", "own_only"} & mech
            if len(three) == 1:
                row["exactly_one"] += 1
            elif len(three) > 1:
                row["more_than_one"] += 1
            else:
                row["none_of_three"] += 1
        lock_mech[SHORT[m]] = row
    out["lock_mech"] = lock_mech

    # ---- protocol order and lock scope per agent (lock configs, contended and control)
    order: Dict[str, Any] = {}
    for m in MODELS:
        for c in LOCK_CONFIGS:
            for arm in ("contended", "control"):
                eps = D.episodes(m, c, 0, arm)
                agents = [(e, a) for e in eps for a in e["agents"]]
                if not agents:
                    continue
                codes = [_protocol_order(e, a) for e, a in agents]
                multi = [(e, a) for e, a in agents if e["family"] in MULTI_FAMILIES]
                scopes = [_lock_scope(e, a) for e, a in multi]
                order[f"{SHORT[m]}|{c}|{arm}"] = {
                    "agents": len(agents), "lock_first": codes.count("lock_first") / len(agents),
                    "read_then_lock": codes.count("read_then_lock") / len(agents), "no_lock": codes.count("no_lock") / len(agents),
                    "multi_agents": len(multi), "locked_all": (scopes.count("all") / len(multi)) if multi else None,
                    "locked_own": (scopes.count("own") / len(multi)) if multi else None,
                    "locked_none": (scopes.count("none") / len(multi)) if multi else None,
                    "locked_all_n": scopes.count("all"), "locked_own_n": scopes.count("own")}
    out["protocol_order"] = order

    # ---- half-done transfers (CAS configs, transfer family, contended): how the credit came to be committed
    ml: Dict[str, Any] = {}
    no_debit_detail: List[Dict[str, Any]] = []
    repaired_ids: List[str] = []
    for m in MODELS:
        row = {"agents": 0, "same_reply": 0, "credit_after_reread": 0, "credit_before_rejection": 0, "credit_later_no_reread": 0,
               "no_debit_attempted": 0, "no_credit": 0, "saw_expected": 0, "listed_effects": 0,
               "listed_no_debit": 0, "listed_no_debit_success": 0, "peer_before_reply": 0, "peer_before_reply_unknown": 0,
               "debit_first": 0,
               "first_rejection_409": 0, "first_rejection_423": 0,
               # the final reply matches the success pattern of the false-success table (review T8b N4b), and the final
               # reply names a concurrent process or another agent (review T7b N-C)
               "reported_success": 0, "names_concurrent": 0,
               # every transfer agent of the cell by its committed legs; "credit only" = credit committed, debit never
               # committed, which is the missing-leg agents plus the agents that reversed the credit (reviews T8b N1, T7b)
               "credit_only": 0, "credit_only_repaired": 0, "credit_only_repaired_saw_expected": 0, "debit_only": 0, "both_legs": 0, "no_leg": 0}
        for c in ("cas_available", "all_available"):
            for e in D.episodes(m, c, 0, "contended"):
                if e["family"] != "transfer_shared_source":
                    continue
                for a, av in e["agents"].items():
                    debit, credit = _transfer_legs(e, a)
                    if credit and not debit:
                        row["credit_only"] += 1
                        if av["rolled_back_agent"]:
                            row["credit_only_repaired"] += 1
                            row["credit_only_repaired_saw_expected"] += int(_missing_leg_code(e, a)["saw_expected"])
                            repaired_ids.append(f"{e['id']} {a}")
                    elif debit and not credit:
                        row["debit_only"] += 1
                    elif debit and credit:
                        row["both_legs"] += 1
                    else:
                        row["no_leg"] += 1
                    if not av["missing_leg"]:
                        continue
                    r = _missing_leg_code(e, a)
                    row["agents"] += 1
                    row[r["code"]] += 1
                    row["saw_expected"] += int(r["saw_expected"])
                    row["listed_effects"] += int(r["listed_effects"])
                    ft = av["final_text"]
                    succ = bool(SUCCESS_RE.search(ft)) and not NEGATION_RE.search(ft)
                    row["reported_success"] += int(succ)
                    row["listed_no_debit"] += int(r["listed_no_debit"])
                    row["listed_no_debit_success"] += int(r["listed_no_debit"] and succ)
                    if r["code"] == "same_reply":
                        row["peer_before_reply"] += int(r["peer_before_reply"] is True)
                        row["peer_before_reply_unknown"] += int(r["peer_before_reply"] is None)
                        row["debit_first"] += int(r["debit_first"] is True)
                    row["names_concurrent"] += int(bool(CONCURRENT_RE.search(ft)))
                    if r["first_rejection_status"] == 409:
                        row["first_rejection_409"] += 1
                    elif r["first_rejection_status"] == 423:
                        row["first_rejection_423"] += 1
                    if r["code"] == "no_debit_attempted":
                        src, dst, _ = _transfer_src_dst(e["intents"].get(a, ""))
                        calls = _agent_calls(e, a)
                        credit_idx = next((i for i, c_ in enumerate(calls) if c_["tool"] == "update_record" and c_["record_id"] == dst and c_["committed"]), len(calls))
                        last_val = next((c_["value"] for c_ in reversed(calls[:credit_idx]) if c_["tool"] == "get_record" and c_["record_id"] == src and c_["status"] == 200), None)
                        no_debit_detail.append({"id": e["id"], "agent": a, "model": SHORT[m], "config": c, "last_source_value_before_credit": last_val,
                                                "waited_rounds": sum(c_["waited_rounds"] for c_ in calls[:credit_idx] if c_["tool"] == "acquire_lock")})
        ml[SHORT[m]] = row
    tot = {k: sum(ml[SHORT[m]][k] for m in CONFIRMATORY) for k in ml[SHORT[CONFIRMATORY[0]]]}
    ml["Confirmatory"] = tot
    out["missing_leg"] = ml
    out["missing_leg_no_debit"] = no_debit_detail
    out["transfer_repaired_ids"] = sorted(repaired_ids)

    # ---- rolled-back agents (the scorer's rolled_back: every record the agent changed restored to its first basis
    #      value) per model, config and arm, all families, with the family split (reviews T8b N1, T7b M-A)
    rb: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            for arm in ("contended", "control"):
                eps = D.episodes(m, c, 0, arm)
                if not eps:
                    continue
                hits = [(e, a) for e in eps for a, av in e["agents"].items() if av["rolled_back_agent"]]
                byfam: Dict[str, int] = {}
                for e, a in hits:
                    byfam[e["family"]] = byfam.get(e["family"], 0) + 1
                rb[f"{SHORT[m]}|{c}|{arm}"] = {"agents": sum(len(e["agents"]) for e in eps), "rolled_back": len(hits),
                                               "by_family": dict(sorted(byfam.items()))}
    out["rolled_back"] = rb

    # ---- reads overlap and failure conditional on overlap (per cell and arm; the share equals results.json reads_overlap)
    ov: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            for arm in ("contended", "control"):
                eps = D.episodes(m, c, 0, arm)
                if not eps:
                    continue
                n = len(eps)
                o = [e for e in eps if e["reads_overlap"]]
                no = [e for e in eps if not e["reads_overlap"]]
                key = f"{SHORT[m]}|{c}|{arm}"
                regv = (res.get("reads_overlap") or {}).get(key, {})
                share = len(o) / n
                if regv and regv.get("share") is not None and abs(regv["share"] - share) > 1e-9:
                    raise SystemExit(f"reads_overlap share for {key} differs from results.json")
                ov[key] = {"n": n, "overlap": share, "overlap_n": len(o), "fail": mean([e["fs"] for e in eps]),
                           "fail_given_overlap": mean([e["fs"] for e in o]) if o else None,
                           "fail_given_no_overlap": mean([e["fs"] for e in no]) if no else None, "no_overlap_n": len(no)}
    out["overlap"] = ov

    # ---- task class: single-record vs multi-record families (episode shares per arm and cluster-mean delta)
    cls: Dict[str, Any] = {}
    per_model_cls: Dict[Tuple[str, str], Dict[str, Dict[Tuple[str, int], Tuple[float, float]]]] = {}
    for m in MODELS:
        for c in CONFIGS:
            cl = cluster_arm_rates(D, m, c, 0, "fs")
            if not cl:
                continue
            for name, fams in (("single", SINGLE_FAMILIES), ("multi", MULTI_FAMILIES)):
                sub = {k: v for k, v in cl.items() if k[0] in fams}
                if not sub:
                    continue
                per_model_cls.setdefault((c, name), {})[m] = sub
                eps = [e for e in D.episodes(m, c, 0, "contended") if e["family"] in fams]
                keps = [e for e in D.episodes(m, c, 0, "control") if e["family"] in fams]
                r = cell_rates(sub)
                r.update({"episodes": len(eps), "failed_n": sum(e["fs"] for e in eps), "control_failed_n": sum(e["fs"] for e in keps),
                          "upper_bound": clopper_pearson_upper(sum(e["fs"] for e in eps), len(eps))})
                cls[f"{SHORT[m]}|{c}|{name}"] = r
    for c in CONFIGS:
        for name in ("single", "multi"):
            pm = {m: per_model_cls.get((c, name), {}).get(m) for m in CONFIRMATORY if per_model_cls.get((c, name), {}).get(m)}
            if pm:
                r = pooled_rates(pm)
                cls[f"Pooled|{c}|{name}"] = r
    out["task_class"] = cls

    # ---- write-skew families: protocol codes per agent and per episode (how write skew was avoided or not)
    ws: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            eps = [e for e in D.episodes(m, c, 0, "contended") if e["family"] in WS_FAMILIES]
            if not eps:
                continue
            row = {"episodes": len(eps), "failed": 0, "clean": 0, "compensated": 0, "clean_decline_after_reread": 0,
                   "clean_decline": 0, "compensated_revert": 0, "both_wrote": 0, "agents": 0, "agent_reverted": 0,
                   "agent_declined_after_reread": 0, "agent_declined": 0, "agent_wrote": 0, "agent_wrote_other": 0,
                   "locked_all_agents": 0, "lock_first_agents": 0,
                   # promotion (the scorer's ``promote`` choice) and the coded form of "wrote, re-read, saw the
                   # constraint broken and reverted" (reviews T7b M-A, T8b N2 and N4a)
                   "agent_promoted": 0, "clean_with_promote": 0, "promote_fired_peer_409": 0,
                   "compensated_revert_after_reread_violation": 0}
            for e in eps:
                codes = {a: _ws_agent_code(e, a) for a in e["agents"]}
                row[e["outcome"]] += 1
                vals = list(codes.values())
                if e["outcome"] == "clean" and "declined_after_reread" in vals:
                    row["clean_decline_after_reread"] += 1
                elif e["outcome"] == "clean" and "declined" in vals:
                    row["clean_decline"] += 1
                if e["outcome"] == "compensated" and "reverted" in vals:
                    row["compensated_revert"] += 1
                    if e["flags"].get("compensated_after_violation") and any(_revert_after_reread(e, a) for a in e["agents"]):
                        row["compensated_revert_after_reread_violation"] += 1
                if all(v in ("wrote", "wrote_other") for v in vals):
                    row["both_wrote"] += 1
                promoted = [a for a, av in e["agents"].items() if av["promote"]]
                row["agent_promoted"] += len(promoted)
                if promoted and e["outcome"] == "clean":
                    row["clean_with_promote"] += 1
                if promoted and _promotion_fired_peer_409(e):
                    row["promote_fired_peer_409"] += 1
                for a, v in codes.items():
                    row["agents"] += 1
                    row["agent_" + v] += 1
                    if c in LOCK_CONFIGS:
                        row["locked_all_agents"] += int(_lock_scope(e, a) == "all")
                        row["lock_first_agents"] += int(_protocol_order(e, a) == "lock_first")
            ws[f"{SHORT[m]}|{c}"] = row
    out["ws_protocols"] = ws

    # ---- the scorer's ``promote`` choice per model, config and arm, all families (core, aware off)
    pm: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            for aware in (0, 1):
                for arm in ("contended", "control"):
                    eps = D.episodes(m, c, aware, arm)
                    if not eps:
                        continue
                    agents = [(e, a, av) for e in eps for a, av in e["agents"].items()]
                    hits = [(e["id"], a) for e, a, av in agents if av["promote"]]
                    pm[f"{SHORT[m]}|{c}|aware{aware}|{arm}"] = {"agents": len(agents), "promoted": len(hits), "ids": [f"{i} {a}" for i, a in hits]}
    out["promote"] = pm

    # ---- success reported without a committed write (phantom success), per model x config x family
    ph: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            for f in FAMILIES:
                eps = [e for e in D.episodes(m, c, 0, "contended") if e["family"] == f]
                if not eps:
                    continue
                agents = [(e, a) for e in eps for a in e["agents"]]
                hits = [(e, a) for e, a in agents if _phantom(e, a)]
                if hits:
                    ph[f"{SHORT[m]}|{c}|{f}"] = {
                        "agents": len(agents), "phantom": len(hits),
                        "scored_clean_decline": sum(1 for e, a in hits if e["agents"][a]["valid_at_end"] is False and not e["agents"][a]["abandoned"]),
                        "scored_abandoned": sum(1 for e, a in hits if e["agents"][a]["abandoned"]),
                        "in_failed_episode": sum(1 for e, a in hits if e["outcome"] == "failed")}
    totals: Dict[str, Dict[str, int]] = {}
    for key, v in ph.items():
        sm, c, f = key.split("|")
        t = totals.setdefault(f"{sm}|{c}", {"phantom": 0, "scored_clean_decline": 0, "scored_abandoned": 0})
        for k in t:
            t[k] += v[k]
    out["phantom"] = ph
    out["phantom_totals"] = totals

    # ---- after an explicit 409 (CAS configs, contended): re-read, then ended wrong?
    af: Dict[str, Any] = {}
    for m in MODELS:
        row = {"agents": 0, "reread": 0, "wrong": 0, "missing_leg": 0, "phantom": 0}
        for c in ("cas_available", "all_available"):
            for e in D.episodes(m, c, 0, "contended"):
                for a, av in e["agents"].items():
                    calls = _agent_calls(e, a)
                    idx = next((i for i, c_ in enumerate(calls) if c_["status"] == 409 and c_["reason"] == "version_conflict"), None)
                    if idx is None:
                        continue
                    rid = calls[idx]["record_id"]
                    reread = False
                    for c_ in calls[idx + 1:]:
                        if c_["tool"] == "get_record" and c_["record_id"] == rid:
                            reread = True
                            break
                        if c_["tool"] in ("update_record", "claim") and c_["record_id"] == rid:
                            break
                    p_ = _phantom(e, a)
                    row["agents"] += 1
                    row["reread"] += int(reread)
                    row["missing_leg"] += int(av["missing_leg"])
                    row["phantom"] += int(p_)
                    row["wrong"] += int(av["missing_leg"] or p_)
        af[SHORT[m]] = row
    af["Confirmatory"] = {k: sum(af[SHORT[m]][k] for m in CONFIRMATORY) for k in af[SHORT[CONFIRMATORY[0]]]}
    out["after409"] = af

    # ---- fs-failed contended episodes whose final store a serial execution of a subset of the intents reproduces
    reach: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            eps = [e for e in D.episodes(m, c, 0, "contended") if e["fs"]]
            if not eps:
                continue
            flags = [serially_reachable(e) for e in eps]
            if any(f is None for f in flags):
                raise SystemExit(f"could not parse an intent text in {SHORT[m]} {c}")
            reach[f"{SHORT[m]}|{c}"] = {"failed": len(eps), "reachable": sum(1 for f in flags if f), "share": sum(1 for f in flags if f) / len(eps)}
    out["reachable"] = reach

    # ---- agreement of fs_nonserializable with the three graph verdicts (aware off, core, both arms)
    dsg: Dict[str, Any] = {}
    for arm in ("contended", "control"):
        eps = [e for m in MODELS for c in CONFIGS for e in D.episodes(m, c, 0, arm)]
        row = {"episodes": len(eps), "fs": sum(e["fs"] for e in eps)}
        for g, key in (("all_reads", "dsg"), ("committed", "dsg_committed"), ("basis", "basis")):
            row[g + "_cycles"] = sum(e[key] for e in eps)
            row[g + "_fs_only"] = sum(1 for e in eps if e["fs"] and not e[key])
            row[g + "_graph_only"] = sum(1 for e in eps if e[key] and not e["fs"])
            row[g + "_disagree"] = row[g + "_fs_only"] + row[g + "_graph_only"]
        row["g1c"] = sum(e["dsg_g1c"] for e in eps)
        dsg[arm] = row
    out["dsg_agreement"] = dsg

    # ---- exploratory items of the registration: per wording, lease lengths, within-prompt variance, extension blocks,
    #      cost and turns, lock goodput with the deadlock stratum
    wording: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            eps = D.episodes(m, c, 0, "contended")
            if not eps:
                continue
            for w in (0, 1):
                sub = [e for e in eps if e["wording"] == w]
                wording[f"{SHORT[m]}|{c}|w{w}"] = {"n": len(sub), "fs": mean([e["fs"] for e in sub]) if sub else None}
    out["wording"] = wording
    lease: Dict[str, Any] = {}
    for m in MODELS:
        vals: List[int] = []
        for c in LOCK_CONFIGS:
            for arm in ("contended", "control"):
                for e in D.episodes(m, c, 0, arm):
                    vals += [int(c_["lease"]) for c_ in e["calls"] if c_["tool"] == "acquire_lock" and c_["status"] in (200, 423) and c_["lease"] is not None]
        if vals:
            vs = sorted(vals)
            counts: Dict[int, int] = {}
            for v in vs:
                counts[v] = counts.get(v, 0) + 1
            mode = max(sorted(counts), key=lambda k: counts[k])
            lease[SHORT[m]] = {"n": len(vs), "median": vs[len(vs) // 2], "min": vs[0], "max": vs[-1], "mode": mode,
                               "mode_share": counts[mode] / len(vs), "at_max": sum(1 for v in vs if v == 20) / len(vs)}
    out["lease"] = lease
    # within-prompt variance: the aware-off probe of an agent against the same agent's first reply in the matching
    # aware-off episodes (same request bytes): a0 contended probe vs a0 in the contended episodes, a1 contended vs a1
    # contended, a1 control vs a1 control
    wp: Dict[str, Any] = {}
    for m in MODELS:
        pairs = 0
        same = 0
        lockpairs = 0
        locksame = 0
        for c in CONFIGS:
            for (pm, pc, pa, fam, inst, arm), pr in sorted(D.pr.items(), key=lambda kv: str(kv[0])):
                if pm != m or pc != c or pa != 0:
                    continue
                for a, pav in pr["agents"].items():
                    for s in D.seeds(m, c, 0, fam, inst):
                        ep = D.ep.get((m, c, 0, fam, inst, s, arm))
                        if ep is None or a not in ep["agents"]:
                            continue
                        pairs += 1
                        same += int(pav["first_reply"] == ep["agents"][a]["first_reply"])
                        if c in LOCK_CONFIGS:
                            lockpairs += 1
                            locksame += int(pav["fr_lock"] == ep["agents"][a]["fr_lock"])
        if pairs:
            wp[SHORT[m]] = {"pairs": pairs, "same_code": same / pairs, "lock_pairs": lockpairs,
                            "same_lock": (locksame / lockpairs) if lockpairs else None}
    out["within_prompt"] = wp
    ext: Dict[str, Any] = {}
    for m in DESCRIPTIVE:
        for c in CONFIGS:
            for arm in ("contended", "control"):
                eps = E.episodes(m, c, 0, arm)
                if eps:
                    ext[f"{SHORT[m]}|{c}|{arm}"] = {"n": len(eps), "fs": mean([e["fs"] for e in eps]),
                                                    "families": sorted({e["family"] for e in eps}),
                                                    "instances": sorted({e["instance"] for e in eps})}
    out["extension"] = ext
    cost: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            eps = D.episodes(m, c, 0, "contended")
            if not eps:
                continue
            agents = [a for e in eps for a in e["agents"].values()]
            cost[f"{SHORT[m]}|{c}"] = {"episodes": len(eps), "cost_per_episode": mean([e["cost_usd"] for e in eps]),
                                       "completions_per_agent": mean([a["completions"] for a in agents]),
                                       "turns_per_agent": mean([a["turns"] for a in agents]),
                                       "input_tokens_per_agent": mean([a["input_tokens"] for a in agents]),
                                       "output_tokens_per_agent": mean([a["output_tokens"] for a in agents]),
                                       "input_tokens_total": sum(a["input_tokens"] for a in agents),
                                       "output_tokens_total": sum(a["output_tokens"] for a in agents),
                                       # registered exploratory items that were computed and not printed before
                                       # review T7b S-E: the reread choice and unnecessary give-ups
                                       "reread": (sum(1 for a in agents if a["reread_choice"]) / len(agents)) if agents else None,
                                       "give_up_n": sum(1 for a in agents if a["give_up"]), "agents": len(agents)}
    out["cost"] = cost
    goodput: Dict[str, Any] = {}
    for m in MODELS:
        for c in LOCK_CONFIGS:
            eps = D.episodes(m, c, 0, "contended")
            if not eps:
                continue
            dl = [e for e in eps if e["deadlock"]]
            nd = [e for e in eps if not e["deadlock"]]
            goodput[f"{SHORT[m]}|{c}"] = {"episodes": len(eps), "deadlock_episodes": len(dl),
                                          "fulfilled_no_deadlock": agent_rate(nd, "fulfilled") if nd else None,
                                          "fulfilled_deadlock": agent_rate(dl, "fulfilled") if dl else None,
                                          "fs_no_deadlock": mean([e["fs"] for e in nd]) if nd else None}
    out["lock_goodput"] = goodput

    # ---- H4 companion: primitive uptake among agents that attempted a write (review T6 S2)
    upt: Dict[str, Any] = {}
    for m in MODELS:
        for c in H4_CONFIGS:
            for arm in ("contended", "control"):
                eps = D.episodes(m, c, 0, arm)
                if not eps:
                    continue
                o = "lock" if c == "locks" else "prim"
                writers = [(e, a) for e in eps for a, av in e["agents"].items()
                           if any(c_["tool"] in ("update_record", "claim") for c_ in _agent_calls(e, a))]
                upt[f"{SHORT[m]}|{c}|{arm}"] = {"writers": len(writers), "agents": sum(len(e["agents"]) for e in eps),
                                                "uptake_among_writers": (sum(1 for e, a in writers if e["agents"][a][o]) / len(writers)) if writers else None,
                                                "uptake_all": agent_rate(eps, o)}
    out["uptake_writers"] = upt

    # ---- H3 per-unit values for the confirmatory models (how many (family, instance) units are non-zero) and the H4b
    #      cluster counts (for the captions)
    h3u: Dict[str, Any] = {}
    for m in CONFIRMATORY:
        units = sorted({(k[3], k[4]) for k in D.pr if k[0] == m and k[1] in LOCK_CONFIGS})
        n_units = 0
        nonzero = 0
        for fam, inst in units:
            ds = []
            for c in LOCK_CONFIGS:
                on = D.pr.get((m, c, 1, fam, inst, "contended"))
                off = D.pr.get((m, c, 0, fam, inst, "contended"))
                if on is None or off is None or "a0" not in on["agents"] or "a0" not in off["agents"]:
                    ds = None
                    break
                ds.append(int(on["agents"]["a0"]["fr_lock"]) - int(off["agents"]["a0"]["fr_lock"]))
            if ds is None:
                continue
            n_units += 1
            nonzero += int(sum(ds) != 0)
        h3u[SHORT[m]] = {"units": n_units, "nonzero": nonzero}
    out["h3_units"] = h3u
    ncl = [v["n_clusters"] for k, v in (res.get("h4b") or {}).items() if any(k.startswith(SHORT[m] + "|") for m in CONFIRMATORY) and v.get("n_clusters")]
    out["h4b_clusters"] = {"min": min(ncl) if ncl else None, "max": max(ncl) if ncl else None}

    # ---- the worked verdict example: one contended Haiku locks episode on inventory_last_unit (the stock-of-five case)
    ex = D.ep.get((HAIKU, "locks", 0, "inventory_last_unit", 0, 0, "contended"))
    if ex is not None:
        rid = next(iter(RECORD_RE.findall(ex["intents"]["a0"])))
        amounts = {a: int(re.search(r"\b(\d+)\b", ex["intents"][a]).group(1)) for a in ex["agents"]}
        first_read = next(c for c in ex["calls"] if c["tool"] == "get_record" and c["status"] == 200)
        calls = [{"agent": c["agent_id"], "own_call": c["own_call"], "tool": c["tool"], "record": c["record_id"], "status": c["status"],
                  "token": c["fencing_token"], "waited": c["waited_rounds"], "value": c["value"], "lease": c["lease"],
                  "read_version": c.get("read_version")} for c in ex["calls"]]
        out["example"] = {"id": ex["id"], "record": rid, "initial": first_read["value"], "amounts": amounts, "calls": calls,
                          "final": next((c["value"] for c in reversed(ex["calls"]) if c["committed"]), None),
                          "outcome": ex["outcome"], "label": ex["primary_label"], "fs": ex["fs"], "flags": {k: v for k, v in ex["flags"].items() if v},
                          "committed": ex["committed_agents"], "pattern": None, "reports": {a: ex["agents"][a]["final_text"] for a in ex["agents"]},
                          "stale_basis_agents": [a for a, av in ex["agents"].items() if av["fenced_stale_basis"] > 0],
                          "signals": {a: ex["agents"][a]["signals"] for a in ex["agents"]}}

    # ---- 423 responses that carry a version (all_available; the one rejection that reveals a version)
    out["locked_with_version"] = sum(1 for DD in (D, E) for e in DD.ep.values() for c_ in e["calls"] if c_["status"] == 423 and c_["ver_body"])

    # ---- exact bounds for the descriptive models' cells: the upper bound for an all-zero cell (0 failures of n contended
    #      episodes) and the lower bound for an all-failed cell (n of n; review T7b N-E)
    zb: Dict[str, Any] = {}
    for m in DESCRIPTIVE:
        for c in CONFIGS:
            eps = D.episodes(m, c, 0, "contended")
            if eps:
                k = sum(e["fs"] for e in eps)
                zb[f"{SHORT[m]}|{c}"] = {"n": len(eps), "failed": k, "upper": clopper_pearson_upper(k, len(eps)),
                                         "lower": clopper_pearson_lower(k, len(eps))}
    out["zero_bounds"] = zb

    # ---- the transfer family's share of the registered conditional-write Delta (review T5b S6/A9). The registered Delta
    #      is the mean over the (family, instance) clusters of the contended minus the control failure rate, so the
    #      transfer family's part is the sum of its cluster differences over the sum of all cluster differences. The mean
    #      of all cluster differences must equal the registered H1-diff estimate, or the script stops.
    tsh: Dict[str, Any] = {}
    for m in CONFIRMATORY:
        for c in ("cas_available", "all_available"):
            cl = cluster_arm_rates(D, m, c, 0, "fs")
            tot = sum(v[0] - v[1] for v in cl.values())
            xfer = sum(v[0] - v[1] for k, v in cl.items() if k[0] == "transfer_shared_source")
            regest = (reg["tests"].get(f"H1-diff|{SHORT[m]}|{c}") or {}).get("estimate")
            if not cl or regest is None or abs(tot / len(cl) - regest) > 1e-9:
                raise SystemExit(f"transfer share: cluster-mean difference for {SHORT[m]} {c} disagrees with results.json")
            tsh[f"{SHORT[m]}|{c}"] = {"clusters": len(cl), "delta": tot / len(cl), "transfer_part": xfer / len(cl),
                                      "share": (xfer / tot) if tot else None}
    out["transfer_share"] = tsh

    # ---- a signal the agent could perceive before its first primitive (review T7c A5): a response with status 409 or
    #      423, or a successful get_record that returned a value different from the agent's previous successful read of
    #      the same record, among the agent's calls before its first primitive call (score5 first_protective_call, an
    #      own-call index; all its calls if it used no primitive). Contended agents, lock configs, aware off, core blocks.
    perc: Dict[str, Any] = {}
    for m in MODELS:
        for c in LOCK_CONFIGS:
            eps = D.episodes(m, c, 0, "contended")
            if not eps:
                continue
            n_ag = 0
            k_ag = 0
            for e in eps:
                for a, av in e["agents"].items():
                    n_ag += 1
                    fpc = av["fp_call"]
                    seen: Dict[str, Any] = {}
                    hit = False
                    for c_ in _agent_calls(e, a):
                        if fpc is not None and c_["own_call"] is not None and c_["own_call"] >= fpc:
                            break
                        if c_["status"] in (409, 423):
                            hit = True
                            break
                        if c_["tool"] == "get_record" and c_["status"] == 200:
                            rid = c_["record_id"]
                            if rid in seen and seen[rid] != c_["value"]:
                                hit = True
                                break
                            seen[rid] = c_["value"]
                    k_ag += int(hit)
            perc[f"{SHORT[m]}|{c}"] = {"agents": n_ag, "perceivable": k_ag, "share": k_ag / n_ag}
    out["perceivable"] = perc

    # ---- compensated write-skew episodes and isolation (review T5b F16/A17): a saga gives up isolation. On the write-skew
    #      families each intent alone keeps the constraint and the two together break it, so the store is in the broken
    #      state while both agents' first changed records hold a value other than their initial one. Window: from the
    #      committed write that opens that state to the committed write that ends it (ledger order). Counted per
    #      compensated contended episode: whether such a window occurred, and whether an agent other than the one whose
    #      write closed the window read (get_record 200) a record of its intent inside it.
    cw: Dict[str, Any] = {}
    for m in MODELS:
        for c in CONFIGS:
            eps = [e for e in D.episodes(m, c, 0, "contended") if e["family"] in WS_FAMILIES and e["outcome"] == "compensated"]
            if not eps:
                continue
            row = {"episodes": len(eps), "with_window": 0, "peer_read_in_window": 0, "flag_violation": 0}
            for e in eps:
                row["flag_violation"] += int(bool(e["flags"].get("compensated_after_violation")))
                firstrec: Dict[str, str] = {}
                for ef in e["effects"]:
                    if not ef["noop"] and ef["agent_id"] not in firstrec:
                        firstrec[ef["agent_id"]] = ef["record_id"]
                if len(firstrec) < 2:
                    continue
                call_idx = {c_["effect_seq"]: i for i, c_ in enumerate(e["calls"]) if c_["committed"]}
                cur = {k: _num(v) for k, v in e["initial"].items()}
                init = dict(cur)
                windows: List[Tuple[int, int, str]] = []
                open_at: Optional[int] = None
                for ef in e["effects"]:
                    cur[ef["record_id"]] = _num(ef["new_value"])
                    broken = all(cur.get(r) != init.get(r) for r in firstrec.values())
                    i = call_idx.get(ef["seq"])
                    if broken and open_at is None:
                        open_at = i
                    elif not broken and open_at is not None:
                        windows.append((open_at, i, ef["agent_id"]))
                        open_at = None
                if not windows:
                    continue
                row["with_window"] += 1
                peer = False
                for lo, hi, closer in windows:
                    for c_ in e["calls"][lo + 1:hi]:
                        if (c_["agent_id"] != closer and c_["tool"] == "get_record" and c_["status"] == 200
                                and c_["record_id"] in set(RECORD_RE.findall(e["intents"].get(c_["agent_id"], "")))):
                            peer = True
                row["peer_read_in_window"] += int(peer)
            cw[f"{SHORT[m]}|{c}"] = row
    out["compensation_windows"] = cw

    # ---- Fable 5's lock scope in the extension blocks (descriptive; review T6b item 8): agents on the multi-record
    #      families under locks, contended arm, aware off, whose granted locks covered every record their intent names
    fx = [(e, a) for e in E.episodes(FABLE, "locks", 0, "contended") if e["family"] in MULTI_FAMILIES for a in e["agents"]]
    out["fable_ext_scope"] = {"agents": len(fx), "locked_all": sum(1 for e, a in fx if _lock_scope(e, a) == "all")}
    return out


# ---------------------------------------------------------------------------------------------------------------
# The registered cross-model regression (Statistical models, "Cross-model comparisons"): Firth-penalized logistic
# regression on the three common families, aware off, all four configs, both arms, with one parameter per
# model x config x arm cell plus family effects (the saturated interaction model the registration names), fitted by
# Newton iterations in the standard library; intervals from a wild cluster bootstrap (Rademacher weights on the
# family x instance clusters, 9,999 draws, score form: one Newton step from the fitted model per draw); plain
# cluster-robust (CR1) standard errors beside them (the registration asked for CR2, which is listed as not done).
# Cells with no events in either arm are reported as counts and left out, as registered. Descriptive only.
# ---------------------------------------------------------------------------------------------------------------

COMMON_FAMILIES = ("inventory_last_unit", "transfer_shared_source", "budget_write_skew")
FIRTH_DRAWS = 9999


def _mat_inverse(A: List[List[float]]) -> Tuple[List[List[float]], float]:
    """Gauss-Jordan inverse with partial pivoting; also returns log|det A| (A must be positive definite here)."""
    n = len(A)
    M_ = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    logdet = 0.0
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M_[r][col]))
        if abs(M_[piv][col]) < 1e-300:
            raise ArithmeticError("singular information matrix")
        if piv != col:
            M_[col], M_[piv] = M_[piv], M_[col]
        p = M_[col][col]
        logdet += math.log(abs(p))
        inv = 1.0 / p
        M_[col] = [v * inv for v in M_[col]]
        for r in range(n):
            if r != col and M_[r][col] != 0.0:
                f = M_[r][col]
                rowc = M_[col]
                M_[r] = [a - f * b for a, b in zip(M_[r], rowc)]
    return [row[n:] for row in M_], logdet


def _firth_fit(rows: Sequence[Tuple[Tuple[int, ...], int, str]], k: int) -> Dict[str, Any]:
    """Firth-penalized logistic regression. ``rows``: (nonzero column indices with value 1, y, cluster). Returns the
    estimate, the inverse information at the estimate, the per-cluster Firth-adjusted score sums and fit info."""
    beta = [0.0] * k

    def info_and_scores(b: List[float]):
        info = [[0.0] * k for _ in range(k)]
        pis = []
        for cols, y, g in rows:
            eta = sum(b[j] for j in cols)
            pi = 1.0 / (1.0 + math.exp(-eta)) if eta > -700 else 0.0
            w = pi * (1.0 - pi)
            pis.append(pi)
            for a in cols:
                ra = info[a]
                for c in cols:
                    ra[c] += w
        inv, logdet = _mat_inverse(info)
        score = [0.0] * k
        cluster_scores: Dict[str, List[float]] = {}
        contrib = []
        loglik = 0.0
        for (cols, y, g), pi in zip(rows, pis):
            h = pi * (1.0 - pi) * sum(inv[a][c] for a in cols for c in cols)  # leverage
            s_ = (y - pi) + h * (0.5 - pi)
            contrib.append(s_)
            cs = cluster_scores.setdefault(g, [0.0] * k)
            for j in cols:
                score[j] += s_
                cs[j] += s_
            loglik += math.log(pi) if y else math.log(1.0 - pi)
        return info, inv, logdet, score, cluster_scores, loglik + 0.5 * logdet

    info, inv, logdet, score, cs, pll = info_and_scores(beta)
    converged = False
    it = 0
    for it in range(1, 61):
        step = [sum(inv[j][c] * score[c] for c in range(k)) for j in range(k)]
        lam = 1.0
        while True:
            cand = [b + lam * s_ for b, s_ in zip(beta, step)]
            try:
                info2, inv2, logdet2, score2, cs2, pll2 = info_and_scores(cand)
            except (ArithmeticError, OverflowError, ValueError):
                pll2 = -math.inf
            if pll2 >= pll - 1e-10 or lam < 1e-4:
                break
            lam /= 2.0
        beta, info, inv, logdet, score, cs, pll = cand, info2, inv2, logdet2, score2, cs2, pll2
        if max(abs(v) for v in score) < 1e-8:
            converged = True
            break
    return {"beta": beta, "inv_info": inv, "cluster_scores": cs, "penalized_loglik": pll, "converged": converged,
            "iterations": it, "n": len(rows), "k": k}


def firth_regression(D: Data, reg: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"fits": {}}
    for outcome in ("fs", "lock"):
        # observations: episodes (fs) or agents (lock), with their cell and cluster
        obs: List[Tuple[str, str, str, str, str, int, int]] = []  # model, config, arm, family, cluster, y, wording-free
        for m in MODELS:
            for c in CONFIGS:
                for arm in ("contended", "control"):
                    for e in D.episodes(m, c, 0, arm):
                        if e["family"] not in COMMON_FAMILIES:
                            continue
                        g = f"{e['family']}|{e['instance']}"
                        if outcome == "fs":
                            obs.append((SHORT[m], c, arm, e["family"], g, int(e["fs"]), 0))
                        else:
                            for av in e["agents"].values():
                                obs.append((SHORT[m], c, arm, e["family"], g, int(av["lock"]), 0))
        # cells with no events in either arm are left out (reported as counts)
        events: Dict[Tuple[str, str], int] = {}
        counts: Dict[Tuple[str, str, str], Tuple[int, int]] = {}
        for sm, c, arm, fam, g, y, _ in obs:
            events[(sm, c)] = events.get((sm, c), 0) + y
            n, k_ = counts.get((sm, c, arm), (0, 0))
            counts[(sm, c, arm)] = (n + 1, k_ + y)
        dropped = sorted(k_ for k_, v in events.items() if v == 0)
        kept = [o for o in obs if events[(o[0], o[1])] > 0]
        cells = sorted({(o[0], o[1], o[2]) for o in kept})
        col_of = {cell: i for i, cell in enumerate(cells)}
        fam_cols = {f: len(cells) + i for i, f in enumerate([f for f in COMMON_FAMILIES[1:] if any(o[3] == f for o in kept)])}
        k = len(cells) + len(fam_cols)
        rows = []
        for sm, c, arm, fam, g, y, _ in kept:
            cols = (col_of[(sm, c, arm)],) + ((fam_cols[fam],) if fam in fam_cols else ())
            rows.append((cols, y, g))
        fit = _firth_fit(rows, k)
        beta, inv = fit["beta"], fit["inv_info"]
        clusters = sorted(fit["cluster_scores"])
        G = len(clusters)
        # CR1 sandwich
        meat = [[0.0] * k for _ in range(k)]
        for g in clusters:
            s_ = fit["cluster_scores"][g]
            for a in range(k):
                if s_[a] == 0.0:
                    continue
                for b in range(k):
                    meat[a][b] += s_[a] * s_[b]
        tmp = [[sum(inv[a][c] * meat[c][b] for c in range(k)) for b in range(k)] for a in range(k)]
        V = [[sum(tmp[a][c] * inv[c][b] for c in range(k)) * (G / (G - 1.0)) for b in range(k)] for a in range(k)]
        # quantities: the contention log-odds ratio per (model, config) and the contrasts among the confirmatory models
        quantities: Dict[str, List[Tuple[int, float]]] = {}
        for (sm, c) in sorted({(o[0], o[1]) for o in kept}):
            if (sm, c, "contended") in col_of and (sm, c, "control") in col_of:
                quantities[f"theta|{sm}|{c}"] = [(col_of[(sm, c, "contended")], 1.0), (col_of[(sm, c, "control")], -1.0)]
        pairs = [("Haiku", "Qwen"), ("Sonnet", "Qwen"), ("Sonnet", "Haiku")]
        for c in CONFIGS:
            for m1, m2 in pairs:
                q1, q2 = quantities.get(f"theta|{m1}|{c}"), quantities.get(f"theta|{m2}|{c}")
                if q1 and q2:
                    quantities[f"contrast|{m1}-{m2}|{c}"] = q1 + [(j, -v) for j, v in q2]
        est = {q: sum(v * beta[j] for j, v in lc) for q, lc in quantities.items()}
        se = {q: math.sqrt(max(sum(v1 * v2 * V[j1][j2] for j1, v1 in lc for j2, v2 in lc), 0.0)) for q, lc in quantities.items()}
        # wild cluster (score) bootstrap: Rademacher weights per cluster, one Newton step per draw
        rng = random.Random(f"20261103|firth|{outcome}")
        cs = [fit["cluster_scores"][g] for g in clusters]
        draws: Dict[str, List[float]] = {q: [] for q in quantities}
        # precompute, per quantity, the row vector c' I^{-1} so that a draw costs one dot product per cluster
        rowvec = {q: [sum(v * inv[j][c_] for j, v in lc) for c_ in range(k)] for q, lc in quantities.items()}
        proj = {q: [sum(rv[c_] * s_[c_] for c_ in range(k)) for s_ in cs] for q, rv in rowvec.items()}
        for _ in range(FIRTH_DRAWS):
            w = [1.0 if rng.getrandbits(1) else -1.0 for _ in range(G)]
            for q in quantities:
                draws[q].append(est[q] + sum(wi * pi_ for wi, pi_ in zip(w, proj[q])))
        ci = {}
        for q, ds in draws.items():
            ds.sort()
            lo = ds[int(math.floor(0.025 * FIRTH_DRAWS))]
            hi = ds[int(math.ceil(0.975 * FIRTH_DRAWS)) - 1]
            ci[q] = (lo, hi)
        out["fits"][outcome] = {"n": fit["n"], "k": k, "converged": fit["converged"], "iterations": fit["iterations"],
                                "clusters": G, "draws": FIRTH_DRAWS, "dropped_cells": [f"{a}|{b}" for a, b in dropped],
                                "cell_counts": {f"{a}|{b}|{c}": v for (a, b, c), v in sorted(counts.items())},
                                "estimates": est, "se_cr1": se, "ci95_wild": ci, "penalized_loglik": fit["penalized_loglik"],
                                # separation (review T7b S-F): a fitted model x config cell in which one arm has no
                                # event or nothing but events; the Firth estimate then sits at the penalty's boundary
                                # and the CR1 and score-bootstrap intervals are nominal
                                "separated_cells": sorted({f"{sm}|{c}" for (sm, c, arm), (n_, k_) in counts.items()
                                                           if (sm, c) not in set(dropped) and (k_ == 0 or k_ == n_)}),
                                "weight_vectors": 2 ** G}
    return out


# ---------------------------------------------------------------------------------------------------------------
# Macros, tables, facts
# ---------------------------------------------------------------------------------------------------------------


class Macros:
    """One \\newcommand per number; every table cell references one. ``src`` records the source for the facts file."""

    def __init__(self, registered: set, reserved: set):
        self.vals: Dict[str, str] = {}
        self.src: Dict[str, str] = {}
        self.group: Dict[str, str] = {}
        self.registered = registered
        self.reserved = reserved
        self.referenced_registered: set = set()
        self.current_group = "misc"

    def put(self, name: str, value: str, source: str) -> str:
        if name in self.vals and self.vals[name] != value:
            raise SystemExit(f"macro {name} defined twice with different values ({self.vals[name]!r} vs {value!r})")
        if name in self.registered:
            raise SystemExit(f"macro {name} collides with the registered numbers.tex")
        if name in self.reserved:
            raise SystemExit(f"macro {name} collides with a macro of latex/study2.tex")
        self.vals[name] = value
        self.src[name] = source
        self.group.setdefault(name, self.current_group)
        return "\\" + name + "{}"

    def ref(self, name: str) -> str:
        """Reference to a registered numbers.tex macro (must exist there)."""
        if name not in self.registered:
            raise SystemExit(f"table references registered macro \\{name}, which numbers.tex does not define")
        self.referenced_registered.add(name)
        return "\\" + name + "{}"

    def tex(self, header: Sequence[str]) -> str:
        lines = list(header)
        for k in sorted(self.vals):
            lines.append(r"\newcommand{\%s}{%s}" % (k, self.vals[k]))
        return "\n".join(lines) + "\n"


def tex_model(m: str) -> str:
    return NAME_MACRO[m] + "{}"


def _cells_text(cells: Sequence[str]) -> str:
    """'Model: config, config; Model: config' for a sorted list of 'Short|config' keys (caption text, model macros)."""
    by_model: Dict[str, List[str]] = {}
    for key in cells:
        sm, c = key.split("|")
        by_model.setdefault(sm, []).append(c)
    parts = []
    for m in MODELS:
        sm = SHORT[m]
        if sm in by_model:
            parts.append(tex_model(m) + ": " + ", ".join(tt(c) for c in CONFIGS if c in by_model[sm]))
    return "; ".join(parts) if parts else "none"


def tt(s: str) -> str:
    return r"\texttt{%s}" % tex_text(s)


def write_table(path: str, body: str, header_note: str) -> None:
    width = r"\textwidth" if r"\begin{table*}" in body else r"\columnwidth"
    # every tabular of the float is scaled down to the text width when it is wider (a float may stack several)
    body = re.sub(r"(\\begin\{tabular\})", lambda mm: r"\begin{adjustbox}{max width=%s}" % width + "\n" + mm.group(1), body)
    body = body.replace(r"\end{tabular}", r"\end{tabular}" + "\n" + r"\end{adjustbox}")
    head = ("% GENERATED by analysis5/descriptives5.py -- do not edit. Input: real data (Study 2, results.json dry_run=false).\n"
            "% Every value is a macro: \\SiiD... from study2_out/study2_numbers.tex, \\Sii... (registered) from analysis5/out_study2/numbers.tex,\n"
            "% model names from the Study 1 numbers.tex. " + header_note + "\n")
    with open(path, "w") as f:
        f.write(head + body)


def build_tables(dd: Mapping[str, Any], reg: Mapping[str, Any], M: Macros, tables_dir: str, deviations: Sequence[Mapping[str, str]]) -> None:
    os.makedirs(tables_dir, exist_ok=True)
    T = reg["tests"]
    note = "Registration: PREREGISTRATION_STUDY2.md, 'Pre-specified descriptive (no test, no Holm)' and 'Pre-specified checks'."
    # registered constants the captions cite (results.json constants and checks; the same values as the registration)
    M.current_group = "misc"
    const = reg["res"]["constants"]
    M.put("SiiDDeltaCell", fnum(const["delta_cell"]), "results.json constants.delta_cell (registration: delta per (model, config))")
    M.put("SiiDDeltaPooled", fnum(const["delta_pooled"]), "results.json constants.delta_pooled (registration: pooled delta)")
    M.put("SiiDAlpha", fnum(const["alpha"]), "results.json constants.alpha")
    M.put("SiiDEligibilityMax", fnum(const["eligibility_max"]), "results.json constants.eligibility_max (H4 eligibility threshold)")
    M.put("SiiDControlExposed", fint(reg["res"]["checks"]["exposure"]["control_agents_exposed"]), "results.json checks.exposure.control_agents_exposed")
    M.put("SiiDIsolationViolations", fint(reg["res"]["checks"]["isolation"]["control_episodes_with_cross_agent_edges"]), "results.json checks.isolation.control_episodes_with_cross_agent_edges")
    M.put("SiiDMutexViolations", fint(reg["res"]["checks"]["lock_safety"]["episodes_with_mutual_exclusion_violations"]), "results.json checks.lock_safety.episodes_with_mutual_exclusion_violations")

    # ------------------------------------------------------------------ (a) H1 table
    M.current_group = "a_h1"
    L = [r"\begin{table*}[t]", r"\centering\scriptsize", r"\begin{tabular}{@{}llcccccrl@{}}", r"\toprule",
         r"Model & config & contended & control & $\Delta$ & 95\,\% CI & $p_{\mathrm{Holm}}$ & clusters & registered reading \\",
         r"\midrule"]
    rows: List[Tuple[str, str, str, int, bool]] = []  # (model short, model tex, config, aware, pooled?)
    for m in CONFIRMATORY:
        rows += [(SHORT[m], tex_model(m), c, 0, False) for c in CONFIGS]
    rows += [("Pooled", "pooled (confirmatory)", c, 0, True) for c in CONFIGS]
    for m in DESCRIPTIVE:
        rows += [(SHORT[m], tex_model(m), c, 0, False) for c in CONFIGS]
    rows += [("Gemini", tex_model(GEMINI) + " (aware on)", c, 1, False) for c in LOCK_CONFIGS]
    prev = None
    dagger_bounds: List[str] = []  # caption text for every zero-width row: the exact bound on its contended episode rate
    for sm, mt, c, aware, pooled in rows:
        key = f"{sm}|{c}|aware{aware}"
        r = dd["h1"].get(key)
        if r is None:
            continue
        if prev is not None and (sm, aware) != prev:
            L.append(r"\addlinespace")
        label = mt if (sm, aware) != prev else ""
        prev = (sm, aware)
        base = f"transcripts: cluster-mean fs_nonserializable over complete pairs, {sm}, {c}, aware {aware}, core blocks"
        cont = M.put(macro("Fs", sm, CFG_SHORT[c], "On" if aware else "", "Cont"), fnum(r["cont"]), base + " (contended arm)")
        ctrl = M.put(macro("Fs", sm, CFG_SHORT[c], "On" if aware else "", "Ctrl"), fnum(r["ctrl"]), base + " (control arm)")
        if aware == 1:
            dmac = M.put(macro("Fs", sm, CFG_SHORT[c], "OnDelta"), fnum(r["delta"]), base + " (contended minus control; no registered interval)")
            L.append(f"{label} & {tt(c)} & {cont} & {ctrl} & {dmac} & \\textemdash{{}} & \\textemdash{{}} & "
                     f"{M.put(macro('Fs', sm, CFG_SHORT[c], 'OnClusters'), fint(r['clusters']), base + ' (clusters)')} & descriptive, aware on \\\\")
            continue
        test = "HoneCalDiff" if c == "none" else "HoneDiff"
        tid = f"{'H1cal-diff' if c == 'none' else 'H1-diff'}|{sm if not pooled else 'pooled'}|{c}"
        t = T.get(tid)
        est, lo, hi, n = (M.ref(reg_macro(test, sm, CFG_SHORT[c], s)) for s in ("Est", "Lo", "Hi", "N"))
        if t and t.get("status") == "tested":
            padj = (M.ref(reg_macro(test, sm, CFG_SHORT[c], "P")) + " (raw)") if c == "none" else M.ref(reg_macro(test, sm, CFG_SHORT[c], "Padj"))
        else:
            padj = r"\textemdash{}"
        ci = t.get("ci95") if t else None
        if ci and ci[0] == ci[1]:  # every cluster value equal: the percentile interval has zero width and is not an interval
            ci_cell = r"\textemdash{}$^\dagger$"
            zb = (dd["mech"].get("zero_bounds") or {}).get(f"{sm}|{c}")
            if zb and zb.get("failed") == 0:
                zn = zb["n"]
                ub = M.put(macro("ZeroBound", sm, CFG_SHORT[c]), fnum(zb["upper"]),
                           f"exact 97.5 % upper bound (Clopper-Pearson) on the contended fs share from 0 of {zn} episodes, {sm}, {c}")
                nn = M.put(macro("ZeroBound", sm, CFG_SHORT[c], "N"), fint(zn), f"contended episodes, {sm}, {c}")
                dagger_bounds.append(f"an upper bound of {ub} for 0 of {nn} episodes ({mt}, {tt(c)})")
            elif zb and zb.get("failed") == zb.get("n"):
                zn = zb["n"]
                lb = M.put(macro("FullBound", sm, CFG_SHORT[c]), fnum(zb["lower"]),
                           f"exact 97.5 % lower bound (Clopper-Pearson) on the contended fs share from {zn} of {zn} episodes, {sm}, {c}")
                nn = M.put(macro("FullBound", sm, CFG_SHORT[c], "N"), fint(zn), f"contended episodes, {sm}, {c}")
                dagger_bounds.append(f"a lower bound of {lb} for {nn} of {nn} episodes ({mt}, {tt(c)})")
        else:
            ci_cell = f"[{lo}, {hi}]"
        if c == "none":
            reading = "calibration: " + short_claim(t, "H1") if t and t.get("status") == "tested" else "calibration, descriptive"
        else:
            reading = short_claim(t, "H1")
            if t and t.get("status") == "tested" and T.get(f"H1-eq|{sm if not pooled else 'pooled'}|{c}", {}).get("status") == "not_tested_gate_closed":
                reading += "; H1-eq not tested (gate closed)"
            elif t and t.get("status") == "tested" and T.get(f"H1-eq|{sm if not pooled else 'pooled'}|{c}", {}).get("status") == "tested":
                reading += "; H1-eq " + ("rejects" if T[f"H1-eq|{sm if not pooled else 'pooled'}|{c}"].get("reject") else "does not reject")
        rd = M.put(macro("Claim", "Hone", sm, CFG_SHORT[c]), reading, f"results.json summary/tests[{tid}].claim and status (words only)")
        L.append(f"{label} & {tt(c)} & {cont} & {ctrl} & {est} & {ci_cell} & {padj} & {n} & {rd} \\\\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\SHone{}: \texttt{fs\_nonserializable} rate per arm and the registered contrast. Rates are cluster means "
          r"(family $\times$ instance) over complete contended--control pairs, aware off, core blocks; $\Delta$ is the registered "
          r"H1-diff estimate (mean of the cluster differences) with its 95\,\% percentile cluster-bootstrap interval and Holm-adjusted "
          r"one-sided sign-flip $p$ (H1-diff family; \texttt{none} is the calibration contrast at raw $\alpha$). ``Pooled'' is the "
          r"equal-weight mean over the confirmatory models on their common clusters. " + tex_model(GPT) + r", " + tex_model(GEMINI) +
          r" and " + tex_model(FABLE) + r" are descriptive (intervals, no test); " + tex_model(GEMINI) +
          r" aware-on episodes are reported apart and never pooled. \SHone-eq (TOST, $\delta=\SiiDDeltaCell$ per cell, \SiiDDeltaPooled{} pooled) was tested only pooled and "
          r"did not reject; its per-cell stage stayed closed. The calibration rows print the raw one-sided $p$ (no Holm). "
          r"$^\dagger$every cluster value is equal, so the percentile interval has zero width and is not an interval. Exact "
          r"one-sided Clopper--Pearson bounds (97.5\,\%, treating the episodes of a cell as independent, which they are not: "
          r"they share instances and schedule seeds) on the contended episode rate of these cells: " + "; ".join(dagger_bounds) + ".}",
          r"\label{tab:s2-h1}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_h1.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (b) primitive use: two tables (use; timing and endings)
    M.current_group = "b_primitives"
    cells: List[Tuple[str, str, str, int]] = []
    for m in MODELS:
        cells += [(SHORT[m], tex_model(m), c, 0) for c in CONFIGS]
    cells += [("Gemini", tex_model(GEMINI) + " (aware on)", c, 1) for c in LOCK_CONFIGS]
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lllcccccrcc@{}}", r"\toprule",
         r"Model & config & arm & lock att. & granted & effective (n) & cond.\ write & unprot.\ write & promoted & \CodeLocked{} waits & stale basis \\",
         r"\midrule"]
    L2 = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lllccc|cc|ccccc@{}}", r"\toprule",
          r"Model & config & arm & pre-emptive & reactive & never & lock after & exposed & fulfilled & abandoned & cap ends & cap-trunc. & compl. \\",
          r"\midrule"]
    prev = None
    for sm, mt, c, aware in cells:
        for arm in ("contended", "control"):
            key = f"main|{sm}|{c}|aware{aware}|{arm}"
            p = dd["primitives"].get(key)
            if p is None:
                continue
            if prev is not None and prev != (sm, aware):
                L.append(r"\addlinespace")
                L2.append(r"\addlinespace")
            label = mt if prev != (sm, aware) else ""
            prev = (sm, aware)
            A = "Cont" if arm == "contended" else "Ctrl"
            pre = ("Prim", sm, CFG_SHORT[c], "On" if aware else "", A)
            src = f"transcripts: share of agents, {sm}, {c}, aware {aware}, {arm} arm, core blocks ({p['agents']} agents, {p['episodes']} episodes)"
            dash = r"\textemdash{}"
            cell = [
                M.put(macro(*pre, "LockAtt"), fnum(p["lock"]), src + "; score5 lock (well-formed acquire_lock)"),
                M.put(macro(*pre, "LockGr"), fnum(p["lock_granted"]), src + "; score5 lock_granted"),
                M.put(macro(*pre, "LockEff"), fnum(p["lock_effective"]), src + f"; score5 lock_effective True among the {p['lock_effective_n']} lock-granted committing agents")
                + r"~{\tiny(" + M.put(macro(*pre, "LockEffN"), fint(p["lock_effective_n"]), src + "; agents with lock_effective not None") + ")}",
                M.put(macro(*pre, "Cas"), fnum(p["cas"]), src + "; score5 cas (conditional write committed or refused version_conflict)"),
                M.put(macro(*pre, "Naive"), fnum(p["naive"]), src + "; ledger effects: >=1 committed value-changing write with neither expected_version nor fencing_token"),
                M.put(macro(*pre, "PromotedN"), fint((dd["mech"]["promote"].get(f"{sm}|{c}|aware{aware}|{arm}") or {}).get("promoted")),
                      src + "; agents with the scorer's promote choice True (a committed no-op conditional write-back of a record the intent reads but does not write; count)"),
                M.put(macro(*pre, "WaitsFourTwoThree"), fint(p["lock_waits_423"]), src + "; sum of lock_waits_423 (acquires refused 423 after the wait)"),
                M.put(macro(*pre, "StaleBasis"), fint(p["fenced_stale_basis_agents"]), src + "; agents with fenced_stale_basis > 0 (count)"),
            ]
            L.append(f"{label} & {tt(c) if arm == 'contended' else ''} & {arm} & " + " & ".join(cell) + r" \\")
            cell2 = [
                M.put(macro(*pre, "PreEmpt"), fnum(p["preemptive"]), src + "; protect_before_contention True (first primitive at or before the first peer signal, or no signal)") if arm == "contended" else dash,
                M.put(macro(*pre, "Reactive"), fnum(p["reactive"]), src + "; protect_before_contention False (first primitive after the first peer signal)") if arm == "contended" else dash,
                M.put(macro(*pre, "Never"), fnum(p["never"]), src + "; protect_before_contention None (no primitive)") if arm == "contended" else dash,
                M.put(macro(*pre, "LockAfterN"), fint(p["lock_after_n"]), src + "; agents with lock_after_contention True (count)") if arm == "contended" else dash,
                M.put(macro(*pre, "Exposed"), fnum(p["exposed"]), src + "; contention_signals > 0") if arm == "contended" else dash,
                M.put(macro(*pre, "Fulfilled"), fnum(p["fulfilled"]), src + "; score5 fulfilled"),
                M.put(macro(*pre, "AbandonN"), fint(p["abandoned_n"]), src + "; agents with abandoned True (count)"),
                M.put(macro(*pre, "CapEnds"), fint(p["cap_endings"]), src + "; agents that ended at the call cap (count)"),
                M.put(macro(*pre, "CapTrunc"), fint(p["cap_truncated"]), src + "; episodes with cap_truncated (count)"),
                M.put(macro(*pre, "Compl"), fnum(p["completions"], 1), src + "; mean completions per agent"),
            ]
            L2.append(f"{label} & {tt(c) if arm == 'contended' else ''} & {arm} & " + " & ".join(cell2) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} primitive use per model, config and arm (share of agents; aware off unless stated; core blocks). "
          r"Lock att.: a well-formed \texttt{acquire\_lock} (granted or refused \CodeLocked{} after the wait); granted: at least one "
          r"grant; effective: among lock-granted agents that committed a write (count in parentheses), every committed write was "
          r"fenced and based on a read inside its lease. Cond.\ write: a write with \texttt{expected\_version} that committed or was "
          r"refused for its version (an \texttt{invalid\_version} refusal counts for \texttt{first\_protective} only). Unprot.\ write: "
          r"at least one committed value-changing write with neither \texttt{expected\_version} nor a fencing token. Promoted: agents "
          r"with the scorer's \texttt{promote} choice, a committed conditional write-back of a record the intent reads but does not "
          r"write whose value is unchanged (the promotion of \S\ref{sec:scoring}; count). \CodeLocked{} "
          r"waits: acquires refused after the wait (count); stale basis: agents with a fenced write whose basis read preceded its lease "
          r"(count). Pre-specified descriptive (no test); the registered H2 contrasts are in Supplement Tables~\ref{tab:s2-tests-full} "
          r"to~\ref{tab:s2-tests-full-3}.}",
          r"\label{tab:s2-primitives}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_primitives.tex"), "\n".join(L), note)
    L2 += [r"\bottomrule", r"\end{tabular}",
           r"\caption{\STwo{} timing of protection and endings per model, config and arm (share of agents unless a count; aware "
           r"off unless stated; core blocks). Pre-emptive, reactive, never: the agent's first primitive came at or before its first "
           r"peer-caused contention signal (or it saw none), after it, or it used none (\texttt{protect\_before\_contention}; "
           r"contended arm, where signals exist); lock after: agents whose first \texttt{acquire\_lock} followed their first signal "
           r"(count); exposed: agents with at least one signal. Fulfilled: the agent's last write applied its intent on its own view; "
           r"abandoned: agents that gave up a still-valid intent (count); cap ends: agents that ended at the call cap (count); "
           r"cap-trunc.: failed episodes with a cap ending (count); compl.: mean completions per agent. Pre-specified descriptive "
           r"(no test).}",
           r"\label{tab:s2-timing}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_timing.tex"), "\n".join(L2), note)

    # ------------------------------------------------------------------ (c) outcome classes
    M.current_group = "c_outcomes"
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lllr|ccc|ccc|cc@{}}", r"\toprule",
         r"Model & config & arm & $n$ & clean & comp. & failed & cap-trunc. & refusal/filter & agent err. & \texttt{fs} & basis DSG \\",
         r"\midrule"]
    L2 = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lllr|ccccccc@{}}", r"\toprule",
          r"Model & config & arm & failed ($n$) & missing leg & stale overwrite & lost update & write skew & guard viol. & out-of-intent & wrong value \\",
          r"\midrule"]
    prev = None
    for sm, mt, c, aware in cells:
        for arm in ("contended", "control"):
            key = f"main|{sm}|{c}|aware{aware}|{arm}"
            o = dd["outcomes"].get(key)
            if o is None:
                continue
            if prev is not None and prev != (sm, aware):
                L.append(r"\addlinespace")
                L2.append(r"\addlinespace")
            label = mt if prev != (sm, aware) else ""
            prev = (sm, aware)
            A = "Cont" if arm == "contended" else "Ctrl"
            pre = ("Out", sm, CFG_SHORT[c], "On" if aware else "", A)
            src = f"transcripts: {sm}, {c}, aware {aware}, {arm} arm, core blocks ({o['episodes']} episodes)"
            cell = [M.put(macro(*pre, "N"), fint(o["episodes"]), src + "; episodes"),
                    M.put(macro(*pre, "Clean"), fnum(o["clean"]), src + "; share outcome clean"),
                    M.put(macro(*pre, "Comp"), fnum(o["compensated"]), src + "; share outcome compensated"),
                    M.put(macro(*pre, "Failed"), fnum(o["failed"]), src + "; share outcome failed"),
                    M.put(macro(*pre, "CapTruncN"), fint(o["cap_truncated_n"]), src + "; cap_truncated episodes (count)"),
                    M.put(macro(*pre, "RefusalN"), fint(o["refusal_n"]), src + "; agents ended refusal or content_filter (count)"),
                    M.put(macro(*pre, "AgentErrN"), fint(o["agent_errors_n"]), src + "; agent_errors (count)"),
                    M.put(macro(*pre, "Fs"), fnum(o["fs"]), src + "; share fs_nonserializable (plain episode share)"),
                    M.put(macro(*pre, "Basis"), fnum(o["basis"]), src + "; share dsg_basis_cycle")]
            L.append(f"{label} & {tt(c) if arm == 'contended' else ''} & {arm} & " + " & ".join(cell) + r" \\")
            cell2 = [M.put(macro(*pre, "FailedN"), fint(o["failed_n"]), src + "; failed episodes (count)")]
            for f, nm in (("missing_leg", "MissingLeg"), ("stale_overwrite", "StaleOverwrite"), ("lost_update", "LostUpdate"),
                          ("write_skew", "WriteSkew"), ("guard_violation", "GuardViol"), ("out_of_intent_write", "OutOfIntent"),
                          ("wrong_value", "WrongValue")):
                cell2.append(M.put(macro(*pre, nm), fnum(o["flag_" + f]), src + f"; share of episodes with flag {f} (non-exclusive)"))
            L2.append(f"{label} & {tt(c) if arm == 'contended' else ''} & {arm} & " + " & ".join(cell2) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} outcome classes per model, config and arm (aware off unless stated; core blocks). Clean, compensated and "
          r"failed are exclusive shares of episodes (clean: fs-serializable, no constraint ever violated, no flag; compensated: only "
          r"rollback flags). Cap-trunc.: failed episodes in which an agent ended at the call cap (count); refusal/filter: agents whose "
          r"reply stopped for a refusal or safety filter (count); agent err.: agents that ended \texttt{truncated}, "
          r"\texttt{provider\_error} or \texttt{error} (count). \texttt{fs}: share of episodes \texttt{fs\_nonserializable} (the "
          r"primary measure; a plain episode share, which equals the cluster mean on this balanced grid); basis DSG: share with a cycle "
          r"in the per-write basis dependency graph (secondary). Pre-specified descriptive (no test).}",
          r"\label{tab:s2-outcomes}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_outcomes.tex"), "\n".join(L), note)
    L2 += [r"\bottomrule", r"\end{tabular}",
           r"\caption{\STwo{} failure mechanisms per model, config and arm (aware off unless stated; core blocks): non-exclusive flags as "
           r"shares of all episodes in the cell, next to the count of failed episodes. Missing leg: part of a multi-record intent "
           r"committed and not rolled back; stale overwrite: a committed write whose basis was older than the version it replaced; "
           r"lost update: a stale overwrite whose basis came from a read; write skew: the A5B pattern on value-changing writes; guard "
           r"violation: a write that ignored the agent's own condition; out-of-intent: a value-changing write outside the intent's "
           r"records; wrong value: any other committed, unfulfilled, not rolled-back write set. The flag shares include compensated "
           r"(rolled-back) episodes, so a flag can be non-zero in a cell with no failed episode. Pre-specified descriptive (no test).}",
           r"\label{tab:s2-flags}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_flags.tex"), "\n".join(L2), note)

    # ------------------------------------------------------------------ (d1) probes: first-reply lock by config x aware
    M.current_group = "d_probes"
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}llr|cc|c|cccc|c@{}}", r"\toprule",
         r" & & & \multicolumn{2}{c|}{a0, contended} & & \multicolumn{4}{c|}{a1 (leakage check)} & \\",
         r"Model & config & units & aware off & aware on & on $-$ off & cont.\ off & ctrl.\ off & cont.\ on & ctrl.\ on & elig.\ rate \\",
         r"\midrule"]
    prev = None
    for m in MODELS:
        for c in CONFIGS:
            off, on = dd["probes"].get(f"{SHORT[m]}|{c}|aware0"), dd["probes"].get(f"{SHORT[m]}|{c}|aware1")
            if off is None and on is None:
                continue
            if prev is not None and prev != m:
                L.append(r"\addlinespace")
            label = tex_model(m) if prev != m else ""
            prev = m
            sm = SHORT[m]
            src = f"probe transcripts: {sm}, {c}, share of (family, instance) units whose first reply has a lock token"

            def P(d: Optional[Mapping[str, Any]], k: str, nm: str, what: str) -> str:
                if d is None or d.get(k) is None:
                    return r"\textemdash{}"
                return M.put(macro("Fr", sm, CFG_SHORT[c], nm), fnum(d[k]), src + f"; {what}")
            units = M.put(macro("Fr", sm, CFG_SHORT[c], "Units"), fint((off or on)["units"]), src + "; probed (family, instance) units")
            h3c = dd["h3"].get(sm, {}).get("per_config", {}).get(c)
            if c in LOCK_CONFIGS and h3c is not None:
                diff = M.put(macro("Hthree", sm, CFG_SHORT[c], "Est"), fnum(h3c), f"results.json tests[H3|{sm}|locks+all_available].per_config.{c}.estimate (a0 lock_on - lock_off, mean over units; reported without test)")
            else:
                diff = r"\textemdash{}"
            elig = M.ref(reg_macro("Elig", sm, CFG_SHORT[c], "Rate")) if (sm != "Fable") else r"\textemdash{}"
            L.append(f"{label} & {tt(c)} & {units} & {P(off, 'a0_lock', 'AzeroOff', 'a0 contended, aware off')} & "
                     f"{P(on, 'a0_lock', 'AzeroOn', 'a0 contended, aware on')} & {diff} & "
                     f"{P(off, 'a1_cont_lock', 'AoneContOff', 'a1 contended, aware off')} & {P(off, 'a1_ctrl_lock', 'AoneCtrlOff', 'a1 control, aware off')} & "
                     f"{P(on, 'a1_cont_lock', 'AoneContOn', 'a1 contended, aware on')} & {P(on, 'a1_ctrl_lock', 'AoneCtrlOn', 'a1 control, aware on')} & {elig} \\\\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} first-reply probes: share of probed (family, instance) units whose first completion contains a "
          r"\texttt{lock} token (\texttt{model\_agent5.first\_reply\_code}; one completion from the initial prompt, nothing executed). "
          r"a0's prompt is byte-identical across arms, so only a0 contended is probed; a1's two prompts differ only in the group tag "
          r"(leakage check, Table~\ref{tab:s2-h3-leak}). On $-$ off is the registered per-config H3 estimate (a0, reported without a "
          r"test; the registered H3 test pools \texttt{locks} and \texttt{all\_available}). Elig.\ rate: the registered H4 eligibility "
          r"rate (share of aware-off contended probe agents, a0 and a1, with a \texttt{lock} or \texttt{cas} token; a model enters H4 "
          r"below \SiiDEligibilityMax). No first reply carried a \texttt{cas} token; under \texttt{none} and \texttt{cas\_available} no lock "
          r"tool exists, so those rows are 0 by construction. " + tex_model(FABLE) + r" has no probe block.}",
          r"\label{tab:s2-probes}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_probes.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (d2) H3 and the leakage check per model
    M.current_group = "d_h3_leak"
    L = [r"\begin{table*}[t]", r"\centering\scriptsize", r"\begin{tabular}{@{}lcccl|ccc@{}}", r"\toprule",
         r" & \multicolumn{4}{c|}{H3: aware on $-$ off, a0 first-reply lock} & \multicolumn{3}{c}{leakage: a1 contended $-$ control} \\",
         r"Model & $\Delta$ & 95\,\% CI & $p_{\mathrm{Holm}}$ & reading & $d$ & 95\,\% CI & $p$ \\", r"\midrule"]
    for m in MODELS:
        sm = SHORT[m]
        h = dd["h3"].get(sm)
        lk = dd["leakage"].get(sm) or {}
        if h is None or h.get("estimate") is None:
            h3cells = [r"\textemdash{}", r"\textemdash{}", r"\textemdash{}", "not run (no probes)"]
        else:
            est, lo, hi = (M.ref(reg_macro("Hthree", sm, "LocksAll", s)) for s in ("Est", "Lo", "Hi"))
            padj = M.ref(reg_macro("Hthree", sm, "LocksAll", "Padj")) if h.get("status") == "tested" else r"\textemdash{}"
            if h.get("status") == "tested" and h.get("p_adj") is not None and h["p_adj"] >= 0.001 and float(f"{h['p_adj']:.3f}") != h["p_adj"]:
                # review F1 N1: three decimals would round the exact p (0.0625 printed as 0.062); print four
                padj = M.put(macro("Hthree", sm, "PadjExact"), f"{h['p_adj']:.4f}", f"results.json tests[H3|{sm}|locks+all_available].p_adj, four decimals")
            reading = M.put(macro("Claim", "Hthree", sm), h["short"] if h.get("status") == "tested" else "descriptive",
                            f"results.json tests[H3|{sm}|locks+all_available].claim (words only)")
            ci = h.get("ci95") or [None, None]
            h3cells = [est, (r"\textemdash{}$^\dagger$" if ci[0] is not None and ci[0] == ci[1] else f"[{lo}, {hi}]"), padj, reading]
        if lk.get("status") == "tested":
            lo, hi = lk["ci95"]
            lo_m = M.put(macro("Leak", sm, "Lo"), fnum(lo), f"results.json checks.leakage.{sm}.ci95[0]")
            hi_m = M.put(macro("Leak", sm, "Hi"), fnum(hi), f"results.json checks.leakage.{sm}.ci95[1]")
            lkcells = [M.ref(reg_macro("Leak", sm, "Est")),
                       (r"\textemdash{}$^\dagger$" if lo == hi else f"[{lo_m}, {hi_m}]"),
                       M.ref(reg_macro("Leak", sm, "P"))]
        else:
            lkcells = [r"\textemdash{}", r"\textemdash{}", r"\textemdash{}"]
        L.append(f"{tex_model(m)} & " + " & ".join(h3cells) + " & " + " & ".join(lkcells) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} H3 and the leakage check (first-reply probes). H3: per (family, instance) unit, the mean over "
          r"\texttt{locks} and \texttt{all\_available} of a0's first-reply lock with minus without the aware sentence; one-sided "
          r"sign-flip test, Holm over the three confirmatory models (the descriptive models carry intervals and no test). Leakage: "
          r"per (config, aware, family, instance) unit under the two lock configs, a1's first-reply lock in the contended minus the "
          r"control probe; two-sided sign-flip test at $\alpha=\SiiDAlpha$, no Holm; a non-rejection is not evidence of no leakage. "
          r"Intervals are 95\,\% percentile cluster-bootstrap intervals; they are unadjusted for multiplicity and liberal when few "
          r"units are non-zero, and the exact sign-flip $p$ governs (" + tex_model(HAIKU) + r" \SHthree{}: the interval excludes zero "
          r"but only \SiiDHthreeHaikuNonzeroUnits{} of \SiiDHthreeHaikuUnits{} units are non-zero, so the exact $p$ cannot fall below "
          r"\SiiDHthreeHaikuMinP{}, which it reached, and the test could not reject at $\alpha=\SiiDAlpha$). "
          r"$^\dagger$every unit value is equal, so the percentile interval has zero width and is not an interval.}",
          r"\label{tab:s2-h3-leak}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_h3_leak.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (e) exposure check
    M.current_group = "e_exposure"
    fams = [f for f in CONFIGS_FAMILY_ORDER]
    fam_head = {"inventory_last_unit": "last unit", "inventory_still_valid": "still valid", "transfer_shared_source": "transfer",
                "budget_write_skew": "budget", "joint_account_write_skew": "joint acct", "seat_same": "seat", "ticket_same": "ticket"}
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}llc|" + "c" * len(fams) + "@{}}", r"\toprule",
         r"Model & config & all & " + " & ".join(fam_head[f] for f in fams) + r" \\", r"\midrule"]
    prev = None
    exp_rows = [(SHORT[m], c, aware) for m in MODELS for aware in (0, 1) for c in CONFIGS if f"{SHORT[m]}|{c}|aware{aware}" in dd["exposure"]]
    for sm, c, aware in exp_rows:
        key = f"{sm}|{c}|aware{aware}"
        e = dd["exposure"][key]
        m = next(mm for mm in MODELS if SHORT[mm] == sm)
        if prev is not None and prev != (sm, aware):
            L.append(r"\addlinespace")
        label = (tex_model(m) + (" (aware on)" if aware else "")) if prev != (sm, aware) else ""
        prev = (sm, aware)
        pre = ("Exp", sm, CFG_SHORT[c], "On" if aware else "")
        src = f"results.json checks.exposure.cells[{key}]"
        allm = M.put(macro(*pre, "All"), fnum(e["estimate"]), src + ".estimate (mean over clusters of the share of contended agents with contention_signals > 0)")
        ests, cis = [], []
        for f in fams:
            fe = e["families"].get(f)
            if fe is None:
                ests.append(r"\textemdash{}")
                cis.append("")
                continue
            ests.append(M.put(macro(*pre, FAM_SHORT[f], "Est"), fnum(fe["estimate"]), src + f".families.{f}.estimate"))
            lo_m = M.put(macro(*pre, FAM_SHORT[f], "Lo"), fnum(fe["ci95"][0]), src + f".families.{f}.ci95[0]")
            hi_m = M.put(macro(*pre, FAM_SHORT[f], "Hi"), fnum(fe["ci95"][1]), src + f".families.{f}.ci95[1]")
            cis.append(r"\textemdash{}$^\dagger$" if fe["ci95"][0] == fe["ci95"][1] else f"[{lo_m}, {hi_m}]")
        L.append(f"{label} & {tt(c)} & {allm} & " + " & ".join(ests) + r" \\")
        L.append(r" & & & " + " & ".join(r"{\tiny %s}" % x if x else "" for x in cis) + r" \\")
    for m in MODELS:
        if not any(k.startswith(SHORT[m] + "|") for k in dd["exposure"]):
            L.append(f"{tex_model(m)} & \\multicolumn{{{2 + len(fams)}}}{{l}}{{not run}} \\\\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} exposure check (the manipulation check of contention): share of contended agents with at least one "
          r"peer-caused contention signal (\texttt{contention\_signals} $>0$: a \CodeLocked, a \CodeConflict{} version conflict, a "
          r"held acquire, a grant after a peer's lock, a read of a peer's version or a write over one), per model $\times$ config, all "
          r"families and per family, with 95\,\% percentile cluster-bootstrap intervals (second line; registered check 2; aware off "
          r"unless stated; core blocks). Columns: \texttt{inventory\_last\_unit}, \texttt{inventory\_still\_valid}, "
          r"\texttt{transfer\_shared\_source}, \texttt{budget\_write\_skew}, \texttt{joint\_account\_write\_skew}, "
          r"\texttt{seat\_same}, \texttt{ticket\_same}. Control agents coded as exposed: \SiiDControlExposed{} (must be 0). Under the lock "
          r"configs, when both agents lock the same record only the one that comes second can meet the other's lock, and on the "
          r"write-skew families an agent that locks only its own record does not meet the other's lock; so the share stayed at or "
          r"below one half in these data, an observed maximum and not a bound (a read of a peer's version also counts). The per-family intervals rest on four clusters and are nominal; $^\dagger$a cell whose clusters all agree "
          r"prints no interval, since a zero-width percentile interval is not an interval.}",
          r"\label{tab:s2-exposure}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_exposure.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (f) H4 reactive rates
    M.current_group = "f_h4"
    L = [r"\begin{table*}[t]", r"\centering\scriptsize", r"\begin{tabular}{@{}llrcccccc l|rrrcc@{}}", r"\toprule",
         r" & & & \multicolumn{7}{c|}{H4: primitive uptake, contended $-$ control} & \multicolumn{5}{c}{H4b: at-risk contended agents} \\",
         r"Model & config & clusters & contended & control & $\Delta$ & 95\,\% CI & 90\,\% CI$_t$ & $q$ & reading & at risk & reacting & clusters & share [95\,\% CI] & lock after (of at risk) \\",
         r"\midrule"]
    order = [(SHORT[m], tex_model(m)) for m in CONFIRMATORY] + [("Pooled", "pooled (eligible)")] + [(SHORT[m], tex_model(m)) for m in DESCRIPTIVE]
    prev = None
    h4b_dagger: List[str] = []  # caption notes for H4b shares whose interval has zero width
    for sm, mt in order:
        for c in H4_CONFIGS:
            r = dd["h4"].get(f"{sm}|{c}")
            if r is None:
                continue
            if prev is not None and prev != sm:
                L.append(r"\addlinespace")
            label = mt if prev != sm else ""
            prev = sm
            o = "lock attempt" if c == "locks" else "any primitive"
            src = f"transcripts: cluster-mean share of agents with {o}, {sm}, {c}, aware off, complete pairs, core blocks"
            cont = M.put(macro("Hfour", sm, CFG_SHORT[c], "Cont"), fnum(r["cont"]), src + " (contended arm)")
            ctrl = M.put(macro("Hfour", sm, CFG_SHORT[c], "Ctrl"), fnum(r["ctrl"]), src + " (control arm)")
            ncl = M.put(macro("Hfour", sm, CFG_SHORT[c], "Clusters"), fint(r["clusters"]), src + " (clusters, family x instance)")
            est, lo, hi, q = (M.ref(reg_macro("HfourDiff", sm, CFG_SHORT[c], s)) for s in ("Est", "Lo", "Hi", "Q"))
            lot, hit = (M.ref(reg_macro("HfourEq", sm, CFG_SHORT[c], s)) for s in ("LoNinety", "HiNinety"))
            td, te = T.get(f"H4-diff|{sm if sm != 'Pooled' else 'pooled'}|{c}") or {}, T.get(f"H4-eq|{sm if sm != 'Pooled' else 'pooled'}|{c}") or {}
            c95 = td.get("ci95") or [None, None]
            c90t = te.get("ci90_t") or [None, None]
            ci95_cell = r"\textemdash{}$^\dagger$" if c95[0] is not None and c95[0] == c95[1] else f"[{lo}, {hi}]"
            ci90_cell = r"\textemdash{}$^\dagger$" if c90t[0] is not None and c90t[0] == c90t[1] else f"[{lot}, {hit}]"
            reading = M.put(macro("Claim", "Hfour", sm, CFG_SHORT[c]), r["short"] if r.get("status") == "tested" else ("descriptive" if r.get("status") == "descriptive" else str(r.get("status") or "not run").replace("_", " ")),
                            f"results.json tests[H4-eq|{sm}|{c}].claim and status (words only)")
            hb = r.get("h4b")
            if hb and hb.get("agents_at_risk"):
                hsrc = f"results.json h4b[{sm}|{c}]"
                atr = M.put(macro("HfourB", sm, CFG_SHORT[c], "AtRisk"), fint(hb["agents_at_risk"]), hsrc + ".agents_at_risk")
                rea = M.put(macro("HfourB", sm, CFG_SHORT[c], "Reacting"), fint(hb["agents_reacting"]), hsrc + ".agents_reacting")
                hcl = M.put(macro("HfourB", sm, CFG_SHORT[c], "Clusters"), fint(hb.get("n_clusters")), hsrc + ".n_clusters (clusters with an agent at risk)")
                if hb.get("estimate") is not None:
                    sh = M.put(macro("HfourB", sm, CFG_SHORT[c], "Est"), fnum(hb["estimate"]), hsrc + ".estimate (mean over clusters of the reacting share)")
                    lo_b = M.put(macro("HfourB", sm, CFG_SHORT[c], "Lo"), fnum(hb["ci95"][0]), hsrc + ".ci95[0]")
                    hi_b = M.put(macro("HfourB", sm, CFG_SHORT[c], "Hi"), fnum(hb["ci95"][1]), hsrc + ".ci95[1]")
                    if hb["ci95"][0] == hb["ci95"][1]:
                        ci = r"\textemdash{}$^\dagger$"
                        h4b_dagger.append(f"{mt} {tt(c)}: {rea} of {atr} at-risk agents reacting in {hcl} clusters")
                    else:
                        ci = f"[{lo_b}, {hi_b}]"
                    shc = f"{sh}~{ci}"
                else:
                    shc = r"\textemdash{}"
                la = M.put(macro("HfourB", sm, CFG_SHORT[c], "LockAfter"), fint(hb["agents_at_risk_lock_after_contention"]), hsrc + ".agents_at_risk_lock_after_contention")
            elif hb is not None:
                atr = M.put(macro("HfourB", sm, CFG_SHORT[c], "AtRisk"), fint(hb["agents_at_risk"]), f"results.json h4b[{sm}|{c}].agents_at_risk")
                rea, hcl, shc, la = r"\textemdash{}", r"\textemdash{}", r"\textemdash{}", r"\textemdash{}"
            else:
                atr = rea = hcl = shc = la = r"\textemdash{}"
            L.append(f"{label} & {tt(c)} & {ncl} & {cont} & {ctrl} & {est} & {ci95_cell} & {ci90_cell} & {q} & {reading} & {atr} & {rea} & {hcl} & {shc} & {la} \\\\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} H4: primitive uptake per arm and the registered contrast (\texttt{lock} attempt under \texttt{locks}, any "
          r"primitive under \texttt{all\_available}; cluster means of agent shares over complete pairs, aware off, core blocks; the "
          r"first clusters column counts the family $\times$ instance clusters that enter). "
          r"$\Delta$ is the registered estimate with the 95\,\% percentile interval (H4-diff) and the 90\,\% bootstrap-$t$ interval of "
          r"the TOST (H4-eq, $\delta=\SiiDDeltaCell$ per cell, \SiiDDeltaPooled{} pooled); $q$ is the mean cluster share of contended "
          r"agents at risk (a signal and no earlier primitive); an equivalence with $q\leq\delta$ is uninformative by the registered "
          r"gate. ``Pooled'' covers the eligible confirmatory models (eligibility from the posted probe rates). H4b: at-risk contended "
          r"agents, those whose first primitive followed their first signal, the clusters with such an agent, the cluster-mean reacting "
          r"share with its 95\,\% interval (nominal, from \SiiDHfourBMinClusters{} to \SiiDHfourBMaxClusters{} clusters for the "
          r"confirmatory models) and the at-risk agents whose first \texttt{acquire\_lock} followed a signal. Under \texttt{all\_available} "
          r"the control rate is \SiiDHfourHaikuAllCtrl{} in every cluster of every confirmatory model, so $\Delta\leq0$ by construction "
          r"and the difference test cannot reject there. Percentile intervals are unadjusted for multiplicity and liberal when few "
          r"clusters are non-zero; the exact sign-flip $p$ governs (" + tex_model(SONNET) + r" \texttt{locks}: raw $p=\SiiHfourDiffSonnetLocksP$, "
          r"Holm-adjusted \SiiHfourDiffSonnetLocksPadj). $^\dagger$every cluster value is equal, so the interval has zero width and is not "
          r"an interval: in a marked H4 row uptake is at the same level in both arms of every cluster, and a marked H4b share has the "
          r"same reacting share in every at-risk cluster (" + "; ".join(h4b_dagger) + r").}",
          r"\label{tab:s2-h4}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_h4.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (g) budget and spend
    M.current_group = "g_budget"
    b = dd["budget"]
    L = [r"\begin{table}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lrrrrrr@{}}", r"\toprule",
         r"Provider & estimate & $\times$\SiiDSafety & cap & spend & of cap & in transcripts \\", r"\midrule"]
    M.put("SiiDSafety", fnum(b["total"]["safety"]), "plan_study2.json safety")
    for p in PROVIDERS:
        r = b["providers"][p]
        pn = PROV_SHORT[p]
        L.append(f"{PROV_NAME[p]} & " + " & ".join([
            M.put(macro("Est", pn), fmoney(r["estimate"]), f"plan_study2.json estimate_by_family.{p} (USD)"),
            M.put(macro("EstSafe", pn), fmoney(r["estimate_safe"]), f"plan_study2.json estimate_by_family.{p} x safety (USD)"),
            M.put(macro("Cap", pn), fmoney(r["cap"]), f"plan_study2.json caps.{p} (USD)"),
            M.put(macro("Spend", pn), fmoney(r["spend"]), f"sum of cost_usd over every Study 2 spend.jsonl (lanes and preflight) with provider_family {p} (USD)"),
            M.put(macro("SpendShare", pn), fnum(r["share_of_cap"]), f"spend / cap, {p}"),
            M.put(macro("SpendEp", pn), fmoney(r["recorded_in_transcripts"]), f"sum of totals.cost_usd over written transcripts (core, probe and extension), provider_family {p} (USD)"),
        ]) + r" \\")
    t = b["total"]
    L.append(r"\midrule")
    L.append("total & " + " & ".join([
        M.put("SiiDEstTotal", fmoney(t["estimate"]), "plan_study2.json estimate_total (USD)"),
        M.put("SiiDEstSafeTotal", fmoney(t["estimate_safe"]), "plan_study2.json estimate_total x safety (USD)"),
        M.put("SiiDCapTotal", fmoney(t["cap"]), "plan_study2.json total_cap (USD)"),
        M.put("SiiDSpendTotal", fmoney(t["spend"]), "sum of the three provider spends (USD)"),
        M.put("SiiDSpendShareTotal", fnum(t["share_of_cap"]), "total spend / total cap"),
        M.put("SiiDSpendEpTotal", fmoney(t["recorded_in_transcripts"]), "sum of totals.cost_usd over all written transcripts (USD)"),
    ]) + r" \\")
    L.append(r"\midrule")
    L.append(r"\multicolumn{7}{@{}l}{Spend by model (spend log; written transcripts)} \\")
    for m in MODELS:
        r = b["models"][SHORT[m]]
        L.append(f"{tex_model(m)} & & & & {M.put(macro('SpendModel', SHORT[m]), fmoney(r['spend']), f'sum of cost_usd over spend.jsonl entries with model {m} (USD)')} & & "
                 f"{M.put(macro('SpendEpModel', SHORT[m]), fmoney(r['recorded_in_transcripts']), f'sum of totals.cost_usd over written transcripts of {m} (USD)')} \\\\")
    w = b["window"]
    L.append(r"\midrule")
    L.append(r"\multicolumn{7}{@{}l}{Shared OpenRouter key: usage window around the OpenRouter lane (\texttt{balance5.py})} \\")
    if w:
        wsrc = "results.json budget.windows[0]"
        others = abs(w["others_spend_usd"]) if abs(w["others_spend_usd"]) < 0.005 else w["others_spend_usd"]
        wrows = [
            ("window start (UTC)", M.put("SiiDWindowFrom", tex_text(w["from_utc"]), wsrc + ".from_utc")),
            ("window end (UTC)", M.put("SiiDWindowTo", tex_text(w["to_utc"]), wsrc + ".to_utc")),
            ("key usage change", M.put("SiiDWindowKeyChange", fmoney(w["key_usage_change_usd"]), wsrc + ".key_usage_change_usd")),
            (r"\STwo{} OpenRouter spend in the window", M.put("SiiDWindowStudySpend", fmoney(w["study2_spend_usd"]), wsrc + ".study2_spend_usd")),
            ("spend by others", M.put("SiiDWindowOthers", fmoney(others), wsrc + ".others_spend_usd (rounded; the raw value is float noise of order 1e-13)")),
            ("lane exit code", M.put("SiiDWindowLaneExit", str(w.get("lane_exit")), wsrc + ".lane_exit")),
            ("stopped by an external cause", M.put("SiiDWindowExternalStop", "yes" if w.get("stopped_by_external_cause") else "no", wsrc + ".stopped_by_external_cause")),
        ]
        for lab, val in wrows:
            L.append(r"\quad " + lab + r" & \multicolumn{6}{r}{" + val + r"} \\")
    else:
        L.append(r"\multicolumn{7}{@{}l}{no balance window recorded} \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} budget and spend (USD). Estimates and caps are the registered plan's (\texttt{plan\_study2.json}); spend "
          r"is the sum of every Study 2 spend log (probe, core and extension blocks and the preflight; batch prices at the 0.5 factor), "
          r"and the last column the cost recorded in the written transcripts, which omits the completions of aborted episodes "
          r"(provider failures, rerun from scratch) and the preflight. No cap stopped a lane. The OpenRouter key is shared with "
          r"another project: others' spend in the window is the key's usage change minus \STwo's logged OpenRouter spend.}",
          r"\label{tab:s2-budget}", r"\end{table}", ""]
    write_table(os.path.join(tables_dir, "s2_budget.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (h) selection and exclusions
    M.current_group = "h_selection"
    s = dd["selection"]
    L = [r"\begin{table}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lr@{}}", r"\toprule", r"Item & count \\", r"\midrule"]
    L.append("transcripts read & " + M.put("SiiDFiles", fint(s["files"]), "number of transcript files under n2-*/transcripts and probe-*/transcripts") + r" \\")
    L.append(r"\quad probe block (priority 0) & " + M.put("SiiDProbeFiles", fint(s["block"].get("priority_0", 0)), "rows whose plan block has priority 0") + r" \\")
    L.append(r"\quad core block (priority 1) & " + M.put("SiiDCoreFiles", fint(s["block"].get("priority_1", 0)), "rows whose plan block has priority 1") + r" \\")
    L.append(r"\quad extension block (priority 4, descriptive only) & " + M.put("SiiDExtFiles", fint(s["block"].get("priority_4", 0)), "rows whose lowest plan block has priority 4") + r" \\")
    L.append(r"\quad unplanned rows & " + M.put("SiiDUnplannedFiles", fint(s["block"].get("unplanned", 0)), "rows in no plan block") + r" \\")
    for m in MODELS:
        sm = SHORT[m]
        parts = []
        for pr, nm in (("priority_0", "Probe"), ("priority_1", "Core"), ("priority_4", "Ext")):
            parts.append(M.put(macro("N", sm, nm), fint(s["block_by_model"].get(f"{sm}|{pr}", 0)), f"rows of {m} in plan blocks of {pr}"))
        L.append(f"\\quad {tex_model(m)}: probe / core / extension & {parts[0]} / {parts[1]} / {parts[2]} \\\\")
    L.append(r"\midrule")
    nd = sum(s["never_data"].values())
    L.append("never-data rows (dry run, other study, unregistered) & " + M.put("SiiDNeverData", fint(nd), "rows failing the never-data rules") + r" \\")
    L.append("duplicate transcripts for one episode id & " + M.put("SiiDDuplicates", fint(s["counts"].get("duplicate_transcripts_ignored", 0)), "selection: duplicate_transcripts_ignored") + r" \\")
    L.append("excluded: agent error, refusal or safety stop & " + M.put("SiiDExclError", fint(s["counts"].get("agent_error_or_refusal", 0)), "selection: agent_error_or_refusal") + r" \\")
    L.append(r"excluded: " + tex_model(QWEN) + " served by another host & " + M.put("SiiDExclHost", fint(s["counts"].get("wrong_host", 0)), "selection: wrong_host") + r" \\")
    L.append("excluded as the partner of an excluded row & " + M.put("SiiDExclPartner", fint(s["counts"].get("partner_excluded", 0)), "selection: partner_excluded") + r" \\")
    L.append(r"provider failures, " + tex_model(GPT) + r" (\texttt{none} / \texttt{locks} / \texttt{all\_available}) & "
             + " / ".join(M.put(macro("ProvFail", "Gpt", CFG_SHORT[c]), fint(s["provider_failures"].get(f"openrouter_openai_gpt-5.5-20260423|{c}", 0)),
                                f"failures.jsonl lines for GPT episodes under {c}") for c in ("none", "locks", "all_available")) + r" \\")
    L.append("provider failures, all models & " + M.put("SiiDProvFailTotal", fint(s["provider_failures_total"]), "failures.jsonl lines, all lanes") + r" \\")
    L.append(tex_model(GPT) + r" episodes with a non-OpenAI host, core / extension & "
             + M.put("SiiDGptAzureEpisodes", fint(s["gpt_non_openai_episodes_main"]), "kept core or probe rows of GPT with a served_host not starting with openai") + " / "
             + M.put("SiiDGptAzureEpisodesExt", fint(s["gpt_non_openai_episodes_extension"]), "extension rows of GPT with a served_host not starting with openai") + r" \\")
    L.append(r"\quad their completions served by Azure & " + M.put("SiiDGptAzureCompletions", fint(s["gpt_non_openai_completions"]), "GPT completions (all blocks) with served_host not starting with openai") + r" \\")
    L.append(tex_model(QWEN) + " episodes with a non-Alibaba host & " + M.put("SiiDQwenOtherHost", fint(s["qwen_non_alibaba_episodes"]), "rows of Qwen with a served_host not starting with alibaba") + r" \\")
    L.append(r"\texttt{cap\_truncated} episodes, core / extension & " + M.put("SiiDCapTruncated", fint(s["cap_truncated_main"]), "core episodes with cap_truncated True") + " / "
             + M.put("SiiDCapTruncatedExt", fint(s["cap_truncated_extension"]), "extension episodes with cap_truncated True") + r" \\")
    L.append("agents ended at the call cap (core) & " + M.put("SiiDCapEndings", fint(s["cap_endings_main"]), "sum of score cap_endings over core episodes") + r" \\")
    L.append("agents ended in a refusal or safety stop (core) & " + M.put("SiiDRefusalAgents", fint(s["refusal_agents"]), "core agents with end_reason refusal or content_filter") + r" \\")
    L.append(r"agents ended in a harness or provider error (core) & " + M.put("SiiDErrorAgents", fint(s["error_agents"]), "core agents with an error end reason") + r" \\")
    L.append(r"agents that did not end \texttt{returned} (core) & " + M.put("SiiDNotReturned", fint(s["not_returned_agents"]), "core agents with end_reason other than returned") + r" \\")
    L.append("agents that abandoned (core) & " + M.put("SiiDAbandoned", fint(s["abandoned_agents"]), "core agents with abandoned True") + r" \\")
    L.append("deadlock episodes (core) & " + M.put("SiiDDeadlocks", fint(s["deadlock_episodes"]), "core episodes with deadlock True") + r" \\")
    L.append(r"\midrule")
    L.append(r"\multicolumn{2}{@{}l}{\texttt{temperature\_effective} per completion, all blocks (value: completions / all)} \\")
    for m in MODELS:
        sm = SHORT[m]
        d = s["temperature_effective"].get(sm, {})
        parts = []
        for k in sorted(d):
            nm = {"null": "Null", "unverified": "Unverified", "ignored_by_provider": "Ignored", "0.0": "Zero"}.get(k, "".join(ch for ch in k.title() if ch.isalpha()))
            parts.append(tt(k) + " " + M.put(macro("Temp", sm, nm), fint(d[k]), f"completions of {m} with temperature_effective {k} (all blocks)"))
        tot = M.put(macro("Temp", sm, "All"), fint(s["completions_by_model"].get(sm, 0)), f"completions of {m} (all blocks)")
        L.append(f"\\quad {tex_model(m)} & " + "; ".join(parts) + f" / {tot} \\\\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} rows read, block membership (\texttt{plan\_study2.json}: probe 0, core 1, extension 4), exclusions under the "
          r"registered rules and flags. Extension blocks (larger " + tex_model(GPT) + r" and " + tex_model(FABLE) +
          r" grids, run while money was left) enter no registered statistic and are reported apart. Provider failures are episodes "
          r"aborted on a provider error and rerun from scratch by the lane (spend counted, no transcript). The temperature rows "
          r"record what each provider reports: the Claude models reject the parameter (null), OpenRouter does not confirm it "
          r"(unverified) and Gemini ignores it.}",
          r"\label{tab:s2-selection}", r"\end{table}", ""]
    write_table(os.path.join(tables_dir, "s2_selection.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (h2) deviations table (complete; page-sized parts)
    M.current_group = "h_deviations"

    def breakable(s: str) -> str:  # long identifiers (paths, episode ids) may break after _ / . in a narrow p-column
        return s.replace(r"\_", r"\_\allowbreak{}").replace("/", r"/\allowbreak{}").replace("...", r"...\allowbreak{}")

    rows_dev = [" & ".join(r"\raggedright " + breakable(row[k]) for k in ("deviation", "reason", "before_after", "effect", "registered_result")) + r" \tabularnewline"
                for row in deviations]
    # a row is as tall as its tallest cell; about 70 lines of \scriptsize text fit on one page, so rows are grouped by
    # their estimated height (characters per line from the column widths 0.2/0.16/0.12/0.2/0.18 of the text width)
    cpl = {"deviation": 21, "reason": 17, "before_after": 12, "effect": 21, "registered_result": 18}
    parts: List[List[str]] = [[]]
    height = 0.0
    for row, rt in zip(deviations, rows_dev):
        h = max(len(row[k]) / cpl[k] for k in cpl) + 1.0
        if parts[-1] and height + h > 112:
            parts.append([])
            height = 0.0
        parts[-1].append(rt)
        height += h
    for stale in glob.glob(os.path.join(tables_dir, "s2_deviations_*.tex")):  # parts of an earlier run
        os.remove(stale)
    for k, part in enumerate(parts, 1):
        L = [r"\begin{table*}[p]", r"\centering\scriptsize",
             r"\begin{tabular}{p{0.2\textwidth}p{0.16\textwidth}p{0.12\textwidth}p{0.2\textwidth}p{0.18\textwidth}}", r"\toprule",
             r"Deviation & reason & before/after data & effect & registered-plan result \\", r"\midrule"] + part
        L += [r"\bottomrule", r"\end{tabular}",
              r"\caption{Deviations from the \STwo{} registration and the notes its reporting rules require (part " + str(k) + " of " + str(len(parts)) +
              r"; from \texttt{STUDY2\_RUN\_LOG.md}, the transcripts and \texttt{results.json}; the same columns as the \SOne{} table). "
              r"Rows that begin with ``Note'' are not departures from the registration text.}",
              r"\label{tab:s2-deviations" + ("" if k == 1 else f"-{k}") + "}", r"\end{table*}", ""]
        write_table(os.path.join(tables_dir, f"s2_deviations_{k}.tex"), "\n".join(L), note)
    with open(os.path.join(tables_dir, "s2_deviations_all.tex"), "w") as f:  # one include for main.tex, whatever the part count
        f.write("% GENERATED by analysis5/descriptives5.py -- inputs every part of the deviations table\n"
                + "".join("\\input{study2_out/tables/s2_deviations_%d.tex}\n" % k for k in range(1, len(parts) + 1)))
    M.put("SiiDDeviationParts", str(len(parts)), "number of parts of the Study 2 deviations table")
    M.put("SiiDDeviationRows", fint(len(deviations)), "rows of the Study 2 deviations table")

    # ------------------------------------------------------------------ (i) integrity by config vs none
    M.current_group = "i_vs_none"
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}llcccrcrrr@{}}", r"\toprule",
         r"Model & config & fs & fs, \texttt{none} & diff. & clusters & fulfilled & cap ends & deadlocks & agent err. \\", r"\midrule"]
    prev = None
    for m in MODELS:
        for c in H1_CONFIGS:
            v = dd["vs_none"].get(f"{SHORT[m]}|{c}")
            if v is None or v["clusters"] == 0:
                continue
            if prev is not None and prev != m:
                L.append(r"\addlinespace")
            label = tex_model(m) if prev != m else ""
            prev = m
            sm = SHORT[m]
            src = f"transcripts: contended arm, aware off, core blocks, {sm}; clusters common to {c} and none"
            L.append(f"{label} & {tt(c)} & " + " & ".join([
                M.put(macro("VsNone", sm, CFG_SHORT[c], "Fs"), fnum(v["fs"]), src + f"; cluster-mean fs_nonserializable under {c}"),
                M.put(macro("VsNone", sm, CFG_SHORT[c], "FsNone"), fnum(v["fs_none"]), src + "; cluster-mean fs_nonserializable under none"),
                M.put(macro("VsNone", sm, CFG_SHORT[c], "Diff"), fnum(v["diff"]), src + f"; mean over clusters of fs({c}) - fs(none)"),
                M.put(macro("VsNone", sm, CFG_SHORT[c], "Clusters"), fint(v["clusters"]), src + "; clusters"),
                M.put(macro("VsNone", sm, CFG_SHORT[c], "Fulfilled"), fnum(v["fulfilled"]), src + f"; share of contended agents fulfilled under {c}"),
                M.put(macro("VsNone", sm, CFG_SHORT[c], "CapEnds"), fint(v["cap_endings"]), src + f"; cap_endings under {c} (count)"),
                M.put(macro("VsNone", sm, CFG_SHORT[c], "Deadlocks"), fint(v["deadlock"]), src + f"; deadlock episodes under {c} (count)"),
                M.put(macro("VsNone", sm, CFG_SHORT[c], "AgentErr"), fint(v["agent_errors"]), src + f"; agent_errors under {c} (count)"),
            ]) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} integrity by config against \texttt{none}, paired by cluster (contended arm, aware off, core blocks): "
          r"cluster-mean \texttt{fs\_nonserializable} under the config and under \texttt{none} on the same clusters, their mean "
          r"difference, and fulfilment, cap endings, deadlocks and agent errors under the config. Every agent of every core episode "
          r"ended \texttt{returned}, so the registered variant restricted to episodes in which every agent ended on its own is "
          r"identical. Pre-specified descriptive (no test).}",
          r"\label{tab:s2-vs-none}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_vs_none.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (j) first_protective under all_available
    M.current_group = "j_first_protective"
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}llcccr|cccr@{}}", r"\toprule",
         r" & & \multicolumn{4}{c|}{update templates} & \multicolumn{4}{c}{claim templates} \\",
         r"Model & arm & lock & cond.\ write & none & agents & lock & cond.\ write & none & agents \\", r"\midrule"]
    prev = None
    for m in MODELS:
        for arm in ("contended", "control"):
            cells_ = []
            any_data = False
            for group in ("update", "claim"):
                v = dd["first_protective"].get(f"{SHORT[m]}|{arm}|{group}")
                A = "Cont" if arm == "contended" else "Ctrl"
                G = "Upd" if group == "update" else "Claim"
                src = f"transcripts: all_available, aware off, core blocks, {SHORT[m]}, {arm} arm, {group} templates; share of agents by first_protective"
                if v is None or not v["agents"]:
                    cells_ += [r"\textemdash{}"] * 4
                    continue
                any_data = True
                cells_ += [M.put(macro("Fp", SHORT[m], A, G, "Lock"), fnum(v["lock"]), src + " = lock"),
                           M.put(macro("Fp", SHORT[m], A, G, "Cas"), fnum(v["cas"]), src + " = cas"),
                           M.put(macro("Fp", SHORT[m], A, G, "None"), fnum(v["none"]), src + " = None"),
                           M.put(macro("Fp", SHORT[m], A, G, "N"), fint(v["agents"]), src + "; agents")]
            if not any_data:
                continue
            if prev is not None and prev != m:
                L.append(r"\addlinespace")
            label = tex_model(m) if prev != m else ""
            prev = m
            L.append(f"{label} & {arm} & " + " & ".join(cells_) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\STwo{} under \texttt{all\_available}: the first protective primitive an agent used (\texttt{first\_protective}: "
          r"lock, conditional write, or none), share of agents, on the update templates (both inventory templates, transfer, budget, "
          r"joint account) and apart on the claim templates (seat, ticket), per arm (aware off, core blocks). The core blocks of " +
          tex_model(GPT) + r" (three common families) and " + tex_model(FABLE) + r" (two) contain no claim template. "
          r"Pre-specified descriptive (no test).}",
          r"\label{tab:s2-first-protective}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_first_protective.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (k) EXPLORATORY: fs_nonserializable per family
    M.current_group = "k_family_fs"
    fams = list(CONFIGS_FAMILY_ORDER)
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}llc|" + "c" * len(fams) + "@{}}", r"\toprule",
         r"Model & config & control, all & " + " & ".join(fam_head[f] for f in fams) + r" \\", r"\midrule"]
    prev = None
    for m in MODELS:
        for c in CONFIGS:
            row = dd["family_fs"].get(f"{SHORT[m]}|{c}")
            if row is None:
                continue
            if prev is not None and prev != m:
                L.append(r"\addlinespace")
            label = tex_model(m) if prev != m else ""
            prev = m
            sm = SHORT[m]
            src = f"transcripts: share fs_nonserializable, {sm}, {c}, aware off, core blocks"
            cells_ = [M.put(macro("FamFs", sm, CFG_SHORT[c], "Ctrl"), fnum(row["control_fs"]), src + ", control arm, all families")]
            for f in fams:
                fe = row[f]
                if fe["n"] == 0:
                    cells_.append(r"\textemdash{}")
                else:
                    cells_.append(M.put(macro("FamFs", sm, CFG_SHORT[c], FAM_SHORT[f]), fnum(fe["fs"]), src + f", contended arm, family {f} ({fe['n']} episodes)"))
            L.append(f"{label} & {tt(c)} & " + " & ".join(cells_) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{EXPLORATORY (registration, Exploratory analysis: per-family breakdowns). \STwo{} \texttt{fs\_nonserializable} share "
          r"of contended episodes per family (columns as in Table~\ref{tab:s2-exposure}; eight episodes per cell for the 28-cluster models, "
          r"four for " + tex_model(GPT) + r", two for " + tex_model(FABLE) + r") next to the control arm's share over all families "
          r"(aware off, core blocks). Supports no claim; the registered estimand weights the seven families equally.}",
          r"\label{tab:s2-family-fs}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_family_fs.tex"), "\n".join(L), note)


def build_mech_tables(dd: Mapping[str, Any], reg: Mapping[str, Any], M: Macros, tables_dir: str) -> None:
    """Tables for the post hoc mechanism counts (added after reviews T5 to T8), the registered-tests appendix table
    and the completed deviations table. Every number is a macro."""
    T = reg["tests"]
    mech = dd["mech"]
    note = "POST HOC mechanism counts (added after the T5 to T8 reviews); rules in the captions and in descriptives5.mechanisms."
    dash = r"\textemdash{}"

    # ------------------------------------------------------------------ (m1) lock-failure mechanisms + protocol order
    M.current_group = "m1_lock_mech"
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lr|rrrr|rr@{}}", r"\toprule",
         r"Model & failed & read-then-lock & write skew, guard records not locked & no lock & missing leg & write skew, all & any stale write \\", r"\midrule"]
    excl_notes: List[str] = []  # caption: exclusivity of the three mechanisms and the lock-scope pairs (reviews T7b, T8b N4f, S-G)
    for m in MODELS:
        r = mech["lock_mech"][SHORT[m]]
        sm = SHORT[m]
        src = f"transcripts: fs-failed contended locks episodes of {sm}, aware off, core blocks; mechanism sets (non-exclusive)"
        L.append(f"{tex_model(m)} & " + " & ".join([
            M.put(macro("LockMech", sm, "Failed"), fint(r["failed"]), src + "; failed episodes"),
            M.put(macro("LockMech", sm, "ReadThenLock"), fint(r["read_then_lock"]), src + "; a stale overwrite that is a fenced write with a pre-lease basis (fenced_stale_basis)"),
            M.put(macro("LockMech", sm, "OwnOnly"), fint(r["write_skew_own_only"]), src + "; write_skew flag and at least one agent whose granted locks did not cover the guard records its constraint reads (it locked only its own record, or nothing)"),
            M.put(macro("LockMech", sm, "NoLock"), fint(r["no_lock"]), src + "; a stale overwrite that is an unfenced write (no lock)"),
            M.put(macro("LockMech", sm, "MissingLeg"), fint(r["missing_leg"]), src + "; missing_leg flag"),
            M.put(macro("LockMech", sm, "WriteSkew"), fint(r["write_skew"]), src + "; write_skew flag (any lock scope)"),
            M.put(macro("LockMech", sm, "AnyStale"), fint(r["any_stale"]), src + "; at least one stale overwrite"),
        ]) + r" \\")
        one = M.put(macro("LockMech", sm, "ExactlyOne"), fint(r["exactly_one"]), src + "; episodes with exactly one of the three mechanisms (read-then-lock, guard records not locked, no lock)")
        many = M.put(macro("LockMech", sm, "MoreThanOne"), fint(r["more_than_one"]), src + "; episodes with more than one of the three mechanisms")
        other = M.put(macro("LockMech", sm, "NoneOfThree"), fint(r["none_of_three"]), src + "; failed episodes with none of the three mechanisms")
        bo = M.put(macro("LockMech", sm, "OwnOnlyBothOwn"), fint(r["own_only_both_own"]), src + "; guard-records-not-locked episodes in which both agents locked only their own record")
        on = M.put(macro("LockMech", sm, "OwnOnlyOneNone"), fint(r["own_only_one_none"]), src + "; guard-records-not-locked episodes in which one agent locked nothing")
        oa = M.put(macro("LockMech", sm, "OwnOnlyOneAll"), fint(r["own_only_one_all"]), src + "; guard-records-not-locked episodes in which one agent locked every intent record while the other locked only its own")
        if r["failed"]:
            excl_notes.append(f"{tex_model(m)}: {one} with exactly one mechanism, {many} with more than one, {other} with none "
                              f"(lock-scope pairs of the guard-records-not-locked episodes: both own {bo}, one agent nothing {on}, one agent every record {oa})")
    L += [r"\midrule", r"\multicolumn{8}{@{}l}{Protocol order and lock scope, share of agents (contended arm; lock scope on the three multi-record families)} \\",
          r"Model & config & arm & lock first & read, then lock & no lock & locked every intent record & locked own only \\", r"\midrule"]
    prev = None
    for m in MODELS:
        for c in LOCK_CONFIGS:
            for arm in ("contended", "control"):
                r = mech["protocol_order"].get(f"{SHORT[m]}|{c}|{arm}")
                if r is None:
                    continue
                if prev is not None and prev != m:
                    L.append(r"\addlinespace")
                label = tex_model(m) if prev != m else ""
                prev = m
                sm = SHORT[m]
                A = "Cont" if arm == "contended" else "Ctrl"
                src = f"transcripts: agents of {sm}, {c}, {arm} arm, aware off, core blocks ({r['agents']} agents; lock scope over the {r['multi_agents']} multi-record-family agents)"
                L.append(f"{label} & {tt(c)} & {arm} & " + " & ".join([
                    M.put(macro("Order", sm, CFG_SHORT[c], A, "LockFirst"), fnum(r["lock_first"]), src + "; first well-formed acquire_lock before the first successful read"),
                    M.put(macro("Order", sm, CFG_SHORT[c], A, "ReadThenLock"), fnum(r["read_then_lock"]), src + "; first successful read before the first well-formed acquire_lock"),
                    M.put(macro("Order", sm, CFG_SHORT[c], A, "NoLock"), fnum(r["no_lock"]), src + "; no well-formed acquire_lock"),
                    M.put(macro("Order", sm, CFG_SHORT[c], A, "LockedAll"), fnum(r["locked_all"]), src + "; granted locks cover every record named in the agent's intent"),
                    M.put(macro("Order", sm, CFG_SHORT[c], A, "LockedOwn"), fnum(r["locked_own"]), src + "; granted locks cover some but not every record named in the intent"),
                ]) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC. Top: mechanism of every \texttt{fs\_nonserializable} contended \texttt{locks} episode (aware off, core blocks; "
          r"counts of episodes, non-exclusive). Read-then-lock: a stale overwrite that is a fenced write whose basis read preceded its "
          r"lease (\texttt{fenced\_stale\_basis}). Write skew, guard records not locked: the \texttt{write\_skew} flag with at least one "
          r"agent whose granted locks never covered the guard records its constraint reads (it locked only the record it wrote, or "
          r"nothing: the lock analogue of write skew). No lock: a stale "
          r"overwrite that is an unfenced write. Missing leg: the \texttt{missing\_leg} flag. The three mechanisms are counted as "
          r"sets, and on the data they are exclusive and exhaustive except for the missing-leg episodes (" + "; ".join(excl_notes) + "). "
          r"The descriptive models had no failed "
          r"\texttt{locks} episode. Bottom: protocol order per agent (first well-formed \texttt{acquire\_lock} before or after the first "
          r"successful read, or none) and, on the transfer, budget and joint-account families, whether the agent's granted locks covered "
          r"every record its intent names (the protocol of the scripted \texttt{lock\_protected} agent, which locks every record its "
          r"guard reads, in sorted order, before reading) or only some of them.}",
          r"\label{tab:s2-lock-mech}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_lock_mech.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (m2) half-done transfers and after a 409
    M.current_group = "m2_missing_leg"
    ml = mech["missing_leg"]
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lr|rrrrr|rr|rr|r|rr@{}}", r"\toprule",
         r"Model & agents & same reply & after re-read & before rej. & later, no re-read & no debit & re-read $=$ expected & \texttt{list\_effects} & first rej.\ \CodeConflict & first rej.\ \CodeLocked & reported success & credit only & of which reversed \\", r"\midrule"]
    for key, label in [(SHORT[m], tex_model(m)) for m in MODELS] + [("Confirmatory", "confirmatory models")]:
        r = ml.get(key)
        if r is None or not (r["agents"] or r["credit_only"]):
            continue
        src = f"transcripts: missing_leg agents of {key}, transfer family, cas_available and all_available, contended arm, aware off, core blocks"
        srct = f"transcripts: transfer agents of {key}, cas_available and all_available, contended arm, aware off, core blocks (committed legs from the ledger effects)"
        L.append(f"{label} & " + " & ".join([
            M.put(macro("MissingLeg", key, "Agents"), fint(r["agents"]), src + "; agents with missing_leg True"),
            M.put(macro("MissingLeg", key, "SameReply"), fint(r["same_reply"]), src + "; first committed credit sent in the same assistant reply as the first rejected debit (any rejection status)"),
            M.put(macro("MissingLeg", key, "AfterReread"), fint(r["credit_after_reread"]), src + "; credit sent after a re-read of the source that followed the rejection"),
            M.put(macro("MissingLeg", key, "BeforeRejection"), fint(r["credit_before_rejection"]), src + "; credit sent in a reply before the rejected debit"),
            M.put(macro("MissingLeg", key, "LaterNoReread"), fint(r["credit_later_no_reread"]), src + "; credit sent in a later reply with no re-read in between"),
            M.put(macro("MissingLeg", key, "NoDebit"), fint(r["no_debit_attempted"]), src + "; no debit call at all"),
            M.put(macro("MissingLeg", key, "SawExpected"), fint(r["saw_expected"]), src + "; a re-read of the source after the first rejection returned first-read value minus the transfer amount"),
            M.put(macro("MissingLeg", key, "Listed"), fint(r["listed_effects"]), src + "; the agent called list_effects"),
            M.put(macro("MissingLeg", key, "RejFourOhNine"), fint(r["first_rejection_409"]), src + "; first rejected debit was a 409"),
            M.put(macro("MissingLeg", key, "RejFourTwoThree"), fint(r["first_rejection_423"]), src + "; first rejected debit was a 423"),
            M.put(macro("MissingLeg", key, "ReportedSuccess"), fint(r["reported_success"]), src + "; final reply matches SUCCESS_RE and not NEGATION_RE (the rule of the false-success table)")
            + r"~{\tiny(" + M.put(macro("MissingLeg", key, "NamesConcurrent"), fint(r["names_concurrent"]), src + "; final reply names a concurrent process or another agent (CONCURRENT_RE)") + ")}",
            M.put(macro("Transfer", key, "CreditOnly"), fint(r["credit_only"]), srct + "; agents with a committed value-changing credit and no committed debit (the missing-leg agents plus the agents that reversed the credit)"),
            M.put(macro("Transfer", key, "Repaired"), fint(r["credit_only_repaired"]), srct + "; of these, agents the scorer marks rolled_back (the credit reversed; the episode's outcome is compensated)"),
        ]) + r" \\")
        M.put(macro("Transfer", key, "RepairedSawExpected"), fint(r["credit_only_repaired_saw_expected"]),
              srct + "; rolled-back credit-only agents whose re-read of the source after the first rejection returned the expected post-debit balance")
    # rolled-back agents per model, config and arm (all families) and the confirmatory totals by family group
    rbk = mech["rolled_back"]
    for m in MODELS:
        sm = SHORT[m]
        for c in CONFIGS:
            for arm in ("contended", "control"):
                v = rbk.get(f"{sm}|{c}|{arm}")
                if v is not None:
                    M.put(macro("RolledBack", sm, CFG_SHORT[c], "Cont" if arm == "contended" else "Ctrl"), fint(v["rolled_back"]),
                          f"transcripts: agents of {sm} the scorer marks rolled_back, {c}, {arm} arm, aware off, core blocks, all families ({v['agents']} agents)")
    conf_keys = [k for k in rbk if k.split("|")[0] in [SHORT[m] for m in CONFIRMATORY] and k.endswith("|contended")]
    M.put("SiiDRolledBackConfirmatoryTotal", fint(sum(rbk[k]["rolled_back"] for k in conf_keys)),
          "transcripts: contended agents of the three confirmatory models the scorer marks rolled_back, all configs and families, aware off, core blocks")
    M.put("SiiDRolledBackConfirmatoryTransfer", fint(sum(rbk[k]["by_family"].get("transfer_shared_source", 0) for k in conf_keys)),
          "transcripts: of these, agents on the transfer family")
    M.put("SiiDRolledBackConfirmatoryClaim", fint(sum(rbk[k]["by_family"].get(f, 0) for k in conf_keys for f in CLAIM_FAMILIES)),
          "transcripts: of these, agents on the seat and ticket families")
    M.put("SiiDRolledBackConfirmatoryWriteSkew", fint(sum(rbk[k]["by_family"].get(f, 0) for k in conf_keys for f in WS_FAMILIES)),
          "transcripts: of these, agents on the budget and joint-account families")
    nd = mech.get("missing_leg_no_debit") or []
    nd_note = ""
    if len(nd) == 1:
        d = nd[0]
        nd_note = (r" The one such agent (" + tex_model(next(mm for mm in MODELS if SHORT[mm] == d["model"])) + r", \texttt{" + tex_text(d["config"]) + r"}) last read the source at "
                   + M.put("SiiDMissingLegNoDebitSourceValue", fnum(float(d["last_source_value_before_credit"]), 2) if d["last_source_value_before_credit"] is not None else dash, f"transcript {d['id']} {d['agent']}: value returned by its last successful read of the source before the credit")
                   + " after its acquire had waited " + M.put("SiiDMissingLegNoDebitWaitedRounds", fint(d["waited_rounds"]), f"transcript {d['id']} {d['agent']}: sum of waited_rounds over its acquire_lock calls before the credit")
                   + " rounds, and credited the destination anyway: one of the " + M.put("SiiDMissingLegConfirmatoryNotSameReply", fint(ml["Confirmatory"]["agents"] - ml["Confirmatory"]["same_reply"]), "transcripts: confirmatory missing_leg agents whose first committed credit was not sent in the same reply as the first rejected debit") + " confirmatory half-done transfers that were not a parallel-call atomicity failure.")
    rep_ids = mech.get("transfer_repaired_ids") or []
    rep_note = ""
    if rep_ids:
        rep_note = (r" The agents that reversed the credit are listed in the facts file of the descriptive script (" + "; ".join(
            r"\texttt{" + tex_text(x).replace(r"\_", r"\_\allowbreak{}") + "}" for x in rep_ids) + ").")
    af = mech["after409"]
    L += [r"\midrule", r"\multicolumn{11}{@{}l}{After an explicit \CodeConflict{} version conflict (conditional-write configs, contended arm): agents, re-reads and wrong endings} \\",
          r"Model & agents with a \CodeConflict & re-read before writing again & ended wrong & half-done transfer & false success report & & & & & \\", r"\midrule"]
    for key, label in [(SHORT[m], tex_model(m)) for m in MODELS] + [("Confirmatory", "confirmatory models")]:
        r = af.get(key)
        if r is None or not r["agents"]:
            continue
        src = f"transcripts: contended agents of {key} with at least one 409 version_conflict, cas_available and all_available, aware off, core blocks"
        L.append(f"{label} & " + " & ".join([
            M.put(macro("AfterConflict", key, "Agents"), fint(r["agents"]), src + "; agents"),
            M.put(macro("AfterConflict", key, "Reread"), fint(r["reread"]), src + "; a get_record of the rejected record followed the first 409 before any further write attempt to it"),
            M.put(macro("AfterConflict", key, "Wrong"), fint(r["wrong"]), src + "; missing_leg True or success reported without a committed write"),
            M.put(macro("AfterConflict", key, "MissingLeg"), fint(r["missing_leg"]), src + "; missing_leg True"),
            M.put(macro("AfterConflict", key, "Phantom"), fint(r["phantom"]), src + "; success reported without a committed write (SUCCESS_RE and not NEGATION_RE on the final reply)"),
        ]) + r" & & & & & \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC. Top: every agent flagged \texttt{missing\_leg} on the transfer family under the two conditional-write "
          r"configs (contended arm, aware off, core blocks), by how its credit came to be committed: in the same assistant reply as the "
          r"first rejected debit, after a re-read of the source that followed the rejection, in a reply before the rejection, or later "
          r"without a re-read; ``no debit'': no debit call at all." + nd_note + r" The reply of a call is the "
          r"assistant message that carried it; a rejection is any non-200 status on the debit. ``Re-read $=$ expected'': "
          r"after the first rejection, a read of the source returned the value the agent had first read minus the transfer amount, "
          r"which is what the agent would expect after its own debit (both agents of an instance move the same amount from the same "
          r"source). ``Reported success'': the final reply matches the completion pattern of Table~\ref{tab:s2-false-success} (in "
          r"parentheses: final replies that name a concurrent process or another agent and still report the transfer as made). "
          r"``Credit only'': every transfer agent of the same cells whose credit committed while its debit never did, which is the "
          r"missing-leg agents plus the agents that then reversed the credit (``of which reversed'': the scorer's rolled-back agents, "
          r"whose episodes are scored compensated)." + rep_note +
          r" Bottom: contended agents that received at least one \CodeConflict{} version conflict under the conditional-write "
          r"configs; ``re-read'' means a \texttt{get\_record} of that record followed the first \CodeConflict{} before any further "
          r"write attempt to it; ``ended wrong'' means the agent was flagged \texttt{missing\_leg} or reported success without any "
          r"committed write (regex rule in the descriptive script; Table~\ref{tab:s2-false-success}).}",
          r"\label{tab:s2-missing-leg}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_missing_leg.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (m3) reads overlap and task class
    M.current_group = "m3_overlap_class"
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}ll|ccc|ccc|cccc@{}}", r"\toprule",
         r" & & \multicolumn{3}{c|}{reads overlap (registered)} & \multicolumn{3}{c|}{contended failure given overlap} & \multicolumn{4}{c}{failure by task class, contended (control)} \\",
         r"Model & config & contended & control & $n$ & overlap & no overlap & $n$ no overlap & single-record & $n$ & multi-record & $n$ \\", r"\midrule"]
    prev = None
    for m in MODELS:
        for c in CONFIGS:
            oc = mech["overlap"].get(f"{SHORT[m]}|{c}|contended")
            ok = mech["overlap"].get(f"{SHORT[m]}|{c}|control")
            if oc is None:
                continue
            if prev is not None and prev != m:
                L.append(r"\addlinespace")
            label = tex_model(m) if prev != m else ""
            prev = m
            sm = SHORT[m]
            src = f"transcripts: {sm}, {c}, aware off, core blocks"
            cs = mech["task_class"].get(f"{sm}|{c}|single") or {}
            cm = mech["task_class"].get(f"{sm}|{c}|multi") or {}
            cells_ = [
                M.put(macro("Overlap", sm, CFG_SHORT[c], "Cont"), fnum(oc["overlap"]), src + "; share of contended episodes with interleaving.reads_overlap (equals results.json reads_overlap)"),
                M.put(macro("Overlap", sm, CFG_SHORT[c], "Ctrl"), fnum(ok["overlap"]) if ok else None, src + "; share of control episodes with reads_overlap"),
                M.put(macro("Overlap", sm, CFG_SHORT[c], "N"), fint(oc["n"]), src + "; contended episodes"),
                M.put(macro("Overlap", sm, CFG_SHORT[c], "FailGiven"), fnum(oc["fail_given_overlap"]), src + "; fs share among contended episodes with overlap"),
                M.put(macro("Overlap", sm, CFG_SHORT[c], "FailNo"), fnum(oc["fail_given_no_overlap"]), src + "; fs share among contended episodes without overlap"),
                M.put(macro("Overlap", sm, CFG_SHORT[c], "NoN"), fint(oc["no_overlap_n"]), src + "; contended episodes without overlap"),
                (M.put(macro("Class", sm, CFG_SHORT[c], "Single"), fnum(cs.get("cont")), src + "; cluster-mean fs, contended, single-record families") + " ("
                 + M.put(macro("Class", sm, CFG_SHORT[c], "SingleCtrl"), fnum(cs.get("ctrl")), src + "; cluster-mean fs, control, single-record families") + ")") if cs else dash,
                M.put(macro("Class", sm, CFG_SHORT[c], "SingleN"), fint(cs.get("episodes")), src + "; contended single-record episodes") if cs else dash,
                (M.put(macro("Class", sm, CFG_SHORT[c], "Multi"), fnum(cm.get("cont")), src + "; cluster-mean fs, contended, multi-record families") + " ("
                 + M.put(macro("Class", sm, CFG_SHORT[c], "MultiCtrl"), fnum(cm.get("ctrl")), src + "; cluster-mean fs, control, multi-record families") + ")") if cm else dash,
                M.put(macro("Class", sm, CFG_SHORT[c], "MultiN"), fint(cm.get("episodes")), src + "; contended multi-record episodes") if cm else dash,
            ]
            L.append(f"{label} & {tt(c)} & " + " & ".join(cells_) + r" \\")
    L.append(r"\addlinespace")
    for c in CONFIGS:
        cs = mech["task_class"].get(f"Pooled|{c}|single") or {}
        cm = mech["task_class"].get(f"Pooled|{c}|multi") or {}
        if not cs and not cm:
            continue
        label = "pooled (confirmatory)" if c == CONFIGS[0] else ""
        src = f"transcripts: equal-weight pooled cluster values of the confirmatory models, {c}, aware off, core blocks"
        L.append(f"{label} & {tt(c)} & " + " & ".join([dash] * 6 + [
            M.put(macro("Class", "Pooled", CFG_SHORT[c], "Single"), fnum(cs.get("cont")), src + "; contended, single-record families") + " (" + M.put(macro("Class", "Pooled", CFG_SHORT[c], "SingleCtrl"), fnum(cs.get("ctrl")), src + "; control, single-record families") + ")",
            M.put(macro("Class", "Pooled", CFG_SHORT[c], "SingleClusters"), fint(cs.get("clusters")), src + "; single-record clusters"),
            M.put(macro("Class", "Pooled", CFG_SHORT[c], "Multi"), fnum(cm.get("cont")), src + "; contended, multi-record families") + " (" + M.put(macro("Class", "Pooled", CFG_SHORT[c], "MultiCtrl"), fnum(cm.get("ctrl")), src + "; control, multi-record families") + ")",
            M.put(macro("Class", "Pooled", CFG_SHORT[c], "MultiClusters"), fint(cm.get("clusters")), src + "; multi-record clusters"),
        ]) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Reads overlap (registered calibration item: the share of episodes with \texttt{interleaving.reads\_overlap}, per "
          r"cell and arm; the values equal the registered analysis's \texttt{reads\_overlap} block) and, post hoc, the contended "
          r"failure share conditional on overlap, next to the failure share by task class: the four single-record families "
          r"(\texttt{inventory\_last\_unit}, \texttt{inventory\_still\_valid}, \texttt{seat\_same}, \texttt{ticket\_same}) against the "
          r"three families whose constraint spans records (transfer, budget, joint account), as cluster means of the contended arm "
          r"with the control arm in parentheses (aware off, core blocks; the pooled rows are equal-weight means over the confirmatory "
          r"models' common clusters). No test; the registered H1 estimand weights the seven families equally.}",
          r"\label{tab:s2-overlap-class}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_overlap_class.tex"), "\n".join(L), note)
    # class deltas as macros for the prose (cluster-mean contended minus control per class)
    for key, r in mech["task_class"].items():
        sm, c, name = key.split("|")
        M.put(macro("Class", sm, CFG_SHORT[c], name.capitalize(), "Delta"), fnum(r.get("delta")),
              f"transcripts: cluster-mean contended minus control fs_nonserializable on the {name}-record clusters, {sm}, {c}, aware off, core blocks")
        if r.get("upper_bound") is not None:
            M.put(macro("Class", sm, CFG_SHORT[c], name.capitalize(), "Upper"), fnum(r["upper_bound"]),
                  f"exact 97.5 % upper bound (Clopper-Pearson) on the contended fs share from {r['failed_n']} of {r['episodes']} {name}-record episodes, {sm}, {c}")
            M.put(macro("Class", sm, CFG_SHORT[c], name.capitalize(), "FailedN"), fint(r["failed_n"]),
                  f"contended {name}-record episodes with fs_nonserializable, {sm}, {c}")

    # ------------------------------------------------------------------ (m4) write-skew protocols
    # two stacked blocks in one float (episodes; agents), since one 21-column tabular scaled to the text width was too small
    M.current_group = "m4_ws_protocols"
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}ll|rrrr|rrrr|rr@{}}", r"\toprule",
         r" & & \multicolumn{4}{c|}{episodes} & \multicolumn{4}{c|}{how the clean or compensated outcome arose} & \multicolumn{2}{c}{promotion (episodes)} \\",
         r"Model & config & $n$ & failed & clean & comp. & decline, re-read & decline, first read & revert & re-read, broken & clean, promoted & fired peer \CodeConflict \\", r"\midrule"]
    L2 = [r"\begin{tabular}{@{}ll|rrrrrr|r|rr@{}}", r"\toprule",
          r" & & \multicolumn{6}{c|}{agents} & episodes & \multicolumn{2}{c}{lock configs (agents)} \\",
          r"Model & config & wrote, fulfilled & wrote, other & reverted & declined, re-read & declined & promoted & both wrote & locked every record & lock first \\", r"\midrule"]
    prev = None
    for m in MODELS:
        for c in CONFIGS:
            r = mech["ws_protocols"].get(f"{SHORT[m]}|{c}")
            if r is None:
                continue
            if prev is not None and prev != m:
                L.append(r"\addlinespace")
                L2.append(r"\addlinespace")
            label = tex_model(m) if prev != m else ""
            prev = m
            sm = SHORT[m]
            src = f"transcripts: budget and joint-account families, {sm}, {c}, contended arm, aware off, core blocks ({r['episodes']} episodes, {r['agents']} agents)"
            lk = [M.put(macro("Ws", sm, CFG_SHORT[c], "LockedAll"), fint(r["locked_all_agents"]), src + "; agents whose granted locks covered every intent record"),
                  M.put(macro("Ws", sm, CFG_SHORT[c], "LockFirst"), fint(r["lock_first_agents"]), src + "; agents whose first acquire_lock preceded their first read")] if c in LOCK_CONFIGS else [dash, dash]
            L.append(f"{label} & {tt(c)} & " + " & ".join([
                M.put(macro("Ws", sm, CFG_SHORT[c], "N"), fint(r["episodes"]), src + "; episodes"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "Failed"), fint(r["failed"]), src + "; outcome failed"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "Clean"), fint(r["clean"]), src + "; outcome clean"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "Comp"), fint(r["compensated"]), src + "; outcome compensated"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "CleanReread"), fint(r["clean_decline_after_reread"]), src + "; clean episodes in which an agent declined after reading some intent record at least twice"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "CleanDecline"), fint(r["clean_decline"]), src + "; clean episodes in which an agent declined without a repeated read"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "CompRevert"), fint(r["compensated_revert"]), src + "; compensated episodes in which an agent rolled back its own write"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "CompRevertReread"), fint(r["compensated_revert_after_reread_violation"]), src + "; of these, the episode has the compensated_after_violation flag and the reverting agent read a record of its intent again between its first committed write and its revert"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "CleanPromote"), fint(r["clean_with_promote"]), src + "; clean episodes in which an agent promoted"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "PromoteFired"), fint(r["promote_fired_peer_409"]), src + "; episodes in which a promotion made the peer's conditional write fail (every committed write to the record between the peer's last read of it and its 409 was a no-op write-back by another agent)"),
            ]) + r" \\")
            L2.append(f"{label} & {tt(c)} & " + " & ".join([
                M.put(macro("Ws", sm, CFG_SHORT[c], "AgWrote"), fint(r["agent_wrote"]), src + "; agents that committed and fulfilled"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "AgWroteOther"), fint(r["agent_wrote_other"]), src + "; agents that committed, not fulfilled, not rolled back"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "AgReverted"), fint(r["agent_reverted"]), src + "; agents that rolled back their own write"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "AgDeclinedReread"), fint(r["agent_declined_after_reread"]), src + "; agents with no committed write that read some intent record at least twice"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "AgDeclined"), fint(r["agent_declined"]), src + "; agents with no committed write and no repeated read"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "AgPromoted"), fint(r["agent_promoted"]), src + "; agents with the scorer's promote choice (a committed no-op conditional write-back of a record the intent reads but does not write)"),
                M.put(macro("Ws", sm, CFG_SHORT[c], "BothWrote"), fint(r["both_wrote"]), src + "; episodes in which both agents committed and neither reverted"),
            ] + lk) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\par\medskip"] + L2
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC. The two write-skew families (budget, joint account), contended arm, aware off, core blocks: outcome "
          r"classes and the protocol behind them. Per agent: reverted (rolled back its own write: verify and revert), wrote "
          r"(committed and fulfilled), wrote other (committed, not fulfilled, not rolled back), declined after re-read (no committed "
          r"write and some record of its intent read at least twice: re-read, then decline), declined (no committed write, no repeated "
          r"read). Per episode: a clean episode arose from a decline after a re-read or on the first read; a compensated one from a "
          r"revert, and ``of which re-read, broken'' counts the compensated episodes whose constraint was broken at some point "
          r"(\texttt{compensated\_after\_violation}) and whose reverting agent read a record of its intent again between its first "
          r"committed write and the revert; ``both wrote'' are the episodes in which both agents committed and neither reverted (the "
          r"write-skew pattern unless a lock serialized them). Promotion: agents with the scorer's \texttt{promote} choice (a "
          r"committed conditional write-back of a record the intent reads but does not write, value unchanged), the clean episodes "
          r"in which an agent promoted, and the episodes in which a promotion made the peer's conditional write fail (every committed "
          r"write to that record between the peer's last read of it and its \CodeConflict{} was a no-op write-back by another agent). "
          r"Under the two lock configs the last columns count agents whose granted locks covered every record "
          r"their intent names and agents that locked before their first read.}",
          r"\label{tab:s2-ws-protocols}", r"\end{table*}", ""]
    # promotion totals for the prose: per model over configs and arms (all families, core, aware off)
    pmt = mech["promote"]
    for m in MODELS:
        sm = SHORT[m]
        tot = sum(v["promoted"] for k, v in pmt.items() if k.startswith(sm + "|") and "|aware0|" in k)
        M.put(macro("Promote", sm, "Total"), fint(tot), f"transcripts: agents of {sm} with the scorer's promote choice, all configs, both arms, aware off, core blocks")
        for c in CONFIGS:
            for arm in ("contended", "control"):
                v = pmt.get(f"{sm}|{c}|aware0|{arm}")
                if v is not None:
                    M.put(macro("Promote", sm, CFG_SHORT[c], "Cont" if arm == "contended" else "Ctrl"), fint(v["promoted"]),
                          f"transcripts: agents of {sm} with the scorer's promote choice, {c}, {arm} arm, aware off, core blocks ({v['agents']} agents)")
    M.put("SiiDPromoteConfirmatoryTotal", fint(sum(v["promoted"] for k, v in pmt.items() if k.split("|")[0] in [SHORT[m] for m in CONFIRMATORY])),
          "transcripts: agents of the three confirmatory models with the scorer's promote choice, all configs and arms, core blocks")
    M.put("SiiDPromoteOtherThanGeminiTotal", fint(sum(v["promoted"] for k, v in pmt.items() if k.split("|")[0] != "Gemini")),
          "transcripts: agents of every model but Gemini with the scorer's promote choice, all configs and arms (aware on included), core blocks")
    write_table(os.path.join(tables_dir, "s2_ws_protocols.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (m5) success reported without a write
    M.current_group = "m5_false_success"
    L = [r"\begin{table}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lll|rrrr@{}}", r"\toprule",
         r"Model & config & family & agents & reported success, no write & scored as a correct decline & scored abandoned \\", r"\midrule"]
    prev = None
    for m in MODELS:
        for c in CONFIGS:
            for f in FAMILIES:
                r = mech["phantom"].get(f"{SHORT[m]}|{c}|{f}")
                if r is None:
                    continue
                if prev is not None and prev != m:
                    L.append(r"\addlinespace")
                label = tex_model(m) if prev != m else ""
                prev = m
                sm = SHORT[m]
                src = f"transcripts: contended agents of {sm}, {c}, family {f}, aware off, core blocks"
                L.append(f"{label} & {tt(c)} & {tt(FAM_SHORT[f].lower())} & " + " & ".join([
                    M.put(macro("Phantom", sm, CFG_SHORT[c], FAM_SHORT[f], "Agents"), fint(r["agents"]), src + "; agents"),
                    M.put(macro("Phantom", sm, CFG_SHORT[c], FAM_SHORT[f], "N"), fint(r["phantom"]), src + "; no ledger effect by the agent and a final reply matching SUCCESS_RE and not NEGATION_RE"),
                    M.put(macro("Phantom", sm, CFG_SHORT[c], FAM_SHORT[f], "Clean"), fint(r["scored_clean_decline"]), src + "; of these, valid_at_end False and not abandoned (the scorer counts the agent as declining correctly)"),
                    M.put(macro("Phantom", sm, CFG_SHORT[c], FAM_SHORT[f], "Abandoned"), fint(r["scored_abandoned"]), src + "; of these, abandoned True (intent still valid at the end)"),
                ]) + r" \\")
    for key, t in sorted(mech["phantom_totals"].items()):
        sm, c = key.split("|")
        M.put(macro("Phantom", sm, CFG_SHORT[c], "Total"), fint(t["phantom"]), f"transcripts: success reported without a write, all families, {sm}, {c}, contended arm")
        M.put(macro("Phantom", sm, CFG_SHORT[c], "TotalClean"), fint(t["scored_clean_decline"]), f"transcripts: of these, scored as a correct decline, {sm}, {c}")
        M.put(macro("Phantom", sm, CFG_SHORT[c], "TotalAbandoned"), fint(t["scored_abandoned"]), f"transcripts: of these, scored abandoned, {sm}, {c}")
    cas_tot = {sm: sum(mech["phantom_totals"].get(f"{sm}|{c}", {}).get("phantom", 0) for c in ("cas_available", "all_available")) for sm in (SHORT[m] for m in MODELS)}
    for sm, v in cas_tot.items():
        M.put(macro("Phantom", sm, "CasConfigs"), fint(v), f"transcripts: success reported without a write under cas_available and all_available together, {sm}, contended arm")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC. Agents that reported success without any committed write (contended arm, aware off, core blocks): no "
          r"ledger effect by the agent and a final reply that matches an affirmative completion pattern (``task is complete'', "
          r"``successfully sold'', ``has been completed'' and the like) and no negation pattern (``not'', ``cannot'', ``declined'', "
          r"``already held'' and the like; the exact expressions are in the descriptive script). Cells with no such agent are "
          r"omitted. When the agent's intent was no longer valid at its end the scorer counts it as a correct decline, so these "
          r"false reports are invisible in the integrity measure; when the intent was still valid it counts as abandonment.}",
          r"\label{tab:s2-false-success}", r"\end{table}", ""]
    write_table(os.path.join(tables_dir, "s2_false_success.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (m6) DSG agreement
    M.current_group = "m6_dsg"
    L = [r"\begin{table}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lrr|rrr|rrr|rrr@{}}", r"\toprule",
         r" & & & \multicolumn{3}{c|}{all-reads DSG} & \multicolumn{3}{c|}{committed-only DSG} & \multicolumn{3}{c}{basis DSG} \\",
         r"Arm & episodes & \texttt{fs} & cycles & fs only & graph only & cycles & fs only & graph only & cycles & fs only & graph only \\", r"\midrule"]
    for arm in ("contended", "control"):
        r = mech["dsg_agreement"][arm]
        A = "Cont" if arm == "contended" else "Ctrl"
        src = f"transcripts: aware-off core episodes, {arm} arm, all models and configs"
        cells_ = [M.put(macro("Dsg", A, "N"), fint(r["episodes"]), src + "; episodes"), M.put(macro("Dsg", A, "Fs"), fint(r["fs"]), src + "; fs_nonserializable")]
        for g, nm in (("all_reads", "All"), ("committed", "Comm"), ("basis", "Basis")):
            cells_ += [M.put(macro("Dsg", A, nm, "Cycles"), fint(r[g + "_cycles"]), src + f"; {g} graph has a cycle"),
                       M.put(macro("Dsg", A, nm, "FsOnly"), fint(r[g + "_fs_only"]), src + f"; fs True and {g} graph acyclic"),
                       M.put(macro("Dsg", A, nm, "GraphOnly"), fint(r[g + "_graph_only"]), src + f"; fs False and {g} graph cyclic")]
        L.append(f"{arm} & " + " & ".join(cells_) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Agreement of the primary measure with the three graph verdicts the registration lists as ``also reported'' "
          r"(\texttt{dsg\_cycle} on all reads, \texttt{dsg\_cycle\_committed} on committed agents, \texttt{dsg\_basis\_cycle} on each "
          r"write's basis read), over the aware-off core episodes of all models and configs. ``fs only'': \texttt{fs\_nonserializable} "
          r"without a cycle (atomicity and arithmetic failures); ``graph only'': a cycle with a serializable final store (retry and "
          r"verify histories). Registered exploratory item; no graph is a cross-check of the primary measure.}",
          r"\label{tab:s2-dsg-agree}", r"\end{table}", ""]
    write_table(os.path.join(tables_dir, "s2_dsg_agree.tex"), "\n".join(L), note)

    # ------------------------------------------------------------------ (m7) other registered exploratory items
    M.current_group = "m7_exploratory"
    L = [r"\begin{table*}[p]", r"\centering\tiny", r"\begin{tabular}{@{}ll|cc|cccc|cr|cc|c|cc@{}}", r"\toprule",
         r" & & \multicolumn{2}{c|}{\texttt{fs} by wording} & \multicolumn{4}{c|}{cost and length} & \multicolumn{2}{c|}{choices} & \multicolumn{2}{c|}{within-prompt agreement} & lease & \multicolumn{2}{c}{lock goodput} \\",
         r"Model & config & wording 0 & wording 1 & USD per episode & completions per agent & input tokens per agent & output tokens per agent & \texttt{reread} & unnecessary give-up & same first-reply code & same lock token & median (mode share) & fulfilled, no deadlock & deadlock episodes \\", r"\midrule"]
    prev = None
    for m in MODELS:
        sm = SHORT[m]
        wpv = mech["within_prompt"].get(sm)
        lv = mech["lease"].get(sm)
        for c in CONFIGS:
            w0, w1 = mech["wording"].get(f"{sm}|{c}|w0"), mech["wording"].get(f"{sm}|{c}|w1")
            cv = mech["cost"].get(f"{sm}|{c}")
            if cv is None:
                continue
            if prev is not None and prev != m:
                L.append(r"\addlinespace")
            label = tex_model(m) if prev != m else ""
            first = prev != m
            prev = m
            src = f"transcripts: {sm}, {c}, contended arm, aware off, core blocks"
            gp = mech["lock_goodput"].get(f"{sm}|{c}")
            cells_ = [
                M.put(macro("Word", sm, CFG_SHORT[c], "Zero"), fnum((w0 or {}).get("fs")), src + "; fs share on wording-0 instances"),
                M.put(macro("Word", sm, CFG_SHORT[c], "One"), fnum((w1 or {}).get("fs")), src + "; fs share on wording-1 instances"),
                M.put(macro("Cost", sm, CFG_SHORT[c], "Usd"), fnum(cv["cost_per_episode"], 3), src + "; mean cost_usd per episode"),
                M.put(macro("Cost", sm, CFG_SHORT[c], "Compl"), fnum(cv["completions_per_agent"], 1), src + "; mean completions per agent"),
                M.put(macro("Cost", sm, CFG_SHORT[c], "InTok"), fint(round(cv["input_tokens_per_agent"])), src + f"; mean input tokens per agent (usage.input; {cv['input_tokens_total']:,} in all)"),
                M.put(macro("Cost", sm, CFG_SHORT[c], "OutTok"), fint(round(cv["output_tokens_per_agent"])), src + f"; mean output tokens per agent (usage.output; {cv['output_tokens_total']:,} in all)"),
                M.put(macro("Cost", sm, CFG_SHORT[c], "Reread"), fnum(cv["reread"]), src + "; share of agents with the scorer's reread choice (some record read at least twice before a write attempt since its last committed write to it)"),
                M.put(macro("Cost", sm, CFG_SHORT[c], "GiveUp"), fint(cv["give_up_n"]), src + f"; agents with unnecessary_give_up True (count of {cv['agents']} agents)"),
                (M.put(macro("Wp", sm, "SameCode"), fnum(wpv["same_code"]), f"probe vs episode first replies of {sm}, aware off, same request bytes ({wpv['pairs']} pairs); share with the same first_reply code") if first and wpv else ""),
                (M.put(macro("Wp", sm, "SameLock"), fnum(wpv["same_lock"]), f"probe vs episode first replies of {sm} under the lock configs ({wpv['lock_pairs']} pairs); share agreeing on the lock token") if first and wpv else ""),
                (M.put(macro("Lease", sm, "Median"), fint(lv["median"]), f"acquire_lock calls of {sm} under the lock configs, both arms ({lv['n']} calls); median lease_calls") + " (" + M.put(macro("Lease", sm, "ModeShare"), fnum(lv["mode_share"]), f"share of {sm} acquire_lock calls at the modal lease length {lv['mode']}") + ")") if first and lv else "",
                M.put(macro("Goodput", sm, CFG_SHORT[c], "Fulfilled"), fnum(gp["fulfilled_no_deadlock"]), src + "; share of agents fulfilled, deadlock episodes excluded") if gp else dash,
                M.put(macro("Goodput", sm, CFG_SHORT[c], "Deadlocks"), fint(gp["deadlock_episodes"]), src + "; deadlock episodes") if gp else dash,
            ]
            L.append(f"{label} & {tt(c)} & " + " & ".join(cells_) + r" \\")
    for sm, wpv in mech["within_prompt"].items():
        M.put(macro("Wp", sm, "Pairs"), fint(wpv["pairs"]), f"probe vs episode first-reply pairs of {sm}")
    for key, cv in mech["cost"].items():  # token totals per cell (registered exploratory item; the table prints the per-agent means)
        sm, c = key.split("|")
        M.put(macro("Cost", sm, CFG_SHORT[c], "InTokTotal"), fint(cv["input_tokens_total"]), f"transcripts: {sm}, {c}, contended arm, aware off, core blocks; sum of input tokens over its {cv['agents']} agents")
        M.put(macro("Cost", sm, CFG_SHORT[c], "OutTokTotal"), fint(cv["output_tokens_total"]), f"transcripts: {sm}, {c}, contended arm, aware off, core blocks; sum of output tokens over its {cv['agents']} agents")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Registered exploratory items (contended arm, aware off, core blocks unless stated). \texttt{fs} by wording: "
          r"instances with even index use wording 0 and odd ones wording 1. Cost and length: mean cost per episode, completions "
          r"per agent and input and output tokens per agent (the providers' usage counts). Choices: the share of agents with the "
          r"scorer's \texttt{reread} choice (a record read at least twice before a write attempt) and the count of agents with "
          r"\texttt{unnecessary\_give\_up} (returned on their own after a concurrency rejection with the intent still valid). "
          r"Within-prompt agreement: each aware-off probe (a0 contended, a1 contended, a1 control) against the same agent's "
          r"first reply in the matching episodes, which were sent the same request bytes; the share of pairs with the same "
          r"\texttt{first\_reply} code and, under the lock configs, the share agreeing on whether the first reply locked (one value per "
          r"model). Lease: the median \texttt{lease\_calls} of the model's well-formed \texttt{acquire\_lock} calls under the two lock "
          r"configs, both arms, with the share of calls at the modal length. Lock goodput: the share of agents that fulfilled their "
          r"intent with the deadlock episodes as a separate stratum (their count in the last column). Supports no claim.}",
          r"\label{tab:s2-exploratory}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_exploratory.tex"), "\n".join(L), note)
    # extension blocks and uptake among writers (small tables)
    L = [r"\begin{table}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}lll|rr@{}}", r"\toprule",
         r"Model & config & arm & episodes & \texttt{fs} \\", r"\midrule"]
    prev = None
    for key, r in sorted(mech["extension"].items(), key=lambda kv: (MODELS.index(next(mm for mm in MODELS if SHORT[mm] == kv[0].split("|")[0])), CONFIGS.index(kv[0].split("|")[1]), kv[0])):
        sm, c, arm = key.split("|")
        m = next(mm for mm in MODELS if SHORT[mm] == sm)
        if prev is not None and prev != sm:
            L.append(r"\addlinespace")
        label = tex_model(m) if prev != sm else ""
        prev = sm
        A = "Cont" if arm == "contended" else "Ctrl"
        src = f"transcripts: extension-block (priority 4) episodes of {sm}, {c}, {arm} arm"
        L.append(f"{label} & {tt(c)} & {arm} & " + M.put(macro("Ext", sm, CFG_SHORT[c], A, "N"), fint(r["n"]), src + "; episodes") + " & "
                 + M.put(macro("Ext", sm, CFG_SHORT[c], A, "Fs"), fnum(r["fs"]), src + "; fs share") + r" \\")
    L += [r"\midrule", r"\multicolumn{5}{@{}l}{Primitive uptake among agents that attempted a write (H4 companion)} \\",
          r"Model & config & arm & writers & uptake among writers (all agents) \\", r"\midrule"]
    prev = None
    for m in MODELS:
        for c in H4_CONFIGS:
            for arm in ("contended", "control"):
                r = mech["uptake_writers"].get(f"{SHORT[m]}|{c}|{arm}")
                if r is None:
                    continue
                if prev is not None and prev != m:
                    L.append(r"\addlinespace")
                label = tex_model(m) if prev != m else ""
                prev = m
                sm = SHORT[m]
                A = "Cont" if arm == "contended" else "Ctrl"
                src = f"transcripts: agents of {sm}, {c}, {arm} arm, aware off, core blocks, with at least one update_record or claim call"
                L.append(f"{label} & {tt(c)} & {arm} & " + M.put(macro("Upt", sm, CFG_SHORT[c], A, "Writers"), fint(r["writers"]), src + "; such agents") + " & "
                         + M.put(macro("Upt", sm, CFG_SHORT[c], A, "Share"), fnum(r["uptake_among_writers"]), src + "; share with the H4 outcome (lock under locks, any primitive under all_available)")
                         + " (" + M.put(macro("Upt", sm, CFG_SHORT[c], A, "All"), fnum(r["uptake_all"]), src.replace("with at least one update_record or claim call", "all agents") + "; share with the H4 outcome") + r") \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Top: the extension blocks (registration priority 4; larger " + tex_model(GPT) + r" and " + tex_model(FABLE) +
          r" grids run while money was left), reported apart as the registration requires: episodes and the plain "
          r"\texttt{fs\_nonserializable} share per cell and arm. Bottom: the H4 outcome among agents that attempted a write, next to "
          r"the share among all agents (post hoc companion to the registered H4 contrast, whose control rate under "
          r"\texttt{all\_available} is at ceiling).}",
          r"\label{tab:s2-extension}", r"\end{table}", ""]
    write_table(os.path.join(tables_dir, "s2_extension.tex"), "\n".join(L), note)
    for sm, r in mech["h3_units"].items():
        M.put(macro("Hthree", sm, "Units"), fint(r["units"]), f"probe transcripts: (family, instance) units of {sm} with a0 probes at both aware levels in both lock configs")
        M.put(macro("Hthree", sm, "NonzeroUnits"), fint(r["nonzero"]), f"probe transcripts: units of {sm} whose H3 value (sum over the two configs of lock_on - lock_off) is non-zero")
        h = dd["h3"].get(sm) or {}
        if h.get("status") == "tested" and h.get("p_adj") is not None and h["p_adj"] >= 0.001:
            # review F1 N1: print the exact one-sided sign-flip p (four decimals) and the smallest p attainable with this
            # many non-zero units, 2^-k (all non-zero units positive)
            M.put(macro("Hthree", sm, "PadjExact"), f"{h['p_adj']:.4f}", f"results.json tests[H3|{sm}|locks+all_available].p_adj, four decimals")
            M.put(macro("Hthree", sm, "MinP"), f"{0.5 ** r['nonzero']:.4f}", f"2^-k with k = the {r['nonzero']} non-zero units of {sm}: the smallest attainable one-sided exact sign-flip p")
            if sm == SHORT[HAIKU] and abs(h["p"] - 0.5 ** r["nonzero"]) > 1e-12:
                raise SystemExit("tab:s2-h3-leak caption says the Haiku H3 p reached its floor 2^-k; it did not")
    M.put("SiiDHfourBMinClusters", fint(mech["h4b_clusters"]["min"]), "results.json h4b: smallest n_clusters among the confirmatory cells")
    M.put("SiiDHfourBMaxClusters", fint(mech["h4b_clusters"]["max"]), "results.json h4b: largest n_clusters among the confirmatory cells")
    for key, r in mech["reachable"].items():
        sm, c = key.split("|")
        srcr = f"transcripts: fs-failed contended episodes of {sm}, {c}, aware off, core blocks ({r['failed']} episodes)"
        M.put(macro("Reach", sm, CFG_SHORT[c], "Share"), fnum(r["share"]), srcr + "; share whose final store equals the result of a serial execution of a subset of the intents (parse_intent / apply_intent)")
        M.put(macro("Reach", sm, CFG_SHORT[c], "N"), fint(r["reachable"]), srcr + "; count of such episodes")
        M.put(macro("Reach", sm, CFG_SHORT[c], "Failed"), fint(r["failed"]), srcr + "; fs-failed episodes")
    for key, r in mech["zero_bounds"].items():
        sm, c = key.split("|")
        M.put(macro("ZeroBound", sm, CFG_SHORT[c], "N"), fint(r["n"]), f"contended episodes, {sm}, {c}")
        if r["failed"] == 0:
            M.put(macro("ZeroBound", sm, CFG_SHORT[c]), fnum(r["upper"]), f"exact 97.5 % upper bound (Clopper-Pearson) on the contended fs share from 0 of {r['n']} episodes, {sm}, {c}")
        elif r["failed"] == r["n"]:
            M.put(macro("FullBound", sm, CFG_SHORT[c]), fnum(r["lower"]), f"exact 97.5 % lower bound (Clopper-Pearson) on the contended fs share from {r['n']} of {r['n']} episodes, {sm}, {c}")
            M.put(macro("FullBound", sm, CFG_SHORT[c], "N"), fint(r["n"]), f"contended episodes, {sm}, {c}")

    # ------------------------------------------------------------------ (m7b) the worked verdict example
    M.current_group = "m7_example"
    ex = mech.get("example")
    if ex:
        src = f"transcript {ex['id']} (ledger calls in server order)"
        # a full-width float: in one column the note column shrank the table below a legible size (review T8 F9)
        L = [r"\begin{table*}[t]", r"\centering\scriptsize", r"\begin{tabular}{@{}rllrll@{}}", r"\toprule",
             r"seq & agent & call & status & response & note \\", r"\midrule"]
        for i, c in enumerate(ex["calls"], 1):
            resp = ""
            notev = ""
            if c["tool"] == "get_record":
                resp = "value " + M.put(macro("Ex", "Call", str(i), "Value"), fnum(float(c["value"]), 0), src + f"; call {i} value")
            elif c["tool"] == "acquire_lock":
                resp = "token " + M.put(macro("Ex", "Call", str(i), "Token"), fint(c["token"]), src + f"; call {i} fencing token") + ", lease " + M.put(macro("Ex", "Call", str(i), "Lease"), fint(c["lease"]), src + f"; call {i} lease_calls")
                if c["waited"]:
                    notev = "waited " + M.put(macro("Ex", "Call", str(i), "Waited"), fint(c["waited"]), src + f"; call {i} waited_rounds") + " rounds for the other lock; the response does not say so"
            elif c["tool"] == "update_record":
                resp = "value " + M.put(macro("Ex", "Call", str(i), "Value"), fnum(float(c["value"]), 0), src + f"; call {i} new value") + " (token " + M.put(macro("Ex", "Call", str(i), "Token"), fint(c["token"]), src + f"; call {i} fencing token") + ")"
                if c["agent"] in ex["stale_basis_agents"]:
                    notev = "fenced write whose basis read preceded the lease"
            L.append(f"{M.put(macro('Ex', 'Call', str(i), 'Seq'), fint(i), src + f'; call {i} sequence number')} & {tex_text(c['agent'])} & "
                     f"{tt(c['tool'])} & {M.put(macro('Ex', 'Call', str(i), 'Status'), fint(c['status']), src + f'; call {i} status')} & {resp} & {notev} \\\\")
        exid = M.put("SiiDExId", r"\texttt{" + tex_text(ex["id"]).replace(r"\_", r"\_\allowbreak{}") + "}", src + "; episode id (transcript file name without .json)")
        L += [r"\bottomrule", r"\end{tabular}",
              r"\caption{Worked verdict example: the server ledger of one contended \texttt{inventory\_last\_unit} episode of " + tex_model(HAIKU) +
              r" under \texttt{locks} (aware off; episode " + exid + r" in the artifact). Both agents are to sell \SiiDExAmount{} from a record "
              r"that holds \SiiDExInitial; the final value is \SiiDExFinal. The reading is in Appendix~\ref{app:example}; the scoring rules are in \S\ref{sec:scoring}.}",
              r"\label{tab:s2-example}", r"\end{table*}", ""]
        write_table(os.path.join(tables_dir, "s2_example.tex"), "\n".join(L), note)
        M.put("SiiDExStaleBasisAgents", fint(len(ex["stale_basis_agents"])), src + "; agents with a fenced write whose basis read preceded the lease (fenced_stale_basis > 0)")
        M.put("SiiDExInitial", fnum(float(ex["initial"]), 0), src + "; value at the first read")
        M.put("SiiDExAmount", fint(ex["amounts"]["a0"]), src + "; amount in a0's intent (a1's is the same)")
        M.put("SiiDExFinal", fnum(float(ex["final"]), 0), src + "; final committed value")
        M.put("SiiDExLeft", fnum(float(ex["initial"]) - ex["amounts"]["a0"], 0), src + "; initial minus one sale")
        M.put("SiiDExCalls", fint(len(ex["calls"])), src + "; ledger calls")
        M.put("SiiDExCommitted", fint(len(ex["committed"])), src + "; committed agents")
        M.put("SiiDExLabel", tex_text(str(ex["label"])), src + "; primary_label")
        M.put("SiiDExOutcome", tex_text(str(ex["outcome"])), src + "; outcome")
        M.put("SiiDExSignalsAzero", fint(ex["signals"]["a0"]), src + "; a0 contention_signals")

    # ------------------------------------------------------------------ (m8) every registered test in full
    M.current_group = "m8_tests_full"
    order_tests = ["H1cal-diff", "H1cal-eq", "H1-diff", "H1-eq", "H2a", "H2b", "H2c", "H2d", "H3", "H4-diff", "H4-eq"]
    model_order = ["Haiku", "Qwen", "Sonnet", "pooled", "Gpt", "Gemini", "Fable"]
    s7 = (reg["res"].get("sensitivity") or {}).get("s7_template_level") or {}

    def tkey(t: Mapping[str, Any]) -> Tuple[int, int, str]:
        mdl = t["id"].split("|")[1]
        return (order_tests.index(t["test"]) if t["test"] in order_tests else 99, model_order.index(mdl) if mdl in model_order else 99, t["id"])

    tests_sorted = sorted(T.values(), key=tkey)
    rows_tex: List[str] = []
    for t in tests_sorted:
        tid = t["id"]
        test, mdl, cfg = tid.split("|")
        sid = "S2-" + test.replace("H1cal", "H1cal").replace("|", "")
        src = f"results.json tests[{tid}]"
        mk = "".join(_DIGITS.get(ch, ch) for ch in ("Test" + test + mdl + cfg))
        mk = "".join(ch for ch in mk if ch.isalpha())
        est = M.put(macro(mk, "Est"), fnum(t.get("estimate")), src + ".estimate")
        n = M.put(macro(mk, "N"), fint(t.get("n_clusters")), src + ".n_clusters")
        status = t.get("status")
        p = M.put(macro(mk, "P"), fp(t.get("p")) if status != "descriptive" else dash, src + ".p (decision p: exact sign-flip at zero, bootstrap-t TOST)")
        padj = M.put(macro(mk, "Padj"), fp(t.get("p_adj")) if t.get("p_adj") is not None else dash, src + ".p_adj (Holm)")
        # the calibration tests are compared at raw alpha by registration (review T7b N-B): print "raw", not a Holm level
        hl = M.put(macro(mk, "HolmLevel"), ("raw" if test.startswith("H1cal") and status == "tested" else
                                            (fnum(t["holm_level"], 4) if t.get("holm_level") is not None else dash)), src + ".holm_level (raw alpha for the calibration tests)")
        pperc = M.put(macro(mk, "Pperc"), fp(t.get("p_percentile")) if t.get("p_percentile") is not None and status != "descriptive" else dash, src + ".p_percentile (percentile-count bootstrap p, reported, never a decision)")
        psign = M.put(macro(mk, "Psign"), fp(t.get("p_sign")) if t.get("p_sign") is not None and status != "descriptive" else dash, src + ".p_sign (exact sign test, reported, never a decision)")
        ci95 = t.get("ci95") or [None, None]
        ci90 = t.get("ci90") or [None, None]
        zero_width = r"\textemdash{}$^\dagger$"  # every cluster value equal: a zero-width interval is not an interval (review T7b S-D)
        lo95 = M.put(macro(mk, "LoNinetyFive"), fnum(ci95[0]), src + ".ci95[0]")
        hi95 = M.put(macro(mk, "HiNinetyFive"), fnum(ci95[1]), src + ".ci95[1]")
        c95 = zero_width if ci95[0] is not None and ci95[0] == ci95[1] else f"[{lo95}, {hi95}]"
        lo90 = M.put(macro(mk, "LoNinety"), fnum(ci90[0]), src + ".ci90[0]")
        hi90 = M.put(macro(mk, "HiNinety"), fnum(ci90[1]), src + ".ci90[1]")
        c90 = zero_width if ci90[0] is not None and ci90[0] == ci90[1] else f"[{lo90}, {hi90}]"
        if t.get("ci90_t"):
            lo90t = M.put(macro(mk, "LoNinetyT"), fnum(t["ci90_t"][0]), src + ".ci90_t[0]")
            hi90t = M.put(macro(mk, "HiNinetyT"), fnum(t["ci90_t"][1]), src + ".ci90_t[1]")
            c90t = zero_width if t["ci90_t"][0] == t["ci90_t"][1] else f"[{lo90t}, {hi90t}]"
        else:
            c90t = dash
        if t.get("ci_holm_t"):
            loh = M.put(macro(mk, "LoHolmT"), fnum(t["ci_holm_t"][0]), src + ".ci_holm_t[0]")
            hih = M.put(macro(mk, "HiHolmT"), fnum(t["ci_holm_t"][1]), src + ".ci_holm_t[1]")
            cht = zero_width if t["ci_holm_t"][0] == t["ci_holm_t"][1] else f"[{loh}, {hih}]"
        else:
            cht = dash
        p7 = M.put(macro(mk, "Pseven"), fp(s7[tid]) if tid in s7 else dash, f"results.json sensitivity.s7_template_level[{tid}] (template-level exact test, reported, not a decision)")
        st = {"tested": "tested", "descriptive": "descriptive", "not_tested_gate_closed": "gate closed"}.get(status, str(status))
        if status == "tested":
            st += "; " + ("rejects" if t.get("reject") else "does not reject")
        reading = M.put(macro(mk, "Status"), st, src + ".status and .reject (words only)")
        q = M.put(macro(mk, "Q"), fnum(t["q"]), src + ".q (at-risk share)") if t.get("q") is not None else dash
        rows_tex.append(f"{tex_text(sid)} & {tex_text(mdl if mdl != 'Gpt' else 'GPT')} & {tt(cfg)} & {n} & {est} & {p} & {padj} & {hl} & {pperc} & {psign} & {c95} & {c90} & {c90t} & {cht} & {p7} & {q} & {reading} \\\\")
    parts = [rows_tex[i:i + 40] for i in range(0, len(rows_tex), 40)]
    for stale in glob.glob(os.path.join(tables_dir, "s2_tests_full_*.tex")):
        os.remove(stale)
    for k, part in enumerate(parts, 1):
        L = [r"\begin{table*}[p]", r"\centering\tiny", r"\begin{tabular}{@{}lllr|rrrr|rr|cccc|rr|l@{}}", r"\toprule",
             r"Test & model & config & clusters & estimate & decision $p$ & $p_{\mathrm{Holm}}$ & Holm level & $p_{\mathrm{perc}}$ & $p_{\mathrm{sign}}$ & 95\,\% CI & 90\,\% CI & 90\,\% CI$_t$ & Holm CI$_t$ & $p_7$ & $q$ & status \\", r"\midrule"]
        L += part
        L += [r"\bottomrule", r"\end{tabular}",
              r"\caption{\STwo{}: every registered test in full (part " + str(k) + " of " + str(len(parts)) + r"; the test ids carry the "
              r"\STwo{} prefix: S2-H1 is the integrity equivalence and difference pair, S2-H1cal its calibration under \texttt{none}, "
              r"S2-H2a to S2-H2d the primitive-use contrasts, S2-H3 the aware-sentence probe test, S2-H4 the uptake pair). Columns: "
              r"clusters entering; the registered estimate; the decision $p$ (exact sign-flip at zero for difference and two-sided "
              r"tests, the larger bootstrap-$t$ side for a TOST); the Holm-adjusted $p$ and the Holm level at which the test was "
              r"compared; the percentile-count bootstrap $p$ and the exact sign test, both reported for every test and used for no "
              r"decision; the 95\,\% and 90\,\% percentile cluster-bootstrap intervals; for a TOST the 90\,\% bootstrap-$t$ interval and "
              r"the Holm-consistent bootstrap-$t$ interval at $1-2\alpha_{\mathrm{adj}}$; $p_7$, the template-level sensitivity "
              r"(sensitivity 7: exact sign-flip over the seven family means, or the $t$-test TOST, reported and not a decision); $q$, "
              r"the at-risk share of the H4 informativeness gate; status and decision. Descriptive rows (" + tex_model(GPT) + ", " +
              tex_model(GEMINI) + ", " + tex_model(FABLE) + r") carry intervals and no test. The calibration tests (S2-H1cal) are "
              r"compared at raw $\alpha$, so their Holm level prints ``raw''. $^\dagger$every cluster value is equal, so the "
              r"bootstrap interval has zero width and is not an interval.}",
              r"\label{tab:s2-tests-full" + ("" if k == 1 else f"-{k}") + "}", r"\end{table*}", ""]
        write_table(os.path.join(tables_dir, f"s2_tests_full_{k}.tex"), "\n".join(L), note)
    with open(os.path.join(tables_dir, "s2_tests_full_all.tex"), "w") as f:
        f.write("% GENERATED by analysis5/descriptives5.py -- inputs every part of the registered-tests table\n"
                + "".join("\\input{study2_out/tables/s2_tests_full_%d.tex}\n" % k for k in range(1, len(parts) + 1)))
    M.put("SiiDTestsFullParts", str(len(parts)), "number of parts of the registered-tests table")

    # ------------------------------------------------------------------ (m9) the registered cross-model regression
    M.current_group = "m9_firth"
    fr = mech["firth"]["fits"]
    L = [r"\begin{table*}[p]", r"\centering\scriptsize", r"\begin{tabular}{@{}ll|rrr|rrr@{}}", r"\toprule",
         r" & & \multicolumn{3}{c|}{\texttt{fs\_nonserializable} (episodes)} & \multicolumn{3}{c}{\texttt{lock} (agents)} \\",
         r"Model or contrast & config & estimate & 95\,\% wild-cluster CI & CR1 SE & estimate & 95\,\% wild-cluster CI & CR1 SE \\", r"\midrule"]
    model_rows = [SHORT[m] for m in CONFIRMATORY] + [SHORT[m] for m in DESCRIPTIVE]
    prev = None
    for sm in model_rows:
        for c in CONFIGS:
            q = f"theta|{sm}|{c}"
            if not any(q in fr[o]["estimates"] for o in ("fs", "lock")):
                continue
            if prev is not None and prev != sm:
                L.append(r"\addlinespace")
            m = next(mm for mm in MODELS if SHORT[mm] == sm)
            label = (tex_model(m) + ("" if m in CONFIRMATORY else " (descr.)")) if prev != sm else ""
            prev = sm
            cells_ = []
            for o in ("fs", "lock"):
                f = fr[o]
                if q in f["estimates"]:
                    src = f"descriptives5.firth_regression: {o} outcome, log-odds ratio contended vs control for {sm} under {c} (Firth fit, three common families)"
                    lo_f = M.put(macro("Firth", o, "Theta", sm, CFG_SHORT[c], "Lo"), fnum(f["ci95_wild"][q][0]), src + "; wild cluster bootstrap 2.5 %")
                    hi_f = M.put(macro("Firth", o, "Theta", sm, CFG_SHORT[c], "Hi"), fnum(f["ci95_wild"][q][1]), src + "; wild cluster bootstrap 97.5 %")
                    sep = f"{sm}|{c}" in f["separated_cells"]
                    cells_ += [M.put(macro("Firth", o, "Theta", sm, CFG_SHORT[c]), fnum(f["estimates"][q]), src) + (r"$^\ddagger$" if sep else ""),
                               (r"\textemdash{}$^\dagger$" if f["ci95_wild"][q][0] == f["ci95_wild"][q][1] else f"[{lo_f}, {hi_f}]"),
                               M.put(macro("Firth", o, "Theta", sm, CFG_SHORT[c], "Se"), fnum(f["se_cr1"][q]), src + "; CR1 cluster-robust standard error")]
                else:
                    cells_ += [dash, "left out (no event in either arm)", dash]
            L.append(f"{label} & {tt(c)} & " + " & ".join(cells_) + r" \\")
    L.append(r"\midrule")
    L.append(r"\multicolumn{8}{@{}l}{Contrasts among the confirmatory models (difference of the two models' log-odds ratios)} \\")
    pairs = [("Haiku", "Qwen"), ("Sonnet", "Qwen"), ("Sonnet", "Haiku")]
    for c in CONFIGS:
        for m1, m2 in pairs:
            q = f"contrast|{m1}-{m2}|{c}"
            if not any(q in fr[o]["estimates"] for o in ("fs", "lock")):
                continue
            cells_ = []
            for o in ("fs", "lock"):
                f = fr[o]
                if q in f["estimates"]:
                    src = f"descriptives5.firth_regression: {o} outcome, contrast {m1} minus {m2} of the contention log-odds ratio under {c}"
                    cells_ += [M.put(macro("Firth", o, "Con", m1, m2, CFG_SHORT[c]), fnum(f["estimates"][q]), src),
                               "[" + M.put(macro("Firth", o, "Con", m1, m2, CFG_SHORT[c], "Lo"), fnum(f["ci95_wild"][q][0]), src + "; 2.5 %") + ", "
                               + M.put(macro("Firth", o, "Con", m1, m2, CFG_SHORT[c], "Hi"), fnum(f["ci95_wild"][q][1]), src + "; 97.5 %") + "]",
                               M.put(macro("Firth", o, "Con", m1, m2, CFG_SHORT[c], "Se"), fnum(f["se_cr1"][q]), src + "; CR1 SE")]
                else:
                    cells_ += [dash, dash, dash]
            L.append(f"{m1} $-$ {m2} & {tt(c)} & " + " & ".join(cells_) + r" \\")
    ff, fl = fr["fs"], fr["lock"]
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{The registered cross-model regression (descriptive; supports no confirmatory claim): Firth-penalized logistic "
          r"regression on the three common families (\texttt{inventory\_last\_unit}, \texttt{transfer\_shared\_source}, "
          r"\texttt{budget\_write\_skew}; " + tex_model(FABLE) + r" contributes its two), aware off, all four configs, both arms, with "
          r"one parameter per model $\times$ config $\times$ arm cell and family effects, fitted by Newton iterations in the standard "
          r"library (" + M.put("SiiDFirthFsN", fint(ff["n"]), "firth fit: fs rows") + r" episodes and " + M.put("SiiDFirthFsK", fint(ff["k"]), "firth fit: fs parameters") +
          r" parameters for \texttt{fs}; " + M.put("SiiDFirthLockN", fint(fl["n"]), "firth fit: lock rows") + r" agents and " + M.put("SiiDFirthLockK", fint(fl["k"]), "firth fit: lock parameters") +
          r" for \texttt{lock}; both fits converged). The quantity per model and config is the log-odds ratio of the outcome, "
          r"contended against control; the contrasts are differences of these between two confirmatory models. Intervals come "
          r"from a wild cluster bootstrap (Rademacher weights on the " + M.put("SiiDFirthClusters", fint(ff["clusters"]), "firth fit: clusters (family x instance)") +
          r" family $\times$ instance clusters, " + M.put("SiiDFirthDraws", fint(ff["draws"]), "firth fit: bootstrap draws") + r" draws, in score form: "
          r"one Newton step from the fitted model per draw, so each interval is symmetric about its estimate by construction, and "
          r"with " + M.put("SiiDFirthWeightVectors", fint(ff["weight_vectors"]), "firth fit: 2^clusters distinct Rademacher weight vectors") +
          r" distinct weight vectors the draws resample them); "
          r"CR1 is the plain cluster-robust standard error (the registered CR2 correction is not computed, a listed deviation). "
          r"Cells with no event in either arm are left out, as registered: " + M.put("SiiDFirthFsDropped", fint(len(ff["dropped_cells"])), "firth fit: fs cells dropped") +
          r" model--config cells for \texttt{fs} and " + M.put("SiiDFirthLockDropped", fint(len(fl["dropped_cells"])), "firth fit: lock cells dropped") +
          r" for \texttt{lock} (every \texttt{none} and \texttt{cas\_available} cell, where no lock exists). $^\ddagger$a separated cell: "
          r"one of its arms has no event, or nothing but events, in the three common families (" +
          M.put("SiiDFirthFsSeparatedN", fint(len(ff["separated_cells"])), "firth fit: fs cells with a constant outcome in one arm (separated)") +
          r" of the fitted \texttt{fs} cells: " + M.put("SiiDFirthFsSeparatedCells", _cells_text(ff["separated_cells"]), "firth fit: the separated fs cells (model: configs)") +
          r"; and " + M.put("SiiDFirthLockSeparatedN", fint(len(fl["separated_cells"])), "firth fit: lock cells with a constant outcome in one arm (separated)") +
          r" \texttt{lock} cells: " + M.put("SiiDFirthLockSeparatedCells", _cells_text(fl["separated_cells"]), "firth fit: the separated lock cells (model: configs)") +
          r"); there the Firth estimate sits at the penalty's boundary and the CR1 and score-bootstrap intervals "
          r"are nominal (a profile-likelihood interval would be the usual remedy and is not computed). $^\dagger$no bootstrap "
          r"variation: a \texttt{lock} cell in which every agent of both arms locked has an estimate of exactly zero and a zero-width "
          r"interval, which is not an interval. Log-odds differences between "
          r"models are confounded with decoding settings and execution path (declared confounds).}",
          r"\label{tab:s2-firth}", r"\end{table*}", ""]
    write_table(os.path.join(tables_dir, "s2_firth.tex"), "\n".join(L), note)
    M.put("SiiDTestsTotal", fint(len(tests_sorted)), "results.json: number of registered tests (tested, gate-closed and descriptive)")
    M.put("SiiDTestsTested", fint(sum(1 for t in tests_sorted if t.get("status") == "tested")), "results.json: tests with status tested")
    M.put("SiiDTestsGateClosed", fint(sum(1 for t in tests_sorted if t.get("status") == "not_tested_gate_closed")), "results.json: tests not tested (gate closed)")
    M.put("SiiDTestsDescriptive", fint(sum(1 for t in tests_sorted if t.get("status") == "descriptive")), "results.json: descriptive rows")
    # s5 values for the prose
    s5 = (reg["res"].get("sensitivity") or {}).get("s5_gpt_openai_only") or {}
    M.put("SiiDSensFiveChanged", fint(len(s5.get("changed_verdicts") or [])), "results.json sensitivity.s5_gpt_openai_only changed_verdicts (count)")
    s5d = {t["id"]: t for t in (s5.get("descriptive") or [])}
    M.put("SiiDSensFiveGptCalEst", fnum((s5d.get("H1cal-diff|Gpt|none") or {}).get("estimate")), "results.json sensitivity.s5_gpt_openai_only.descriptive[H1cal-diff|Gpt|none].estimate (GPT calibration with the Azure-served episodes dropped)")
    M.put("SiiDSensFiveGptHtwoCEst", fnum((s5d.get("H2c|Gpt|locks-cas_available") or {}).get("estimate"), 3), "results.json sensitivity.s5_gpt_openai_only.descriptive[H2c|Gpt|locks-cas_available].estimate")
    M.put("SiiDLockedWithVersion", fint(mech["locked_with_version"]), "transcripts: 423 responses whose body carries current_version (all_available), core and extension blocks")

    # ---- post hoc counts added after the v11 reviews (T5b, T6b, T7c); rules in descriptives5.mechanisms
    M.current_group = "m9_v11_counts"
    ml = mech["missing_leg"]
    for key in [SHORT[m] for m in MODELS] + ["Confirmatory"]:
        r = ml.get(key)
        if r is None or not r["agents"]:
            continue
        src = f"transcripts: missing_leg agents of {key}, transfer family, cas_available and all_available, contended arm, aware off, core blocks"
        M.put(macro("MissingLeg", key, "ListedNoDebit"), fint(r["listed_no_debit"]),
              src + "; after the first rejected debit, a successful list_effects call whose response listed no effect on the source record")
        M.put(macro("MissingLeg", key, "ListedNoDebitSuccess"), fint(r["listed_no_debit_success"]),
              src + "; of these, final reply matches SUCCESS_RE and not NEGATION_RE")
        if r["peer_before_reply_unknown"]:
            raise SystemExit(f"peer_before_reply: {r['peer_before_reply_unknown']} same-reply agents of {key} could not be aligned")
        M.put(macro("MissingLeg", key, "PeerBeforeReply"), fint(r["peer_before_reply"]),
              src + "; same-reply agents for which a peer's committed write to the source preceded, in ledger order, the first executed call of the reply carrying the rejected debit")
        M.put(macro("MissingLeg", key, "DebitFirst"), fint(r["debit_first"]),
              src + "; same-reply agents whose rejected debit came before the committed credit in that reply's call order (post hoc, review F1 S1)")
    conf = ml["Confirmatory"]
    M.put("SiiDMissingLegConfirmatoryNotSameReply", fint(conf["agents"] - conf["same_reply"]),
          "transcripts: confirmatory missing_leg agents whose first committed credit was not sent in the same reply as the first rejected debit")
    tsh = mech["transfer_share"]
    for k, v in tsh.items():
        sm, c = k.split("|")
        M.put(macro("XferShare", sm, CFG_SHORT[c], "Pct"), fint(int(round(100 * v["share"]))),
              f"transcripts and results.json H1-diff|{sm}|{c}: sum over the transfer clusters of contended minus control fs over the sum over all {v['clusters']} clusters, in per cent")
    shares = [v["share"] for v in tsh.values()]
    M.put("SiiDXferShareMinPct", fint(int(round(100 * min(shares)))), "smallest transfer-family share of the conditional-write Delta over the confirmatory models and the two conditional-write configs, in per cent")
    M.put("SiiDXferShareMaxPct", fint(int(round(100 * max(shares)))), "largest transfer-family share of the conditional-write Delta over the confirmatory models and the two conditional-write configs, in per cent")
    perc = mech["perceivable"]
    for k, v in perc.items():
        sm, c = k.split("|")
        M.put(macro("Perceivable", sm, CFG_SHORT[c]), fnum(v["share"]),
              f"transcripts: contended agents of {sm}, {c}, aware off, core blocks ({v['agents']} agents): a 409 or 423 response, or a re-read returning a changed value, before the first primitive call")
    pc = [perc[f"{SHORT[m]}|{c}"]["share"] for m in CONFIRMATORY for c in LOCK_CONFIGS]
    M.put("SiiDPerceivableConfMin", fnum(min(pc)), "smallest perceivable-signal share over the confirmatory models and the two lock configs")
    M.put("SiiDPerceivableConfMax", fnum(max(pc)), "largest perceivable-signal share over the confirmatory models and the two lock configs")
    cw = mech["compensation_windows"]
    for k, v in cw.items():
        sm, c = k.split("|")
        src = f"transcripts: compensated contended write-skew episodes of {sm}, {c}, aware off, core blocks"
        M.put(macro("CompWin", sm, CFG_SHORT[c], "Episodes"), fint(v["episodes"]), src)
        M.put(macro("CompWin", sm, CFG_SHORT[c], "Window"), fint(v["with_window"]), src + "; with a window in which both agents' first changed records held non-initial values")
        M.put(macro("CompWin", sm, CFG_SHORT[c], "PeerRead"), fint(v["peer_read_in_window"]), src + "; an agent other than the one whose write closed the window read a record of its intent inside it")
    M.put("SiiDCompWinTotalEpisodes", fint(sum(v["episodes"] for v in cw.values())), "transcripts: compensated contended write-skew episodes, all models and configs, aware off, core blocks")
    M.put("SiiDCompWinTotalWindow", fint(sum(v["with_window"] for v in cw.values())), "transcripts: of these, episodes with a broken-constraint window")
    M.put("SiiDCompWinTotalPeerRead", fint(sum(v["peer_read_in_window"] for v in cw.values())), "transcripts: of these, episodes in which the other agent read a record of its intent inside the window")
    fo = mech["protocol_order"].get("Fable|locks|contended") or {}
    M.put("SiiDFableCoreMultiAgents", fint(fo.get("multi_agents")), "transcripts: Fable 5 contended agents on the multi-record families under locks, aware off, core blocks")
    M.put("SiiDFableCoreLockedAll", fint(fo.get("locked_all_n")), "transcripts: of these, agents whose granted locks covered every record their intent names")
    fx = mech["fable_ext_scope"]
    M.put("SiiDFableExtMultiAgents", fint(fx["agents"]), "transcripts: Fable 5 contended agents on the multi-record families under locks, aware off, extension blocks")
    M.put("SiiDFableExtLockedAll", fint(fx["locked_all"]), "transcripts: of these, agents whose granted locks covered every record their intent names")


# ---------------------------------------------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------------------------------------------


def savefig(fig, stem: str, fig_dir: str) -> None:
    fig.savefig(os.path.join(fig_dir, stem + ".pdf"), metadata=PDF_META)
    fig.savefig(os.path.join(fig_dir, stem + ".png"), dpi=200, metadata=PNG_META)
    plt.close(fig)


def fig_delta(dd: Mapping[str, Any], reg: Mapping[str, Any], fig_dir: str) -> None:
    """Fig A: registered Delta (contended - control) of fs_nonserializable with its 95 % percentile interval, per model x
    config, none included as the calibration contrast; the pooled confirmatory estimate as a black star. Revised after
    reviews T7c A12 and T8c C8: text at 7 pt, larger markers, no x grid (the margin lines alone), and a legend built from
    proxy handles that show each model's marker exactly as plotted (descriptive models hollow, Fable 5 a hollow plus)."""
    T = reg["tests"]
    configs = list(CONFIGS)
    series = [(SHORT[m], NAME_PLAIN[m], MODEL_COLOR[m], MODEL_MARKER[m]) for m in MODELS] + [("pooled", "pooled", INK, "*")]
    fs_txt = 7
    ms_pt, ms_star = 4.6, 7.0
    fig, ax = plt.subplots(figsize=(COL_W, 2.5))
    k = len(series)
    offs = [-0.36 + 0.72 * i / (k - 1) for i in range(k)]
    dc, dp = reg["res"]["constants"]["delta_cell"], reg["res"]["constants"]["delta_pooled"]
    handles = []
    for i, (sm, name, col, mk) in enumerate(series):
        descriptive = sm in {SHORT[m] for m in DESCRIPTIVE}
        style = (dict(mfc="white", mec=col, ms=ms_pt, mew=1.0) if descriptive else
                 dict(color=col, ms=ms_star if mk == "*" else ms_pt, mec="white", mew=0.5))
        for j, c in enumerate(configs):
            tid = f"{'H1cal-diff' if c == 'none' else 'H1-diff'}|{sm}|{c}"
            t = T.get(tid)
            if not t or t.get("estimate") is None:
                continue
            lo, hi = t["ci95"]
            y = j + offs[i]
            if hi > lo:  # a zero-width percentile interval (every cluster equal) is not drawn as an interval
                ax.plot([lo, hi], [y, y], color=col, lw=1.0, solid_capstyle="round", zorder=2, alpha=0.6 if descriptive else 1.0)
            ax.plot([t["estimate"]], [y], mk, zorder=3, clip_on=False, **style)
        handles.append(Line2D([], [], ls="none", marker=mk, label=name, **style))
    ax.axvline(0.0, color=MUTED, lw=0.7, zorder=1)
    for x in (-dc, dc):
        ax.axvline(x, color=MUTED, lw=0.7, ls=(0, (3, 2)), zorder=1)
    for x in (-dp, dp):
        ax.axvline(x, color=MUTED, lw=0.7, ls=(0, (1, 1.5)), zorder=1)
    handles.append(Line2D([], [], color=MUTED, lw=0.7, ls=(0, (3, 2)), label=f"$\\pm\\delta$ cell ({dc:g})"))
    handles.append(Line2D([], [], color=MUTED, lw=0.7, ls=(0, (1, 1.5)), label=f"$\\pm\\delta$ pooled ({dp:g})"))
    ax.set_yticks(range(len(configs)))
    ax.set_yticklabels([c + ("\n(calibration)" if c == "none" else "") for c in configs], family="monospace", fontsize=fs_txt)
    ax.tick_params(axis="x", labelsize=fs_txt)
    ax.invert_yaxis()
    ax.set_ylim(len(configs) - 0.5, -0.6)
    ax.set_xlim(-0.4, 1.08)
    ax.set_xlabel("$\\Delta$ committed-intent serializability failures,\ncontended $-$ control (95% percentile CI)", fontsize=fs_txt)
    for j in range(len(configs) - 1):
        ax.axhline(j + 0.5, color=GRID, lw=0.5)
    ax.legend(handles=handles, ncol=3, loc="upper center", bbox_to_anchor=(0.36, -0.25), frameon=False, handletextpad=0.25,
              columnspacing=0.6, handlelength=1.4, fontsize=fs_txt, numpoints=1)
    savefig(fig, "fig_s2_delta", fig_dir)


def fig_primitives(dd: Mapping[str, Any], fig_dir: str) -> None:
    """Fig B: primitive use by config per model (contended arm, aware off, core blocks): grouped bars for lock attempt,
    conditional write and unprotected committed write (share of agents)."""
    configs = list(CONFIGS)
    fig, axes = plt.subplots(2, 3, figsize=(TEXT_W, 3.3), sharex=True, sharey=True)
    w = 0.26
    for ax, m in zip(axes.flat, MODELS):
        for j, c in enumerate(configs):
            p = dd["primitives"].get(f"main|{SHORT[m]}|{c}|aware0|contended")
            if p is None:
                continue
            vals = [(p["lock"] or 0.0, -w, LOCK_COLOR, "", LOCK_COLOR), (p["cas"] or 0.0, 0.0, CAS_COLOR, "////", CAS_COLOR),
                    (p["naive"] or 0.0, w, "none", "", INK)]
            for v, dx, fc, hatch, ec in vals:
                ax.bar(j + dx, v, width=w * 0.92, color=fc, hatch=hatch, edgecolor="white" if fc != "none" else ec,
                       linewidth=0.6, zorder=2)
                if fc == CAS_COLOR:
                    ax.bar(j + dx, v, width=w * 0.92, color="none", edgecolor=CAS_COLOR, linewidth=0.4, zorder=3)
        p0 = dd["primitives"].get(f"main|{SHORT[m]}|locks|aware0|contended") or {}
        ax.set_title(NAME_PLAIN[m] + ("" if m in CONFIRMATORY else " (descriptive)") + f"\n{p0.get('agents', 0)} agents per config", fontsize=6, pad=2)
        ax.set_xticks(range(len(configs)))
        ax.set_xticklabels(configs, family="monospace", rotation=30, ha="right", fontsize=5.5)
        ax.set_ylim(0, 1.0)
        ax.set_yticks([0, 0.5, 1.0])
        ax.set_yticklabels(["0", ".5", "1"])
        ax.grid(axis="y", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", length=0)
    for ax in axes[:, 0]:
        ax.set_ylabel("share of agents")
    handles = [Patch(facecolor=LOCK_COLOR, edgecolor="white", label="lock attempt (acquire_lock)"),
               Patch(facecolor=CAS_COLOR, edgecolor=CAS_COLOR, hatch="////", label="conditional write (expected_version)"),
               Patch(facecolor="none", edgecolor=INK, label="unprotected committed write")]
    fig.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.03), frameon=False, columnspacing=1.2, handletextpad=0.4)
    fig.text(0.5, -0.085, "contended arm, aware off, core blocks; shares overlap (an agent can lock and write conditionally)", ha="center", fontsize=6, color=MUTED)
    fig.tight_layout(h_pad=0.8, w_pad=0.5, rect=(0, 0.04, 1, 1))
    savefig(fig, "fig_s2_primitives", fig_dir)


def fig_firstreply(dd: Mapping[str, Any], fig_dir: str) -> None:
    """Fig C: a0 first-reply lock share, aware off (hollow) vs on (filled), per model, one panel per lock config."""
    models = [m for m in MODELS if any(k.startswith(SHORT[m] + "|") for k in dd["probes"])]
    fig, axes = plt.subplots(2, 1, figsize=(COL_W, 2.9), sharex=True)
    for ax, c in zip(axes, LOCK_CONFIGS):
        for i, m in enumerate(models):
            off = dd["probes"].get(f"{SHORT[m]}|{c}|aware0")
            on = dd["probes"].get(f"{SHORT[m]}|{c}|aware1")
            if off is None or on is None or off.get("a0_lock") is None or on.get("a0_lock") is None:
                continue
            x0, x1 = off["a0_lock"], on["a0_lock"]
            col = MODEL_COLOR[m]
            ax.plot([x0, x1], [i, i], color=col, lw=1.2, zorder=2, solid_capstyle="round")
            ax.plot([x0], [i], MODEL_MARKER[m], mfc="white", mec=col, ms=4.2, mew=0.9, zorder=3)
            ax.plot([x1], [i], MODEL_MARKER[m], color=col, ms=4.2, mec="white", mew=0.5, zorder=4)
        ax.set_yticks(range(len(models)))
        labels = []
        for m in models:
            off = dd["probes"].get(f"{SHORT[m]}|{c}|aware0") or {}
            h3 = dd["h3"].get(SHORT[m]) or {}
            tag = ""
            if h3.get("status") == "tested":
                tag = ", no claim" if not h3.get("reject") else ""
            elif m in DESCRIPTIVE:
                tag = ", descr."
            labels.append(f"{NAME_PLAIN[m]}, {off.get('a0_n', 0)}{tag}")
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlim(-0.03, 1.03)
        ax.grid(axis="x", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        ax.text(1.0, -0.72, c, ha="right", va="bottom", family="monospace", fontsize=6.5)
        ax.set_ylim(len(models) - 0.5, -0.8)
        ax.tick_params(axis="y", length=0)
    axes[-1].set_xlabel("share of a0 first replies with a lock call (contended probes; label: model, probed units)")
    handles = [Line2D([], [], marker="o", mfc="white", mec=INK, ms=4.2, mew=0.9, linestyle="none", label="aware sentence off"),
               Line2D([], [], marker="o", color=INK, ms=4.2, mec="white", mew=0.5, linestyle="none", label="aware sentence on")]
    fig.legend(handles=handles, loc="lower center", ncol=2, bbox_to_anchor=(0.55, -0.04), frameon=False, handletextpad=0.3, columnspacing=1.5)
    fig.tight_layout(h_pad=0.6, rect=(0, 0.05, 1, 1))
    savefig(fig, "fig_s2_firstreply", fig_dir)


def fig_family(dd: Mapping[str, Any], fig_dir: str) -> None:
    """Fig D: contended fs_nonserializable share per family for the confirmatory models under each config (aware off,
    core blocks), the four single-record families left of the three constraint-spanning ones. Exploratory."""
    fams = ["inventory_last_unit", "inventory_still_valid", "seat_same", "ticket_same",
            "transfer_shared_source", "budget_write_skew", "joint_account_write_skew"]
    labels = ["inv. last", "inv. valid", "seat", "ticket", "transfer", "budget", "joint"]
    configs = list(CONFIGS)
    fig, axes = plt.subplots(2, 2, figsize=(TEXT_W, 3.2), sharey=True)
    w = 0.26
    for ax, c in zip(axes.flat, configs):
        for i, m in enumerate(CONFIRMATORY):
            row = dd["family_fs"].get(f"{SHORT[m]}|{c}") or {}
            vals = [(row.get(f) or {}).get("fs") or 0.0 for f in fams]
            xs = [j + (i - 1) * w for j in range(len(fams))]
            ax.bar(xs, vals, width=w * 0.92, color=MODEL_COLOR[m], edgecolor="white", linewidth=0.4, zorder=2,
                   label=NAME_PLAIN[m] if c == configs[0] else None)
        ax.axvline(3.5, color=MUTED, lw=0.6, ls=(0, (3, 2)), zorder=1)
        ax.set_title(c + ("  (calibration)" if c == "none" else ""), family="monospace", fontsize=6.5, pad=10)
        ax.set_xticks(range(len(fams)))
        ax.set_xticklabels(labels, fontsize=5.5, rotation=30, ha="right")
        ax.set_ylim(0, 1.0)
        ax.set_yticks([0, 0.5, 1.0])
        ax.set_yticklabels(["0", ".5", "1"])
        ax.grid(axis="y", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", length=0)
        ax.text(1.5, 1.02, "single-record", ha="center", va="bottom", fontsize=5.5, color=MUTED)
        ax.text(5.0, 1.02, "constraint spans records", ha="center", va="bottom", fontsize=5.5, color=MUTED)
    for ax in axes[:, 0]:
        ax.set_ylabel("contended failure share")
    fig.legend(loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.03), frameon=False, columnspacing=1.2, handletextpad=0.4)
    fig.tight_layout(w_pad=0.6, h_pad=1.2, rect=(0, 0.04, 1, 1))
    savefig(fig, "fig_s2_family", fig_dir)


# ---------------------------------------------------------------------------------------------------------------
# Facts file
# ---------------------------------------------------------------------------------------------------------------

GROUP_TITLES = {
    "a_h1": "Table `tab:s2-h1` (tables/s2_h1.tex): H1 rates per arm",
    "b_primitives": "Tables `tab:s2-primitives` and `tab:s2-timing` (tables/s2_primitives.tex, s2_timing.tex): primitive use, timing and endings",
    "c_outcomes": "Tables `tab:s2-outcomes` and `tab:s2-flags` (tables/s2_outcomes.tex, s2_flags.tex): outcome classes and failure flags",
    "d_probes": "Table `tab:s2-probes` (tables/s2_probes.tex): first-reply probes",
    "d_h3_leak": "Table `tab:s2-h3-leak` (tables/s2_h3_leak.tex): H3 and the leakage check",
    "e_exposure": "Table `tab:s2-exposure` (tables/s2_exposure.tex): exposure check",
    "f_h4": "Table `tab:s2-h4` (tables/s2_h4.tex): H4 rates and H4b",
    "g_budget": "Table `tab:s2-budget` (tables/s2_budget.tex): budget and spend",
    "h_selection": "Table `tab:s2-selection` (tables/s2_selection.tex): selection and exclusions",
    "h_deviations": "Table `tab:s2-deviations` (tables/s2_deviations_*.tex): deviations table (complete)",
    "m1_lock_mech": "Table `tab:s2-lock-mech` (tables/s2_lock_mech.tex): POST HOC lock-failure mechanisms, protocol order and lock scope",
    "m2_missing_leg": "Table `tab:s2-missing-leg` (tables/s2_missing_leg.tex): POST HOC half-done transfers and endings after a 409",
    "m3_overlap_class": "Table `tab:s2-overlap-class` (tables/s2_overlap_class.tex): reads overlap (registered) and the task-class split",
    "m4_ws_protocols": "Table `tab:s2-ws-protocols` (tables/s2_ws_protocols.tex): POST HOC write-skew protocols",
    "m5_false_success": "Table `tab:s2-false-success` (tables/s2_false_success.tex): POST HOC success reported without a write",
    "m6_dsg": "Table `tab:s2-dsg-agree` (tables/s2_dsg_agree.tex): agreement with the three graph verdicts",
    "m7_exploratory": "Tables `tab:s2-exploratory` and `tab:s2-extension` (tables/s2_exploratory.tex, s2_extension.tex): other registered exploratory items",
    "m7_example": "Table `tab:s2-example` (tables/s2_example.tex): the worked verdict example (one ledger)",
    "m8_tests_full": "Tables `tab:s2-tests-full*` (tables/s2_tests_full_*.tex): every registered test in full",
    "m9_firth": "Table `tab:s2-firth` (tables/s2_firth.tex): the registered cross-model regression (stdlib Firth fit, wild cluster bootstrap)",
    "i_vs_none": "Table `tab:s2-vs-none` (tables/s2_vs_none.tex): integrity by config vs none",
    "j_first_protective": "Table `tab:s2-first-protective` (tables/s2_first_protective.tex): first_protective under all_available",
    "k_family_fs": "Table `tab:s2-family-fs` (tables/s2_family_fs.tex): EXPLORATORY fs_nonserializable per family",
    "misc": "Other",
}


def plain(s: str) -> str:
    """TeX number string -> plain text for the facts file."""
    return s.replace("$-$", "-").replace(r"\textemdash{}", "-").replace("$<$", "<").replace("{,}", ",")


def facts_markdown(dd: Mapping[str, Any], reg: Mapping[str, Any], M: Macros, args: argparse.Namespace, reserved_src: str) -> str:
    res = reg["res"]
    T = reg["tests"]
    L: List[str] = []
    L.append("# Facts: Study 2 results (descriptive tables, figures and macros)")
    L.append("")
    L.append("Generated by `analysis5/descriptives5.py` from the final Study 2 data. Every number printed by the Study 2 tables "
             "is listed here with its source. Two macro files feed the tables: the registered `analysis5/out_study2/numbers.tex` "
             "(`\\Sii...`, written by the frozen `analyze5.py`; it holds every registered estimate, interval, p-value, claim word, "
             "eligibility rate and leakage statistic) and the descriptive `latex/study2_out/study2_numbers.tex` (`\\SiiD...`, this "
             "script; rates per arm, counts, spend). Model names come from the Study 1 `numbers.tex` (`\\ModelQwenName` etc.). "
             "`results.json` paths are given for registered values; computed values name the transcripts and the rule.")
    L.append("")
    L.append(f"- registered analysis: `results.json` sha256 `{reg['results_sha256']}`, `numbers.tex` sha256 `{reg['numbers_sha256']}`, "
             f"analyze5.py sha256 `{res.get('analyze5_sha256')}`; inputs {res['inputs']['n_files']} transcripts, list sha256 "
             f"`{res['inputs']['sha256_of_list']}`.")
    L.append(f"- this script read {dd['selection']['files']} transcripts: probe {dd['selection']['block'].get('priority_0', 0)}, core "
             f"{dd['selection']['block'].get('priority_1', 0)}, extension {dd['selection']['block'].get('priority_4', 0)}, unplanned "
             f"{dd['selection']['block'].get('unplanned', 0)} (block membership from `src5/plan_study2.json`); the registered analysis "
             f"reports {json.dumps(res['selection']['block'], sort_keys=True)}.")
    L.append(f"- macro collision check: {len(M.vals)} descriptive macros, {len(M.registered)} registered macros, "
             f"{len(M.reserved)} macros of {reserved_src}; no name is shared. Registered macros the tables reference: "
             f"{len(M.referenced_registered)}.")
    L.append("- reporting rule (registration, Exploratory analysis): every number here is pre-specified descriptive or a registered "
             "statistic; none carries a test unless the registered macro says so. Descriptive numbers take the inline tag "
             "*(descriptive)*; confirmatory claims come only from the registered claim words.")
    L.append("")
    L.append("## Registered verdicts (from results.json `summary`; the claim text is the registered wording)")
    L.append("")
    def g3(x: Optional[float]) -> str:
        return "None" if x is None else f"{x:.3g}"

    for k in sorted(res.get("summary") or {}):
        s = res["summary"][k]
        est = "None" if s["estimate"] is None else f"{s['estimate']:.4f}"
        L.append(f"- `{k}`: status {s['status']}, estimate {est}, p {g3(s['p'])}, p_adj {g3(s['p_adj'])}, "
                 f"reject {s['reject']}, reading {s['reading']}; claim: {s['claim']}")
    L.append("")
    L.append("## Consistency check: computed cluster-mean differences against the registered estimates")
    L.append("")
    worst = max((c["abs_diff"] for c in dd["checks_delta"]), default=0.0)
    L.append(f"{len(dd['checks_delta'])} cells compared (H1, H1 calibration, H4; per model and pooled); largest absolute difference "
             f"{worst:.2e}. The descriptive rates per arm therefore sit on the same clusters and pairs as the registered contrast.")
    L.append("")
    L.append("## Highlights (facts, with the macro that prints each)")
    L.append("")
    hl_start = len(L)
    for m in CONFIRMATORY + (POOLED,):
        sm = "Pooled" if m == POOLED else SHORT[m]
        name = "pooled" if m == POOLED else NAME_PLAIN[m]
        for c in H1_CONFIGS:
            r = dd["h1"].get(f"{sm}|{c}|aware0") or {}
            t = T.get(f"H1-diff|{'pooled' if m == POOLED else sm}|{c}") or {}
            L.append(f"- H1 {name} `{c}`: contended {fnum(r.get('cont'))} (`\\{macro('Fs', sm, CFG_SHORT[c], 'Cont')}`), control "
                     f"{fnum(r.get('ctrl'))} (`\\{macro('Fs', sm, CFG_SHORT[c], 'Ctrl')}`), Delta {fnum(t.get('estimate'))} "
                     f"95% [{fnum((t.get('ci95') or [None, None])[0])}, {fnum((t.get('ci95') or [None, None])[1])}] "
                     f"(`\\{reg_macro('HoneDiff', sm, CFG_SHORT[c], 'Est')}`, `Lo`, `Hi`), p_Holm {fp(t.get('p_adj'))}; {t.get('claim')}")
    for m in DESCRIPTIVE:
        sm = SHORT[m]
        for c in H1_CONFIGS:
            r = dd["h1"].get(f"{sm}|{c}|aware0") or {}
            t = T.get(f"H1-diff|{sm}|{c}") or {}
            L.append(f"- H1 {NAME_PLAIN[m]} `{c}` (descriptive): contended {fnum(r.get('cont'))}, control {fnum(r.get('ctrl'))}, Delta "
                     f"{fnum(t.get('estimate'))} 95% [{fnum((t.get('ci95') or [None, None])[0])}, {fnum((t.get('ci95') or [None, None])[1])}], "
                     f"{t.get('n_clusters')} clusters, no test.")
    for m in MODELS:
        sm = SHORT[m]
        for c in ("locks", "all_available"):
            p = dd["primitives"].get(f"main|{sm}|{c}|aware0|contended") or {}
            L.append(f"- primitives {NAME_PLAIN[m]} `{c}` contended: lock attempt {fnum(p.get('lock'))}, granted {fnum(p.get('lock_granted'))}, "
                     f"effective {fnum(p.get('lock_effective'))} of {p.get('lock_effective_n')} lock-granted committing agents, conditional write "
                     f"{fnum(p.get('cas'))}, unprotected write {fnum(p.get('naive'))}, reactive {fnum(p.get('reactive'))}, lock after signal "
                     f"{p.get('lock_after_n')} agents, abandoned {p.get('abandoned_n')}, cap_truncated {p.get('cap_truncated')}, mean completions "
                     f"{fnum(p.get('completions'), 1)} (`\\{macro('Prim', sm, CFG_SHORT[c], 'Cont', 'LockAtt')}` etc.).")
        p = dd["primitives"].get(f"main|{sm}|cas_available|aware0|contended") or {}
        L.append(f"- primitives {NAME_PLAIN[m]} `cas_available` contended: conditional write {fnum(p.get('cas'))}, unprotected write "
                 f"{fnum(p.get('naive'))}, reactive {fnum(p.get('reactive'))}, abandoned {p.get('abandoned_n')}.")
    for sm, h in sorted(dd["h3"].items()):
        L.append(f"- H3 {sm}: Delta {fnum(h['estimate'])} 95% [{fnum((h.get('ci95') or [None, None])[0])}, {fnum((h.get('ci95') or [None, None])[1])}], "
                 f"p_Holm {fp(h.get('p_adj'))}, status {h['status']}, per config {json.dumps(h['per_config'])}; {h['claim']}")
    for sm, lk in sorted(dd["leakage"].items()):
        L.append(f"- leakage {sm}: estimate {fnum(lk.get('estimate'))}, 95% {lk.get('ci95')}, p {fp(lk.get('p'))}, status {lk.get('status')}, leaks {lk.get('leaks')}.")
    for k, r in sorted(dd["h4"].items()):
        L.append(f"- H4 {k}: contended {fnum(r.get('cont'))}, control {fnum(r.get('ctrl'))}, Delta {fnum(r.get('delta'))}, q {fnum(r.get('q'))}, "
                 f"reading {r.get('reading')}, status {r.get('status')}; H4b {json.dumps(r.get('h4b'))}")
    b = dd["budget"]
    L.append("- budget: " + "; ".join(f"{p} spend {fmoney(b['providers'][p]['spend'])} of cap {fmoney(b['providers'][p]['cap'])} (estimate "
                                        f"{fmoney(b['providers'][p]['estimate'])}, recorded in transcripts {fmoney(b['providers'][p]['recorded_in_transcripts'])})"
                                        for p in PROVIDERS) + f"; total {fmoney(b['total']['spend'])} of {fmoney(b['total']['cap'])}.")
    if b.get("window"):
        w = b["window"]
        L.append(f"- OpenRouter key window {w['from_utc']} to {w['to_utc']}: key usage change {fmoney(w['key_usage_change_usd'])}, Study 2 spend "
                 f"{fmoney(w['study2_spend_usd'])}, others {w['others_spend_usd']:.2e} (float noise; reported as 0.00), lane exit {w['lane_exit']}, "
                 f"stopped by external cause {w['stopped_by_external_cause']}.")
    s = dd["selection"]
    L.append(f"- selection: excluded rows {sum(v for k, v in s['counts'].items() if k != 'duplicate_transcripts_ignored')}, duplicates "
             f"{s['counts'].get('duplicate_transcripts_ignored', 0)}, provider failures {s['provider_failures_total']} "
             f"({json.dumps(s['provider_failures'])}), GPT non-OpenAI-host episodes {s['gpt_non_openai_episodes_main']} core + "
             f"{s['gpt_non_openai_episodes_extension']} extension ({s['gpt_non_openai_completions']} completions), cap_truncated "
             f"{s['cap_truncated_main']}, cap endings {s['cap_endings_main']}, refusals {s['refusal_agents']}, agent errors {s['error_agents']}, "
             f"agents not ending returned {s['not_returned_agents']}, abandoned agents {s['abandoned_agents']}, deadlock episodes {s['deadlock_episodes']}.")
    L.append(f"- temperature_effective per model (all completions): {json.dumps(s['temperature_effective'], sort_keys=True)}.")
    L.append(f"- served hosts: {json.dumps(s['served_host'], sort_keys=True)}; served ids: {json.dumps(s['model_served'], sort_keys=True)}.")
    L.append(f"- sensitivity analyses with changed verdicts (registered): {json.dumps(s['sensitivity_changed'], sort_keys=True)}; s1 episodes dropped "
             f"{s['s1_dropped_with_partners']}; s9 pairs scored against equivalence {s['s9_pairs_scored_against']}.")
    L[hl_start:] = [plain(x) for x in L[hl_start:]]
    L.append("")
    L.append("## Notes for the writers (observations, not claims)")
    L.append("")
    L.append("- STUDY2_RUN_LOG.md says early Haiku probe completions mix temperature 0 and the provider default and that "
             "`temperature_effective` identifies each case. In the written transcripts every Claude completion carries "
             "`temperature_effective` null (counts above) and `lane_anthropic.log` shows the first paid Haiku batch errored in full "
             "(errored=66 of 66) before the driver resent without the parameter; the later batches' errors were requests built before "
             "the rejection was recorded. The deviations table states that the data cannot distinguish the two and reports every "
             "Claude completion at the provider default.")
    mech = dd["mech"]
    lm = mech["lock_mech"]
    L.append("- POST HOC lock-failure mechanisms (contended locks, fs-failed episodes; non-exclusive): " + "; ".join(
        f"{NAME_PLAIN[m]} failed {lm[SHORT[m]]['failed']}, read-then-lock {lm[SHORT[m]]['read_then_lock']}, own-record lock only "
        f"(write skew) {lm[SHORT[m]]['write_skew_own_only']}, no lock {lm[SHORT[m]]['no_lock']}, missing leg {lm[SHORT[m]]['missing_leg']}"
        for m in CONFIRMATORY) + ".")
    ml = mech["missing_leg"]["Confirmatory"]
    L.append(f"- POST HOC half-done transfers (confirmatory models, CAS configs): {ml['agents']} missing-leg agents; credit in the same reply as the "
             f"rejected debit {ml['same_reply']}, after a re-read {ml['credit_after_reread']}, no debit attempted {ml['no_debit_attempted']}; a re-read "
             f"after the rejection returned the expected post-debit balance for {ml['saw_expected']}; list_effects called by {ml['listed_effects']}.")
    af = mech["after409"]["Confirmatory"]
    L.append(f"- POST HOC after a 409 (confirmatory models, CAS configs, contended): {af['agents']} agents, {af['reread']} re-read the record before "
             f"writing it again, {af['wrong']} ended wrong ({af['missing_leg']} half-done transfers, {af['phantom']} success reports without a write).")
    L.append("- POST HOC success reported without a write, CAS configs together: " + ", ".join(
        f"{NAME_PLAIN[m]} {sum(mech['phantom_totals'].get(f'{SHORT[m]}|{c}', {}).get('phantom', 0) for c in ('cas_available', 'all_available'))}" for m in MODELS) + ".")
    tc = mech["task_class"]
    L.append("- Task class (cluster-mean contended fs, single / multi): " + "; ".join(
        f"{NAME_PLAIN[m]} {c} {fnum((tc.get(f'{SHORT[m]}|{c}|single') or {}).get('cont'))} / {fnum((tc.get(f'{SHORT[m]}|{c}|multi') or {}).get('cont'))}"
        for m in CONFIRMATORY for c in CONFIGS) + ".")
    ws = mech["ws_protocols"]
    L.append("- POST HOC write-skew protocols, Gemini cas_available: " + json.dumps(ws.get("Gemini|cas_available")) + "; Gemini none: " + json.dumps(ws.get("Gemini|none")) + ".")
    pmt = mech["promote"]
    L.append("- POST HOC the scorer's `promote` choice (a committed no-op conditional write-back of a record the intent reads but does not "
             "write; reviews T7b M-A, T8b N2), cells with at least one such agent (core blocks): " + "; ".join(
                 f"{k}: {v['promoted']} of {v['agents']} agents ({', '.join(v['ids'])})" for k, v in sorted(pmt.items()) if v["promoted"]) + ".")
    L.append("- POST HOC transfer agents whose credit committed while their debit never did (confirmatory models, CAS configs, contended): "
             f"{ml['credit_only']} agents, {ml['credit_only_repaired']} of them reversed the credit (scorer rolled_back; outcome compensated): "
             + ", ".join(mech.get("transfer_repaired_ids") or []) + f"; the other {ml['agents']} are the missing-leg agents, of whose final "
             f"replies {ml['reported_success']} match the success pattern of the false-success table.")
    lm2 = mech["lock_mech"]
    L.append("- POST HOC exclusivity of the three lock-failure mechanisms (failed contended locks episodes): " + "; ".join(
        f"{NAME_PLAIN[m]} exactly one {lm2[SHORT[m]]['exactly_one']}, more than one {lm2[SHORT[m]]['more_than_one']}, none {lm2[SHORT[m]]['none_of_three']}; "
        f"guard-records-not-locked scope pairs both-own {lm2[SHORT[m]]['own_only_both_own']}, one-none {lm2[SHORT[m]]['own_only_one_none']}, one-all {lm2[SHORT[m]]['own_only_one_all']}"
        for m in CONFIRMATORY) + ".")
    L.append(f"- DSG agreement (aware-off core, both arms): {json.dumps(mech['dsg_agreement'])}.")
    L.append(f"- Within-prompt agreement: {json.dumps(mech['within_prompt'])}; lease lengths: {json.dumps(mech['lease'])}.")
    if mech.get("firth"):
        L.append("- Firth regression: " + json.dumps({o: {k: v for k, v in f.items() if k in ("n", "k", "converged", "clusters", "draws", "dropped_cells", "separated_cells", "weight_vectors")}
                                                      for o, f in mech["firth"]["fits"].items()}, sort_keys=True) + ".")
    L.append("- Every agent of every core and extension episode ended `returned`: no cap ending, no truncation, no provider error, no "
             "refusal and no safety stop. The exclusion rule, the cap_truncated stratum, sensitivity 1 (no agent above 24 calls) and "
             "sensitivity 9 (no excluded pair) therefore act on nothing in Study 2.")
    L.append("- Under `locks`, Haiku 4.5 attempted a lock in most contended agents but its locks were effective in none of them "
             "(the basis read preceded the lease, `fenced_stale_basis`): lock use and lock protection are different measures.")
    L.append("- Under `cas_available` every model used the conditional write in about nine of ten contended agents, and the three "
             "confirmatory models still added 0.34 to 0.43 integrity failures (write skew and missing legs, which a per-record "
             "version check does not prevent); GPT-5.5, Gemini 4 Argon and Fable 5 added 0.08, 0.00 and 0.00 (descriptive).")
    L.append("- No first reply carried a `cas` token and no episode agent ever ended other than `returned`; `first_reply` codes seen: "
             "read, lock, blind_write (Gemini aware on, under `none`).")
    L.append("- The H4 equivalence cells are all uninformative by the registered q gate (q 0.04 to 0.12 <= delta 0.25): few "
             "contended agents were at risk because most protected before their first signal (or saw none).")
    L.append("")
    L.append("## Macro list (name, value, source)")
    L.append("")
    cur = None
    for name in sorted(M.vals, key=lambda n: (M.group[n], n)):
        g = M.group[name]
        if g != cur:
            L.append("")
            L.append(f"### {GROUP_TITLES.get(g, g)}")
            L.append("")
            L.append("| macro | value | source |")
            L.append("|---|---|---|")
            cur = g
        L.append(f"| `\\{name}` | {plain(M.vals[name]).replace('|', '/')} | {M.src[name].replace('|', '/')} |")
    L.append("")
    L.append("### Registered macros referenced by the tables (defined in analysis5/out_study2/numbers.tex)")
    L.append("")
    for name in sorted(M.referenced_registered):
        L.append(f"- `\\{name}`")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------------------------


def jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {(k if isinstance(k, str) else "|".join(map(str, k)) if isinstance(k, tuple) else str(k)): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, set):
        return sorted(jsonable(v) for v in x)
    return x


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.path.join(ROOT, "study2_data", "results5", "study2"))
    ap.add_argument("--results", default=os.path.join(ROOT, "study2_data", "analysis5", "out_study2", "results.json"))
    ap.add_argument("--numbers", default=os.path.join(ROOT, "study2_data", "analysis5", "out_study2", "numbers.tex"))
    ap.add_argument("--plan", default=os.path.join(ROOT, "src5", "plan_study2.json"))
    ap.add_argument("--study2-tex", default=os.path.join(ROOT, "paper-concurrency", "latex", "study2.tex"),
                    help="macros defined there are reserved (collision check)")
    ap.add_argument("--out", default=os.path.join(ROOT, "paper-concurrency", "latex", "study2_out"))
    ap.add_argument("--facts", default=os.path.join(ROOT, "paper-concurrency", "latex", "facts", "src", "study2_results_facts.md"))
    args = ap.parse_args(argv)

    plan = json.load(open(args.plan))
    reg = load_registered(args.results, args.numbers)
    if reg["res"].get("dry_run"):
        raise SystemExit("results.json is a dry run: refusing to build descriptive tables from rehearsal data")
    reserved = set()
    if os.path.exists(args.study2_tex):
        with open(args.study2_tex) as f:
            for line in f:
                for mm in re.finditer(r"\\(?:re)?newcommand\{\\([A-Za-z]+)\}", line):
                    reserved.add(mm.group(1))

    dirs = discover(args.base)
    if not dirs:
        raise SystemExit(f"no transcript directories under {args.base}")
    recs: List[Dict[str, Any]] = []
    n_files = 0
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.json"))):
            n_files += 1
            with open(path) as f:
                recs.append(normalize(json.load(f), path))
    sel = select(recs, plan)
    D, E = Data(sel["main"]), Data(sel["extension"])
    spend = spend_by_provider(args.base)
    failures = provider_failures(args.base)
    dd = compute(D, E, reg, sel["log"], spend, failures, plan, n_files)
    dd["mech"] = mechanisms(D, E, reg)
    dd["mech"]["firth"] = firth_regression(D, reg)

    # consistency with the registered estimates (same clusters and pairs): refuse to publish tables that disagree
    worst = max((c["abs_diff"] for c in dd["checks_delta"]), default=0.0)
    if worst > 1e-9:
        bad = [c for c in dd["checks_delta"] if c["abs_diff"] > 1e-9]
        raise SystemExit(f"computed cluster-mean differences disagree with results.json: {bad[:5]}")

    s = dd["selection"]
    T = reg["tests"]
    s5 = {t["id"]: t for t in ((reg["res"].get("sensitivity") or {}).get("s5_gpt_openai_only") or {}).get("descriptive") or []}

    def g2(x: Optional[float]) -> str:
        return "n/a" if x is None else f"{x:.2f}"

    def g3(x: Optional[float]) -> str:
        return "n/a" if x is None else f"{x:.3f}"

    fills = {
        "HaikuNull": f"{s['temperature_effective'].get('Haiku', {}).get('null', 0):,}",
        "SonnetNull": f"{s['temperature_effective'].get('Sonnet', {}).get('null', 0):,}",
        "FableNull": f"{s['temperature_effective'].get('Fable', {}).get('null', 0):,}",
        "ProbeFiles": f"{s['block'].get('priority_0', 0):,}",
        "ProvFailTotal": str(s["provider_failures_total"]),
        "ProvFailEpisodes": str(provider_failure_episodes(args.base)),
        "ProvFailNone": str(s["provider_failures"].get("openrouter_openai_gpt-5.5-20260423|none", 0)),
        "ProvFailLocks": str(s["provider_failures"].get("openrouter_openai_gpt-5.5-20260423|locks", 0)),
        "ProvFailAll": str(s["provider_failures"].get("openrouter_openai_gpt-5.5-20260423|all_available", 0)),
        "GptAzureEpisodes": str(s["gpt_non_openai_episodes_main"]),
        "GptAzureCompletions": str(s["gpt_non_openai_completions"]),
        "GptCalNoneEst": g2((T.get("H1cal-diff|Gpt|none") or {}).get("estimate")),
        "GptCalNoneEstSFive": g2((s5.get("H1cal-diff|Gpt|none") or {}).get("estimate")),
        "GptClusters": str((T.get("H1cal-diff|Gpt|none") or {}).get("n_clusters")),
        "GptHtwoCEst": g3((T.get("H2c|Gpt|locks-cas_available") or {}).get("estimate")),
        "GptHtwoCEstSFive": g3((s5.get("H2c|Gpt|locks-cas_available") or {}).get("estimate")),
        "SensFiveChanged": str(len(((reg["res"].get("sensitivity") or {}).get("s5_gpt_openai_only") or {}).get("changed_verdicts") or [])),
        "ExtFiles": str(s["block"].get("priority_4", 0)),
        "GptExt": str(s["block_by_model"].get("Gpt|priority_4", 0)),
        "FableExt": str(s["block_by_model"].get("Fable|priority_4", 0)),
        "LockedWithVersion": str(dd["mech"]["locked_with_version"]),
        "Duplicates": str(s["counts"].get("duplicate_transcripts_ignored", 0)),
    }
    deviations = []
    for row in DEVIATIONS:
        deviations.append({k: v.format(**fills) for k, v in row.items()})

    os.makedirs(args.out, exist_ok=True)
    tables_dir, fig_dir = os.path.join(args.out, "tables"), os.path.join(args.out, "figures")
    os.makedirs(tables_dir, exist_ok=True)
    os.makedirs(fig_dir, exist_ok=True)
    M = Macros(reg["macros"], reserved)
    build_tables(dd, reg, M, tables_dir, [{k: tex_text(v) for k, v in r.items()} for r in deviations])
    build_mech_tables(dd, reg, M, tables_dir)
    with open(os.path.join(args.out, "study2_deviations.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["deviation", "reason", "before_after", "effect", "registered_result"], lineterminator="\n")
        wr.writeheader()
        for r in deviations:
            wr.writerow(r)

    fig_delta(dd, reg, fig_dir)
    fig_primitives(dd, fig_dir)
    fig_firstreply(dd, fig_dir)
    fig_family(dd, fig_dir)

    header = ["% GENERATED by analysis5/descriptives5.py -- do not edit. Descriptive Study 2 numbers (prefix \\SiiD).",
              f"% inputs: {n_files} transcripts under {os.path.basename(args.base)}; results.json sha256 {reg['results_sha256']}; "
              f"registered numbers.tex sha256 {reg['numbers_sha256']}",
              "% Complements the registered numbers.tex (\\Sii...), which the tables also reference; no macro name is shared with it",
              f"% or with latex/study2.tex ({len(reserved)} reserved names checked)."]
    with open(os.path.join(args.out, "study2_numbers.tex"), "w") as f:
        f.write(M.tex(header))
    with open(os.path.join(args.out, "descriptives.json"), "w") as f:
        # provenance (review T7 N9): the interpreter and platform that produced these values, since a rerun elsewhere can
        # differ in the last ulp; the registered results.json and numbers.tex are hash-checked and unchanged by this script
        prov = {"python": sys.version, "platform": sys.platform, "matplotlib": matplotlib.__version__,
                "results_sha256": reg["results_sha256"], "numbers_sha256": reg["numbers_sha256"], "transcripts": n_files}
        json.dump(jsonable({**{k: v for k, v in dd.items() if k != "summary_registered"}, "provenance": prov}), f, indent=1, sort_keys=True)
        f.write("\n")
    os.makedirs(os.path.dirname(args.facts), exist_ok=True)
    with open(args.facts, "w") as f:
        f.write(facts_markdown(dd, reg, M, args, os.path.relpath(args.study2_tex, ROOT)))

    print(f"transcripts {n_files}: blocks {json.dumps(s['block'], sort_keys=True)}; excluded {sum(v for k, v in s['counts'].items() if k != 'duplicate_transcripts_ignored')}")
    print(f"consistency with results.json: {len(dd['checks_delta'])} cells, max |diff| {worst:.1e}")
    print(f"macros: {len(M.vals)} descriptive, {len(M.referenced_registered)} registered referenced; no collisions")
    print(f"written: {args.out} (tables, figures, study2_numbers.tex, study2_deviations.csv, descriptives.json) and {args.facts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
