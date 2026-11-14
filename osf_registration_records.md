# OSF registration records

Both studies were registered on the OSF and both registrations are embargoed. This file lets a reader check the
timing claims of the paper against the shipped files without the embargo being lifted. Every value below is copied
from a record kept at the time (source named in each row); nothing here was read from the OSF after the fact, and
no OSF setting was changed to write it. Reviewers can be given a view-only link to both registrations on request.

Times are UTC. "In the artifact" paths are relative to the top of this artifact.

## Study 1

| field | value | source |
|---|---|---|
| registration id | `a5vec` (https://osf.io/a5vec) | `release/ARR_STEPS.md` section 5; `make_artifact_v2.py` (`OSF1`) |
| date_registered | 2026-10-31 (the time of day was not written into any log of this project; the OSF registration page shows it) | `PREREGISTRATION.md` title line; `release/ARR_STEPS.md` section 5 |
| embargo end | 2027-11-01 | `release/ARR_STEPS.md` section 5 |
| registered text in the artifact | `preregistration/PREREGISTRATION.md` (also `paper/PREREGISTRATION.md`, the copy the pipeline reads) | this artifact |
| sha256 of that text | `97239ad06daa93ab59818ba4cd4e871ee8197c03b2f42132a3faa3e6fc6292f1` | computed on the shipped copy on 2026-11-14; no hash of the Study 1 text was recorded at filing, so this value identifies the shipped copy, not the OSF record |
| frozen code named in the text | the "Freeze" table of the text lists the sha256 of every frozen `src4` file (identical to `src4/FREEZE.md`) | `preregistration/PREREGISTRATION.md`, "Freeze" |
| first paid run | started 2026-10-31T23:13:01Z (16:13:01 PDT) | `results4/full/run.log` of the Study 1 run, first line (shipped under `data/results4/full/` only in a build that includes the Study 1 run outputs) |
| eligibility file | none (Study 1 had no eligibility step) | |

## Study 2

| field | value | source |
|---|---|---|
| registration id | `zj3an` (https://osf.io/zj3an), in OSF project `9qvpt` | `STUDY2_RUN_LOG.md` title line; `.study2_registered` |
| date_registered | 2026-11-09T18:35:24Z | `STUDY2_RUN_LOG.md` title line; `.study2_registered` (written after the Register click, before any paid call) |
| embargo end | 2027-11-01 | `.study2_registered` |
| registered text in the artifact | `preregistration/PREREGISTRATION_STUDY2.md` | this artifact |
| sha256 of that text | `8193e9602f0c1257e1ec69d890f15ab4e63c084fa0da77d1eae416c16fd23ee5` | the registered value that `make_artifact_v2.py` checks at build time (`EXPECTED`); `README.md` of this artifact |
| frozen code named in the text | `src5/FREEZE.md` sha256 `e5834fb5b81565158493acda36b3fb5d32e2455a3504a86ffac646ba09681c6f`; `run_conc_study2.sh` sha256 `76bcfa3f6e2c518ba0dafa50f702f68512490a9eee37f5c24bd0fe6443f9ead9` | `.study2_registered`; the "Freeze" table of the text |
| paid run start | 2026-11-09T18:36Z (10:36 PST, queued job 004); lanes started 18:40Z | `STUDY2_RUN_LOG.md`, 2026-11-09 |
| eligibility file computed | 2026-11-09T22:22Z, from the probe transcripts only, by the frozen `analysis5/analyze5.py eligibility` | `STUDY2_RUN_LOG.md`, "ELIGIBILITY STEP" |
| eligibility file OSF upload | posted to project `9qvpt` as `eligibility_study2.json`, version 1, modified 2026-11-09T23:08:01Z; the OSF-computed sha256 equals the file's | `STUDY2_RUN_LOG.md`, "ELIGIBILITY STEP" |
| eligibility file in the artifact | `analysis5/out_study2/eligibility.json`, sha256 `f4ad4f072fffc0e3a703ab708d61b5371e72f5481cb6f13a639f1598b228341d` | `STUDY2_RUN_LOG.md`; checked at build time by `make_artifact_v2.py` |

## How to check

- `sha256sum preregistration/PREREGISTRATION.md preregistration/PREREGISTRATION_STUDY2.md analysis5/out_study2/eligibility.json src5/FREEZE.md run_conc_study2.sh`
  must print the values above.
- After the embargo ends (2027-11-01), or through a view-only link given on request, the OSF pages show
  `date_registered` and the registered text, and the project's file list shows the eligibility file's upload time
  and the OSF-computed sha256.
- The review build of this artifact replaces the OSF identifiers with a redaction token; the dates, times and hashes
  are unchanged.
