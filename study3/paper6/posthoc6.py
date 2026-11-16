#!/usr/bin/env python3
"""posthoc6.py: exploratory transcript counts for the paper (not registered, no test; reads only, writes
paper6/posthoc6.json). Per model x config x start x arm (lock configs): agents, agents shown a reported wait,
agents shown a locked read. Per model: completions, served model or host, effective temperature values.

    python3 paper6/posthoc6.py
"""
import collections
import glob
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "..", "results6", "study3")


def short(model):
    return "Qwen" if "qwen" in model else model.split("-")[1].capitalize()


def main():
    files = sorted(glob.glob(os.path.join(BASE, "n2-*", "transcripts", "*.json")))
    lock = collections.Counter()
    served = collections.Counter()
    temp = collections.Counter()
    for p in files:
        d = json.load(open(p))
        m = short(d["model"])
        arm = "control" if "_ctrl@" in os.path.basename(p) else "contended"
        for a in d["agents"].values():
            for tu in a.get("turns") or []:
                served[f"{m}|{tu.get('model_served')}"] += 1
                temp[f"{m}|{tu.get('temperature_effective')}"] += 1
        if d["config"] in ("locks", "all_available", "locks_s2text"):
            for s in d["score"]["agents"].values():
                k = f"{m}|{d['config']}|{d['start_mode']}|{arm}"
                lock[k + "|agents"] += 1
                lock[k + "|waits"] += int(s.get("lock_waits_reported") or 0) > 0
                lock[k + "|locked_reads"] += int(s.get("locked_reads") or 0) > 0
    h = hashlib.sha256("\n".join(os.path.basename(p) for p in files).encode()).hexdigest()
    out = {"n_files": len(files), "file_list_sha256": h, "lock_bundle": dict(sorted(lock.items())),
           "served": dict(sorted(served.items())), "temperature_effective": dict(sorted(temp.items()))}
    json.dump(out, open(os.path.join(HERE, "posthoc6.json"), "w"), indent=1, sort_keys=True)
    print(f"posthoc6: {len(files)} transcripts; wrote paper6/posthoc6.json")


if __name__ == "__main__":
    main()
