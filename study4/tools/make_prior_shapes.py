"""Build src7/prior_shapes.json: the numeric shapes of every Study 1 and Study 2 instance at n = 2 (read-only use of
the frozen src4/instances_full.json and src5/instances5.py; nothing there is written: bytecode is off), and, for
Study 4, of every Study 3 instance (study3/src6/instances6.py, i0 to i7, n = 2, the eight contended families).

    python3 -B tools/make_prior_shapes.py --repo /path/to/concurrency-bench --out src7/prior_shapes.json
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
sys.path.insert(0, os.path.join(a.repo, "study3", "src6"))
import instances6 as I6  # noqa: E402
s3 = set()
for f in I6.CONTENDED:
    fam = I6.family_of(f)
    if fam in getattr(I6, "NAME_ONLY_FAMILIES", ()):
        continue
    for i in range(8):
        s3.add(I6.shape(I6.build(f, i, 2), f).replace(f'"{fam}"', f'"{I6._family_key(fam)}"', 1))
s3 = sorted(s3)
out = {"_README": "Numeric shapes (family, sorted initial values, sorted intent amounts) of the Study 1 instances "
                  "(src4/instances_full.json at n = 2 plus the pilot catalog) and of the Study 2 instances (src5 "
                  "instances5, i0 to i3, n = 2). and of the Study 3 instances (study3/src6 instances6, i0 to i7, n = 2; claim families without numbers left "
                  "out). Study 4 instances must avoid every one (src7/instances7.py).",
       "study1": s1, "study2": s2, "study3": s3}
with open(a.out, "w") as f:
    json.dump(out, f, indent=1, sort_keys=True)
    f.write("\n")
print(f"study1 {len(s1)}, study2 {len(s2)}, study3 {len(s3)} shapes -> {a.out}")
