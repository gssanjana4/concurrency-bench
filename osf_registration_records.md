# OSF registration records

Studies 1, 2 and 4 were registered on the OSF before their runs; Study 3's registration is retrospective (below). All four registrations are embargoed. This file lets a reader check the
timing claims of the paper against the shipped files without the embargo being lifted. Every value below is copied
from a record kept at the time (source named in each row); nothing here was read from the OSF after the fact, and
no OSF setting was changed to write it. Reviewers can be given a view-only link to the registrations on request.

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

## Study 3

Study 3's plan was time-stamped on the OSF before the run, but its first registration failed, so the registration
that exists is retrospective. The record below is complete, including the failure.

| field | value | source |
|---|---|---|
| plan files uploaded to the OSF project | project `9qvpt`, osfstorage: `PREREGISTRATION_STUDY3.md` 2026-11-15T05:52:58Z, `SHA256SUMS_STUDY3.txt` 05:52:59Z, `study3_frozen_code_and_plan.zip` 05:52:59Z; version 1 each, not modified since; the OSF-computed sha256 of each equals the shipped copy | OSF API (`/v2/nodes/9qvpt/files/osfstorage/`), read on 2026-11-16; copies in `study3/osf_upload/` |
| first registration | submitted about 2026-11-15T06:06Z from the same text; the OSF could not archive it ("errors copying files from some of the linked third-party services", email of 06:06:51Z) and removed it | OSF email "Problem Registering"; `/v2/registrations/h79j4/` returns 410 |
| paid run | started 2026-11-15T06:07:18Z (freeze check, validity gate, preflight, then both lanes); lanes ended 13:48:25Z | `data/results6/study3/run_study3.log` |
| why the run started | the run script refuses to spend without a local marker of the filing; the marker was written right after the filing was submitted, without waiting for the OSF to confirm the archive | `study3/STUDY3_FILING_RECORD.md` |
| analysis | the frozen `analysis6/analyze6.py` on 2026-11-15, about 16:00Z | `study3/analysis6/out_study3/` |
| failure noticed | 2026-11-16, about 01:00Z | `study3/STUDY3_FILING_RECORD.md` |
| registration id | `3pa4k` (https://osf.io/3pa4k), in OSF project `9qvpt` | OSF API |
| date_registered | 2026-11-16T01:07:17Z (retrospective: the form's answer on prior knowledge of the data is "Analyses in this plan have been conducted already") | OSF API |
| embargo end | 2027-11-01 | OSF API |
| registered text | the plan of 05:52:58Z with a filing note added at the top of the description and of the explanation of prior knowledge; nothing else changed | OSF draft `6af9480ae45abab9ff91489a` |
| plan text in the artifact | `preregistration/PREREGISTRATION_STUDY3.md` (also `study3/PREREGISTRATION_STUDY3.md`), sha256 `85c0fb965b1598db8594fcd6db16920b334f070f4b9683d41ae4b208bd422e50` | this artifact |
| frozen code named in the plan | `study3/src6/FREEZE.md` sha256 `7dc10fab662462e12815eb89d9c379ad10d126c79aae13da565bc657c7f3b912`; `study3/run_conc_study3.sh` sha256 `6c9a79126a0d974673883bc80ed06cea501df14bf5b4e77ba691f42932342fbe`; `study3/analysis6/analyze6.py` sha256 `55f05ef1898a99dd7aade70e2a6132635fce590f020b18ecf1cb910c040e71a6` | the plan's "Freeze" table |
| uploaded code archive | `study3/osf_upload/study3_frozen_code_and_plan.zip`, sha256 `7924a02bce7f1ed43bd0ad529624859751f4ccfc2f3916d76026fc70596371e4` | equals the OSF-computed sha256 |

## Study 4

Registered before any paid call; the run script refused to spend until the OSF reported the registration archived.

| field | value | source |
|---|---|---|
| registration id | `6asc8` (https://osf.io/6asc8), in OSF project `9qvpt`, OSF Preregistration template | OSF API |
| date_registered | 2026-11-16T15:31:50Z; archiving finished within a minute; the embargo was approved by the author at about 16:01Z | OSF API; OSF email "Pending Embargo" |
| record the gate checked | read 2026-11-16T16:02:31Z in the signed-in browser (the registration is embargoed): `archiving` false, `withdrawn` false, no pending approval; saved as `study4/.study4_osf_api.json`, sha256 `7eabf20a85ed0fb601edca963fe1ca213b4b1a95cdb4d23afacd217284dd6a59` | `study4/.study4_registered` |
| paid run | started 2026-11-16T16:03:19Z; Anthropic lane ended 21:36:21Z; OpenRouter lane stopped for good 21:46:57Z | `data/results7/study4/run_study4.log`, `study4/STUDY4_RUN_NOTES.md` |
| embargo end | 2027-11-01 | OSF API |
| registered text | every form field holds the plan's text for that field; the title and description are the plan's | OSF registration |
| plan text in the artifact | `preregistration/PREREGISTRATION_STUDY4.md` (also `study4/PREREGISTRATION_STUDY4.md`), sha256 `5dea5e38d5afd6ac18af9e717feb231eb68a4e29971739d2982f7a03ae0fe79a` | this artifact |
| frozen code named in the plan | `study4/src7/FREEZE.md` sha256 `a14bba8e0a99ce0918f1a56bbbae2cc926256dd25bd9b25ec7498f8987b0e00e`; `study4/analysis7/analyze7.py` sha256 `eec68bbac58a213230dab31efdbd83222b75d37c0aae499ac02a518b241168cc` (the plan's Freeze table lists 15 files) | the plan's "Freeze" table |
| frozen files on the OSF | not uploaded to the project; bound by the hashes in the registered Freeze table | `study4/STUDY4_FILING_RECORD.md` |

## How to check

- `sha256sum preregistration/PREREGISTRATION.md preregistration/PREREGISTRATION_STUDY2.md analysis5/out_study2/eligibility.json src5/FREEZE.md run_conc_study2.sh preregistration/PREREGISTRATION_STUDY3.md study3/src6/FREEZE.md study3/run_conc_study3.sh study3/analysis6/analyze6.py study3/osf_upload/study3_frozen_code_and_plan.zip preregistration/PREREGISTRATION_STUDY4.md study4/src7/FREEZE.md study4/analysis7/analyze7.py study4/.study4_osf_api.json`
  must print the values above.
- After the embargo ends (2027-11-01), or through a view-only link given on request, the OSF pages show
  `date_registered` and the registered text, and the project's file list shows the eligibility file's upload time
  and the OSF-computed sha256.
- The review build of this artifact replaces the OSF identifiers with a redaction token; the dates, times and hashes
  are unchanged.
