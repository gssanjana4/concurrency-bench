# Study 4: filing record

All times UTC, 16 November 2026.

1. The plan (`PREREGISTRATION_STUDY4.md`) and the frozen code were finished after two pre-spend reviews; the Freeze
   table in the plan lists `src7/FREEZE.md` (36 files) and 14 further files. A free dry run with fake models on the
   author's Mac, with the interpreter of the paid run, reproduced the frozen dry-run analysis outputs exactly (all 30
   tests, the descriptives and `numbers.tex`).
2. The plan was filed as an OSF registration from project 9qvpt with the OSF Preregistration template: every field
   holds the plan's text for that field; the title and description are the plan's. The frozen files were not uploaded
   to the project before the filing; they are bound by the sha256 values in the plan's
   Freeze table and released with the data.
3. 15:31:50: `date_registered` of the registration https://osf.io/6asc8 (embargo to 2027-11-01).
4. The OSF API reported `archiving` false within the first minute; the embargo was pending the author's approval.
   About 16:01 the author's approval was given (the approve link of OSF's "Pending Embargo" email).
5. 16:02:31: the registration record was read from the OSF API in the signed-in browser, as a sparse fieldset of
   `GET /v2/registrations/6asc8/` (title, archiving, withdrawn, pending approvals, date_registered, embargo end), and
   saved byte for byte as `.study4_osf_api.json` (sha256 `7eabf20a85ed0fb601edca963fe1ca213b4b1a95cdb4d23afacd217284dd6a59`):
   `archiving` false, `withdrawn` false, no pending approval. The plan says the gate reads "the OSF API record"; the
   saved file is that endpoint's response restricted to the fields the gate checks (the full record is 61 kB and
   holds the plan text). `.study4_registered` records the URL, `archiving: complete`, the hash, the time of the read
   and the request URL.
6. 16:03:19: the paid run started (`results7/study4/run_study4.log`): `src7/gate7.py` OK, freeze check (36 files OK),
   validity gate (280 rows, 0 failures), gate again, preflight (all four models; Qwen served by Alibaba), then both
   lanes.
