# Study 3 filing record

Times are UTC. This file replaces the run-machine marker `.study3_registered` (not shipped), which recorded the same
facts at the time and was corrected on 2026-11-16.

1. 2026-11-15 05:52:58Z to 05:52:59Z: `PREREGISTRATION_STUDY3.md` (sha256 `85c0fb965b1598db8594fcd6db16920b334f070f4b9683d41ae4b208bd422e50`),
   `SHA256SUMS_STUDY3.txt` and `study3_frozen_code_and_plan.zip` (sha256 `7924a02bce7f1ed43bd0ad529624859751f4ccfc2f3916d76026fc70596371e4`)
   uploaded to OSF project `9qvpt`. Copies: `osf_upload/`.
2. About 06:06Z: the registration was submitted from the same text, with an embargo to 2027-11-01.
3. 06:06:51Z: the OSF reported that it could not archive the registration and removed it (email "Problem Registering").
4. 06:07:14Z: the local marker that `run_conc_study3.sh` requires was written, on the assumption that the filing had
   succeeded; the OSF's confirmation was not checked.
5. 06:07:18Z: the paid run started (`../data/results6/study3/run_study3.log`): freeze check (32 files OK), validity gate
   (432 rows, 0 failures), preflight, then both lanes. It ended at 13:48:25Z with 2,688 episodes and no failure.
6. About 16:00Z: the registered analysis (`analysis6/analyze6.py`, frozen) wrote `analysis6/out_study3/`.
7. 2026-11-16, about 01:00Z: the failure was noticed (the registration's page and API answered "deleted").
8. 01:07:17Z on 2026-11-16 is the `date_registered` of the re-filed registration `3pa4k` (https://osf.io/3pa4k): the same
   draft with a filing note at the top of the description and of the explanation of prior knowledge, and the
   prior-knowledge answer "Analyses in this plan have been conducted already ... retrospective registration".
   Embargo to 2027-11-01. Its archiving completed (API: `archiving` false).

What rests on the time stamp before the run is the plan text and the frozen code (items 1 and 5), not an OSF
registration. The paper calls the Study 3 tests pre-specified and reports the registration as retrospective.

**Departure found later (2026-11-16).** The plan names the instance seed space `src6-study3-v1`; the frozen code
(`src6/instances6.py`, `SPACE`) drew the instances from `src6-study2-v1`. Every draw was still checked to differ from
all Study 1 and Study 2 instances and from the other Study 3 instances of its family, as planned. The key only selects
which random draws are made; no test is affected. The paper lists it in its table of Study 3 departures.
