"""Write src6/study2_lock_schemas.json: the Study 2 tool schemas per config, as the frozen src5/world5.py builds them
(read-only import, no bytecode). tests6 checks that src6 builds the same bytes for none, cas_available,
locks_s2text (= Study 2 locks) and cas_available+locks+s2text (= Study 2 all_available).

    python3 -B tools/make_study2_fixtures.py --repo /path/to/concurrency-bench --out src6/study2_lock_schemas.json
"""
import argparse, json, os, sys

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(a.repo, "src5"))
import world5 as W5  # noqa: E402

out = {"_README": "Study 2 tool schemas (src5/world5.tool_schemas) per Study 2 config, and the Study 2 system prompt "
                  "of a sample agent; frozen fixture for tests6.",
       "schemas": {c: W5.tool_schemas(W5.CoordinationConfig.from_names(c)) for c in W5.STUDY2_CONFIGS},
       "prompt": W5.build_system_prompt("a0", ("a1",), "Sell 2 from inventory:x, only if enough remains.",
                                        W5.world_config("locks"))}
with open(a.out, "w") as f:
    json.dump(out, f, indent=1, sort_keys=True)
    f.write("\n")
print("wrote", a.out)
