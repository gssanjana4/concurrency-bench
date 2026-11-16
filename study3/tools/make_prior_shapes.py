"""Build src6/prior_shapes.json: the numeric shapes of every Study 1 and Study 2 instance at n = 2 (read-only use of
the frozen src4/instances_full.json and src5/instances5.py; nothing there is written: bytecode is off).

    python3 -B tools/make_prior_shapes.py --repo /path/to/concurrency-bench --out src6/prior_shapes.json
"""
import argparse, json, os, sys

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(a.repo, "src5"))
os.environ["STUDY1_INSTANCES"] = os.path.join(a.repo, "src4", "instances_full.json")
import instances5 as I5  # noqa: E402

s1 = sorted(I5.study1_shapes())
s2 = sorted({I5.shape(I5.build(f, i, 2), f) for f in I5.CONTENDED for i in range(4)})
out = {"_README": "Numeric shapes (family, sorted initial values, sorted intent amounts) of the Study 1 instances "
                  "(src4/instances_full.json at n = 2 plus the pilot catalog) and of the Study 2 instances (src5 "
                  "instances5, i0 to i3, n = 2). Study 3 instances must avoid every one (src6/instances6.py).",
       "study1": s1, "study2": s2}
with open(a.out, "w") as f:
    json.dump(out, f, indent=1, sort_keys=True)
    f.write("\n")
print(f"study1 {len(s1)} shapes, study2 {len(s2)} shapes -> {a.out}")
