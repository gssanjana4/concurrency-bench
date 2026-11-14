"""Facts for the deviation note, taken at the switch to batch execution (used by run_rest.sh).

Counts the confirmatory episodes already in BASE/phase{1,2,3}/results.csv (rows with dry_run = 0) per
phase and model, checks that no claude-sonnet-5 / claude-fable-5 episode was run synchronously, and
writes BASE/batch_switch_facts.json once (with --record, which run_rest.sh passes just before the first
Sonnet 5 / Fable 5 batch run, so N is the count at the switch) and BASE/batch_switch_facts_latest.json on every start
(including provider failures per phase and model, rate limits, and how many failed episodes later completed).

    python3 src4_batch/switch_facts.py --base results4/full [--sub /dry_run] [--allow-existing-sync]

Exit 1 if a Sonnet 5 / Fable 5 transcript exists that was not written by the batch driver (the deviation
note would then be wrong), unless --allow-existing-sync.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Any, Dict, Optional, Sequence

import frozen
import model_agent4 as M
import run4

BATCH_MODELS = ("claude-sonnet-5", "claude-fable-5")
GEMINI = "openrouter:google/gemini-4-argon-20261013"  # switched to the Gemini Batch API before any confirmatory episode


def facts(base: str, sub: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {"at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "phases": {},
                           "confirmatory_episodes_total": 0, "batch_models_sync_transcripts": 0,
                           "batch_models_batch_transcripts": 0, "gemini_sync_transcripts": 0,
                           "gemini_batch_transcripts": 0}
    logs = [os.path.join(base, "preflight" + sub, "spend.jsonl")]
    for ph in (1, 2, 3):
        d = os.path.join(base, f"phase{ph}{sub}")
        logs.append(os.path.join(d, "spend.jsonl"))
        counts: Dict[str, int] = {}
        p = os.path.join(d, "results.csv")
        if os.path.exists(p):
            with open(p, newline="") as f:
                for r in csv.DictReader(f):
                    if sub or r.get("dry_run") == "0":
                        counts[r["model"]] = counts.get(r["model"], 0) + 1
        out["phases"][str(ph)] = counts
        out["confirmatory_episodes_total"] += sum(counts.values())
        tdir = os.path.join(d, "transcripts")
        if os.path.isdir(tdir):
            for fn in os.listdir(tdir):
                if fn.endswith(".json") and any(fn.startswith(run4.safe_name(m) + "__") for m in BATCH_MODELS):
                    with open(os.path.join(tdir, fn)) as f:
                        tr = json.load(f)
                    key = "batch_models_batch_transcripts" if "execution" in tr.get("run_info", {}) else "batch_models_sync_transcripts"
                    out[key] += 1
                elif fn.endswith(".json") and fn.startswith(run4.safe_name(GEMINI) + "__"):
                    with open(os.path.join(tdir, fn)) as f:
                        tr = json.load(f)
                    key = "gemini_batch_transcripts" if "execution" in tr.get("run_info", {}) else "gemini_sync_transcripts"
                    out[key] += 1
    out["provider_failures"] = provider_failures(base, sub)
    out["notes"] = [
        "openrouter:openai/gpt-5.5-20260423 hit OpenRouter HTTP 429 rate limits in phase 1 ('new accounts are "
        "limited to 20 requests per minute'); the live run_full.sh stopped at 235/768 phase-1 GPT-5.5 episodes "
        "(phase 1: Qwen 768, Haiku 768; spend $24.32).",
        "run_rest.sh re-invokes the frozen run4.py with run_full.sh's arguments until every cell of a sync model is "
        "done (120-180 s between attempts; stops on the cost cap, a credit/key limit (402), or 10 attempts in a row "
        "without a finished episode). Rate-limited episodes are logged in failures.jsonl and retried, never dropped; "
        "analyze4 reports them as provider_failure_recovered.",
    ]
    out["spend_usd_all_logs"] = round(sum(M.SpendTracker(x).total for x in logs if os.path.exists(x)), 6)
    out["src4_batch_sha256"] = frozen.own_hashes()
    try:
        import anthropic  # noqa: PLC0415

        out["anthropic_sdk"] = anthropic.__version__
    except ImportError:
        out["anthropic_sdk"] = None
    return out


def provider_failures(base: str, sub: str = "") -> Dict[str, Any]:
    """Per phase and model: failures.jsonl lines, how many were rate limits (HTTP 429), and how many of the
    failed episodes have since completed (transcript present)."""
    out: Dict[str, Any] = {}
    for ph in (1, 2, 3):
        d = os.path.join(base, f"phase{ph}{sub}")
        p = os.path.join(d, "failures.jsonl")
        if not os.path.exists(p):
            continue
        per: Dict[str, Dict[str, Any]] = {}
        failed: Dict[str, set] = {}
        with open(p) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eid = e.get("episode_id", "")
                model = eid.split("__", 1)[0]
                r = per.setdefault(model, {"lines": 0, "rate_limited_429": 0})
                r["lines"] += 1
                err = str(e.get("error", ""))
                if "429" in err or "rate limit" in err.lower() or "requests per minute" in err.lower():
                    r["rate_limited_429"] += 1
                failed.setdefault(model, set()).add(eid)
        for model, ids in failed.items():
            per[model]["episodes"] = len(ids)
            per[model]["episodes_recovered"] = sum(
                1 for i in ids if os.path.exists(os.path.join(d, "transcripts", i + ".json")))
        out[str(ph)] = per
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", required=True)
    p.add_argument("--sub", default="")
    p.add_argument("--allow-existing-sync", action="store_true")
    p.add_argument("--record", action="store_true",
                   help="write batch_switch_facts.json if it does not exist (run_rest.sh: just before the first batch episode)")
    p.add_argument("--record-gemini", action="store_true",
                   help="write batch_switch_facts_gemini.json if it does not exist (just before the first Gemini batch run)")
    a = p.parse_args(argv)
    f = facts(a.base, a.sub)
    print(f"   confirmatory episodes so far: {f['confirmatory_episodes_total']}  "
          + "  ".join(f"phase{ph}: " + (", ".join(f"{m}={n}" for m, n in c.items()) or "-") for ph, c in f["phases"].items()))
    print(f"   Sonnet 5 / Fable 5 transcripts: sync {f['batch_models_sync_transcripts']}, batch {f['batch_models_batch_transcripts']}; "
          f"spend so far ${f['spend_usd_all_logs']:.4f}")
    for ph, per in f["provider_failures"].items():
        for model, r in per.items():
            print(f"   provider failures phase {ph} {model}: {r['lines']} lines ({r['rate_limited_429']} rate-limited), "
                  f"{r['episodes_recovered']}/{r['episodes']} failed episodes since completed")
    latest = os.path.join(a.base, "batch_switch_facts" + ("_dry" if a.sub else "") + "_latest.json")
    with open(latest, "w") as fh:
        json.dump(f, fh, indent=1, sort_keys=True)
    path = os.path.join(a.base, "batch_switch_facts" + ("_dry" if a.sub else "") + ".json")
    if a.record and not os.path.exists(path):
        with open(path, "w") as fh:
            json.dump(f, fh, indent=1, sort_keys=True)
        print(f"   recorded {path} (first start of batch execution)")
    gpath = os.path.join(a.base, "batch_switch_facts_gemini" + ("_dry" if a.sub else "") + ".json")
    print(f"   Gemini transcripts: sync {f['gemini_sync_transcripts']}, batch {f['gemini_batch_transcripts']}")
    if a.record_gemini and not os.path.exists(gpath):
        with open(gpath, "w") as fh:
            json.dump(f, fh, indent=1, sort_keys=True)
        print(f"   recorded {gpath} (first start of Gemini batch execution)")
    if f["batch_models_sync_transcripts"] and not a.allow_existing_sync:
        print("!! Sonnet 5 / Fable 5 episodes already exist from the sync runner; the deviation note assumes none. "
              "Rerun with --allow-existing-sync only after updating the note.")
        return 1
    if f["gemini_sync_transcripts"] and not a.allow_existing_sync:
        print("!! Gemini episodes already exist from the sync runner (OpenRouter); the Gemini deviation note assumes "
              "none and the model must not mix execution paths. Rerun with --allow-existing-sync only after updating it.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
