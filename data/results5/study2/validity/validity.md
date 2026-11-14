# Reference policy validity table (4 instances x 8 schedules per cell)

Lock columns (contended): attempted / granted share of agents, effective share of the agents that were granted a lock and committed a write; fenced writes with a stale basis; lock waits (423 after the full wait); deadlock episodes. Exposure (Round 3): share of agents with a peer-caused contention signal, contended / control (the control must be 0); cap-truncated failed episodes (contended).

| n | family | policy | role | config | contended outcomes | control | fulfilled (cont.) | max calls / cap | lock att/gr/eff | stale-basis fenced | waits (423) | deadlocks | exposure c/k | cap-trunc | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | inventory_last_unit | naive | naive | none | clean 8, failed 24 (lost_update 24) | clean 32 | 0.88 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.12/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | cas_available | clean 8, failed 24 (lost_update 24) | clean 32 | 0.88 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | locks | clean 8, failed 24 (lost_update 24) | clean 32 | 0.88 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.12/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | all_available | clean 8, failed 24 (lost_update 24) | clean 32 | 0.88 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | none | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | cas_available | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | locks | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | all_available | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | cas_retry | correct | cas_available | clean 32 | clean 32 | 0.50 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | cas_retry | correct | all_available | clean 32 | clean 32 | 0.50 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | locks | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | all_available | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 5 / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.95/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 5 / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.95/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 4 / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 4 / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 28 | 1.00/1.00/0.00 | 64 | 73 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 28 | 1.00/1.00/0.00 | 64 | 73 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | locks | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.53/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | all_available | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.53/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | locks | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | none | clean 5, failed 27 (lost_update 27) | clean 32 | 1.00 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.08/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | cas_available | clean 5, failed 27 (lost_update 27) | clean 32 | 1.00 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | locks | clean 5, failed 27 (lost_update 27) | clean 32 | 1.00 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.08/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | all_available | clean 5, failed 27 (lost_update 27) | clean 32 | 1.00 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | none | clean 13, failed 19 (lost_update 19) | clean 32 | 1.00 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | cas_available | clean 13, failed 19 (lost_update 19) | clean 32 | 1.00 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | locks | clean 13, failed 19 (lost_update 19) | clean 32 | 1.00 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | all_available | clean 13, failed 19 (lost_update 19) | clean 32 | 1.00 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | cas_retry | correct | cas_available | clean 32 | clean 32 | 1.00 | 4 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | cas_retry | correct | all_available | clean 32 | clean 32 | 1.00 | 4 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | locks | clean 32 | clean 32 | 1.00 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | all_available | clean 32 | clean 32 | 1.00 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 5 / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 5 / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 4 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 4 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 28 | 1.00/1.00/0.00 | 64 | 73 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 28 | 1.00/1.00/0.00 | 64 | 73 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | locks | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | all_available | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.58/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | locks | clean 32 | clean 32 | 1.00 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | all_available | clean 32 | clean 32 | 1.00 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | none | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | cas_available | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | locks | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | all_available | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | none | clean 14, failed 18 (lost_update 18) | clean 32 | 0.78 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | cas_available | clean 14, failed 18 (lost_update 18) | clean 32 | 0.78 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | locks | clean 14, failed 18 (lost_update 18) | clean 32 | 0.78 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | all_available | clean 14, failed 18 (lost_update 18) | clean 32 | 0.78 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_retry | correct | cas_available | clean 32 | clean 32 | 0.50 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_retry | correct | all_available | clean 32 | clean 32 | 0.50 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | locks | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | all_available | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 5 / 28 | 1.00/1.00/n/a | 0 | 29 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 5 / 28 | 1.00/1.00/n/a | 0 | 29 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 4 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 4 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | none | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | cas_available | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | locks | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | all_available | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_claim | correct | cas_available | clean 32 | clean 32 | 0.50 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_claim | correct | all_available | clean 32 | clean 32 | 0.50 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | locks | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 / 28 | 1.00/1.00/0.00 | 0 | 29 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | all_available | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 / 28 | 1.00/1.00/0.00 | 0 | 29 (0) | 0 | 0.58/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | locks | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | none | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | cas_available | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | locks | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | all_available | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | none | clean 15, failed 17 (lost_update 17) | clean 32 | 0.77 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | cas_available | clean 15, failed 17 (lost_update 17) | clean 32 | 0.77 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | locks | clean 15, failed 17 (lost_update 17) | clean 32 | 0.77 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | all_available | clean 15, failed 17 (lost_update 17) | clean 32 | 0.77 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_retry | correct | cas_available | clean 32 | clean 32 | 0.50 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_retry | correct | all_available | clean 32 | clean 32 | 0.50 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | locks | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | all_available | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 5 / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 5 / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 4 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 4 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | none | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | cas_available | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | locks | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | all_available | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_claim | correct | cas_available | clean 32 | clean 32 | 0.50 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_claim | correct | all_available | clean 32 | clean 32 | 0.50 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 28 | 1.00/1.00/0.00 | 64 | 66 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 28 | 1.00/1.00/0.00 | 64 | 66 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | locks | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.53/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | all_available | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | locks | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.50 | 4 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | none | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 4 / 24 | - | 0 | 0 (0) | 0 | 0.02/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | cas_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 4 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | locks | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 4 / 28 | - | 0 | 0 (0) | 0 | 0.02/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | all_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 4 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | none | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 6 / 24 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | cas_available | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 6 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | locks | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 6 / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | all_available | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 6 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | cas_retry | correct | cas_available | clean 32 | clean 32 | 0.50 | 5 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | cas_retry | correct | all_available | clean 32 | clean 32 | 0.50 | 5 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | locks | clean 32 | clean 32 | 0.50 | 8 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | all_available | clean 32 | clean 32 | 0.50 | 8 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 8 / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 8 / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 7 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 7 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 / 28 | 1.00/1.00/0.00 | 128 | 60 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 / 28 | 1.00/1.00/0.00 | 128 | 60 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | locks | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 10 / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.52/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | all_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 10 / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.58/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | locks | clean 32 | clean 32 | 0.50 | 8 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.50 | 8 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | none | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 4 / 24 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | cas_available | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 4 / 24 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | locks | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 4 / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | all_available | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 4 / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | none | clean 21, failed 11 (write_skew 11) | clean 32 | 0.67 | 7 / 24 | - | 0 | 0 (0) | 0 | 0.33/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | cas_available | clean 21, failed 11 (write_skew 11) | clean 32 | 0.67 | 7 / 24 | - | 0 | 0 (0) | 0 | 0.33/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | locks | clean 21, failed 11 (write_skew 11) | clean 32 | 0.67 | 7 / 28 | - | 0 | 0 (0) | 0 | 0.33/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | all_available | clean 21, failed 11 (write_skew 11) | clean 32 | 0.67 | 7 / 28 | - | 0 | 0 (0) | 0 | 0.33/0.00 | 0 | yes |
| 2 | budget_write_skew | cas_retry | naive | cas_available | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 4 / 24 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | budget_write_skew | cas_retry | naive | all_available | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 4 / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_before_write | correct | cas_available | clean 32 | clean 32 | 0.50 | 13 / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_before_write | correct | all_available | clean 32 | clean 32 | 0.50 | 13 / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_after_write | naive | cas_available | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 6 / 24 | - | 0 | 0 (0) | 0 | 0.80/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_after_write | naive | all_available | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 6 / 28 | - | 0 | 0 (0) | 0 | 0.80/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | none | clean 13, compensated 19 | clean 32 | 0.50 | 18 / 24 | - | 0 | 0 (0) | 0 | 0.80/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | cas_available | clean 13, compensated 19 | clean 32 | 0.50 | 18 / 24 | - | 0 | 0 (0) | 0 | 0.80/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | locks | clean 13, compensated 19 | clean 32 | 0.50 | 18 / 28 | - | 0 | 0 (0) | 0 | 0.80/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | all_available | clean 13, compensated 19 | clean 32 | 0.50 | 18 / 28 | - | 0 | 0 (0) | 0 | 0.80/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | locks | clean 32 | clean 32 | 0.50 | 10 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | all_available | clean 32 | clean 32 | 0.50 | 10 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | locks | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 6 / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | all_available | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 6 / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 11 / 28 | 1.00/1.00/n/a | 0 | 54 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 11 / 28 | 1.00/1.00/n/a | 0 | 54 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 10 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 10 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | locks | failed 32 (write_skew 32) | clean 32 | 1.00 | 15 / 28 | 1.00/1.00/0.00 | 64 | 84 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | all_available | failed 32 (write_skew 32) | clean 32 | 1.00 | 15 / 28 | 1.00/1.00/0.00 | 64 | 84 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | locks | clean 2, failed 30 (write_skew 30) | clean 32 | 0.97 | 11 / 28 | 1.00/1.00/0.00 | 0 | 54 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | all_available | clean 2, failed 30 (write_skew 30) | clean 32 | 0.97 | 11 / 28 | 1.00/1.00/0.00 | 0 | 54 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | locks | clean 32 | clean 32 | 0.02 | 13 / 28 | 1.00/1.00/1.00 | 0 | 254 (229) | 31 | 0.98/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.02 | 13 / 28 | 1.00/1.00/1.00 | 0 | 254 (229) | 31 | 0.98/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | none | clean 10, failed 22 (write_skew 22) | clean 32 | 0.84 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | cas_available | clean 10, failed 22 (write_skew 22) | clean 32 | 0.84 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | locks | clean 10, failed 22 (write_skew 22) | clean 32 | 0.84 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | all_available | clean 10, failed 22 (write_skew 22) | clean 32 | 0.84 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | none | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 5 / 24 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | cas_available | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 5 / 24 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | locks | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 5 / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | all_available | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 5 / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | joint_account_write_skew | cas_retry | naive | cas_available | clean 10, failed 22 (write_skew 22) | clean 32 | 0.84 | 3 / 24 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | joint_account_write_skew | cas_retry | naive | all_available | clean 10, failed 22 (write_skew 22) | clean 32 | 0.84 | 3 / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_before_write | correct | cas_available | clean 32 | clean 32 | 0.50 | 13 / 24 | - | 0 | 0 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_before_write | correct | all_available | clean 32 | clean 32 | 0.50 | 13 / 28 | - | 0 | 0 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_after_write | naive | cas_available | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 10 / 24 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_after_write | naive | all_available | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 10 / 28 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | none | clean 10, compensated 22 | clean 32 | 0.50 | 15 / 24 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | cas_available | clean 10, compensated 22 | clean 32 | 0.50 | 15 / 24 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | locks | clean 10, compensated 22 | clean 32 | 0.50 | 15 / 28 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | all_available | clean 10, compensated 22 | clean 32 | 0.50 | 15 / 28 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | locks | clean 32 | clean 32 | 0.50 | 7 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | all_available | clean 32 | clean 32 | 0.50 | 7 / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | locks | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 5 / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | all_available | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 5 / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 8 / 28 | 1.00/1.00/n/a | 0 | 46 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 8 / 28 | 1.00/1.00/n/a | 0 | 46 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 7 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 7 / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | locks | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 / 28 | 1.00/1.00/0.00 | 64 | 78 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | all_available | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 / 28 | 1.00/1.00/0.00 | 64 | 78 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | locks | failed 32 (write_skew 32) | clean 32 | 1.00 | 9 / 28 | 1.00/1.00/0.00 | 0 | 46 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | all_available | failed 32 (write_skew 32) | clean 32 | 1.00 | 9 / 28 | 1.00/1.00/0.00 | 0 | 46 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | locks | clean 32 | clean 32 | 0.31 | 10 / 28 | 1.00/1.00/1.00 | 0 | 203 (180) | 24 | 0.88/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.31 | 10 / 28 | 1.00/1.00/1.00 | 0 | 203 (180) | 24 | 0.88/0.00 | 0 | yes |
| 4 | inventory_last_unit | naive | naive | none | clean 4, failed 28 (lost_update 28) | clean 32 | 0.65 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | inventory_last_unit | naive | naive | cas_available | clean 4, failed 28 (lost_update 28) | clean 32 | 0.65 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | naive | naive | locks | clean 4, failed 28 (lost_update 28) | clean 32 | 0.65 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | inventory_last_unit | naive | naive | all_available | clean 4, failed 28 (lost_update 28) | clean 32 | 0.65 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | rereader | naive | none | clean 7, failed 25 (lost_update 25) | clean 32 | 0.62 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.38/0.00 | 0 | yes |
| 4 | inventory_last_unit | rereader | naive | cas_available | clean 7, failed 25 (lost_update 25) | clean 32 | 0.62 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | rereader | naive | locks | clean 7, failed 25 (lost_update 25) | clean 32 | 0.62 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.38/0.00 | 0 | yes |
| 4 | inventory_last_unit | rereader | naive | all_available | clean 7, failed 25 (lost_update 25) | clean 32 | 0.62 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | cas_retry | correct | cas_available | clean 32 | clean 32 | 0.25 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | cas_retry | correct | all_available | clean 32 | clean 32 | 0.25 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | lock_protected | correct | locks | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | lock_protected | correct | all_available | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 5 / 44 | 1.00/1.00/n/a | 0 | 95 (0) | 0 | 0.99/0.00 | 0 | yes |
| 4 | inventory_last_unit | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 5 / 44 | 1.00/1.00/n/a | 0 | 95 (0) | 0 | 0.99/0.00 | 0 | yes |
| 4 | inventory_last_unit | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 4 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 4 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 0.84 | 7 / 44 | 1.00/1.00/0.00 | 108 | 198 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | inventory_last_unit | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 0.84 | 7 / 44 | 1.00/1.00/0.00 | 108 | 198 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | inventory_last_unit | lease_then_tokenless | naive | locks | clean 2, failed 30 (lost_update 30) | clean 32 | 0.65 | 7 / 44 | 1.00/1.00/0.00 | 0 | 95 (0) | 0 | 0.96/0.00 | 0 | yes |
| 4 | inventory_last_unit | lease_then_tokenless | naive | all_available | clean 2, failed 30 (lost_update 30) | clean 32 | 0.65 | 7 / 44 | 1.00/1.00/0.00 | 0 | 95 (0) | 0 | 0.96/0.00 | 0 | yes |
| 4 | inventory_last_unit | lock_own_first | probe | locks | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_last_unit | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | naive | naive | none | failed 32 (lost_update 32) | clean 32 | 1.00 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | inventory_still_valid | naive | naive | cas_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | naive | naive | locks | failed 32 (lost_update 32) | clean 32 | 1.00 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | inventory_still_valid | naive | naive | all_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | rereader | naive | none | failed 32 (lost_update 32) | clean 32 | 1.00 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | inventory_still_valid | rereader | naive | cas_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | rereader | naive | locks | failed 32 (lost_update 32) | clean 32 | 1.00 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | inventory_still_valid | rereader | naive | all_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | cas_retry | correct | cas_available | clean 32 | clean 32 | 1.00 | 8 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | cas_retry | correct | all_available | clean 32 | clean 32 | 1.00 | 8 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | lock_protected | correct | locks | clean 32 | clean 32 | 1.00 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | lock_protected | correct | all_available | clean 32 | clean 32 | 1.00 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 5 / 44 | 1.00/1.00/n/a | 0 | 93 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | inventory_still_valid | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 5 / 44 | 1.00/1.00/n/a | 0 | 93 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | inventory_still_valid | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 4 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 4 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 44 | 1.00/1.00/0.00 | 128 | 196 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | inventory_still_valid | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 / 44 | 1.00/1.00/0.00 | 128 | 196 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | inventory_still_valid | lease_then_tokenless | naive | locks | clean 1, failed 31 (lost_update 31) | clean 32 | 0.64 | 7 / 44 | 1.00/1.00/0.00 | 0 | 93 (0) | 0 | 0.96/0.00 | 0 | yes |
| 4 | inventory_still_valid | lease_then_tokenless | naive | all_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.64 | 7 / 44 | 1.00/1.00/0.00 | 0 | 93 (0) | 0 | 0.98/0.00 | 0 | yes |
| 4 | inventory_still_valid | lock_own_first | probe | locks | clean 32 | clean 32 | 1.00 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | inventory_still_valid | lock_own_first | probe | all_available | clean 32 | clean 32 | 1.00 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | naive | naive | none | clean 9, failed 23 (lost_update 23) | clean 32 | 0.58 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.42/0.00 | 0 | yes |
| 4 | seat_same | naive | naive | cas_available | clean 9, failed 23 (lost_update 23) | clean 32 | 0.58 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | naive | naive | locks | clean 9, failed 23 (lost_update 23) | clean 32 | 0.58 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.42/0.00 | 0 | yes |
| 4 | seat_same | naive | naive | all_available | clean 9, failed 23 (lost_update 23) | clean 32 | 0.58 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | rereader | naive | none | clean 10, failed 22 (lost_update 22) | clean 32 | 0.55 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.45/0.00 | 0 | yes |
| 4 | seat_same | rereader | naive | cas_available | clean 10, failed 22 (lost_update 22) | clean 32 | 0.55 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | rereader | naive | locks | clean 10, failed 22 (lost_update 22) | clean 32 | 0.55 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.45/0.00 | 0 | yes |
| 4 | seat_same | rereader | naive | all_available | clean 10, failed 22 (lost_update 22) | clean 32 | 0.55 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | cas_retry | correct | cas_available | clean 32 | clean 32 | 0.25 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | cas_retry | correct | all_available | clean 32 | clean 32 | 0.25 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | lock_protected | correct | locks | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | lock_protected | correct | all_available | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 5 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.99/0.00 | 0 | yes |
| 4 | seat_same | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 5 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.99/0.00 | 0 | yes |
| 4 | seat_same | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 4 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 4 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | naive_claim | naive | none | clean 9, failed 23 (lost_update 23) | clean 32 | 0.58 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.42/0.00 | 0 | yes |
| 4 | seat_same | naive_claim | naive | cas_available | clean 9, failed 23 (lost_update 23) | clean 32 | 0.58 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | naive_claim | naive | locks | clean 9, failed 23 (lost_update 23) | clean 32 | 0.58 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.42/0.00 | 0 | yes |
| 4 | seat_same | naive_claim | naive | all_available | clean 9, failed 23 (lost_update 23) | clean 32 | 0.58 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | cas_claim | correct | cas_available | clean 32 | clean 32 | 0.25 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | cas_claim | correct | all_available | clean 32 | clean 32 | 0.25 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 0.76 | 7 / 44 | 1.00/1.00/0.00 | 97 | 189 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | seat_same | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 0.76 | 7 / 44 | 1.00/1.00/0.00 | 97 | 189 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | seat_same | lease_then_tokenless | naive | locks | clean 3, failed 29 (lost_update 29) | clean 32 | 0.58 | 7 / 44 | 1.00/1.00/0.00 | 0 | 96 (0) | 0 | 0.98/0.00 | 0 | yes |
| 4 | seat_same | lease_then_tokenless | naive | all_available | clean 3, failed 29 (lost_update 29) | clean 32 | 0.58 | 7 / 44 | 1.00/1.00/0.00 | 0 | 96 (0) | 0 | 0.98/0.00 | 0 | yes |
| 4 | seat_same | lock_own_first | probe | locks | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | seat_same | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | naive | naive | none | clean 1, failed 31 (lost_update 31) | clean 32 | 0.75 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 4 | ticket_same | naive | naive | cas_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.75 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | naive | naive | locks | clean 1, failed 31 (lost_update 31) | clean 32 | 0.75 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 4 | ticket_same | naive | naive | all_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.75 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | rereader | naive | none | clean 5, failed 27 (lost_update 27) | clean 32 | 0.64 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.36/0.00 | 0 | yes |
| 4 | ticket_same | rereader | naive | cas_available | clean 5, failed 27 (lost_update 27) | clean 32 | 0.64 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | rereader | naive | locks | clean 5, failed 27 (lost_update 27) | clean 32 | 0.64 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.36/0.00 | 0 | yes |
| 4 | ticket_same | rereader | naive | all_available | clean 5, failed 27 (lost_update 27) | clean 32 | 0.64 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | cas_retry | correct | cas_available | clean 32 | clean 32 | 0.25 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | cas_retry | correct | all_available | clean 32 | clean 32 | 0.25 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | lock_protected | correct | locks | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | lock_protected | correct | all_available | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 5 / 44 | 1.00/1.00/n/a | 0 | 95 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | ticket_same | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 5 / 44 | 1.00/1.00/n/a | 0 | 95 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | ticket_same | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 4 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 4 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | naive_claim | naive | none | clean 1, failed 31 (lost_update 31) | clean 32 | 0.75 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 4 | ticket_same | naive_claim | naive | cas_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.75 | 2 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | naive_claim | naive | locks | clean 1, failed 31 (lost_update 31) | clean 32 | 0.75 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 4 | ticket_same | naive_claim | naive | all_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.75 | 2 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | cas_claim | correct | cas_available | clean 32 | clean 32 | 0.25 | 3 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | cas_claim | correct | all_available | clean 32 | clean 32 | 0.25 | 3 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 0.80 | 7 / 44 | 1.00/1.00/0.00 | 102 | 193 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | ticket_same | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 0.80 | 7 / 44 | 1.00/1.00/0.00 | 102 | 193 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | ticket_same | lease_then_tokenless | naive | locks | clean 1, failed 31 (lost_update 31) | clean 32 | 0.62 | 7 / 44 | 1.00/1.00/0.00 | 0 | 95 (0) | 0 | 0.99/0.00 | 0 | yes |
| 4 | ticket_same | lease_then_tokenless | naive | all_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.62 | 7 / 44 | 1.00/1.00/0.00 | 0 | 95 (0) | 0 | 0.99/0.00 | 0 | yes |
| 4 | ticket_same | lock_own_first | probe | locks | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | ticket_same | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.25 | 4 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | naive | naive | none | clean 1, failed 31 (lost_update 31) | clean 32 | 0.90 | 4 / 40 | - | 0 | 0 (0) | 0 | 0.10/0.00 | 0 | yes |
| 4 | transfer_shared_source | naive | naive | cas_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.90 | 4 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | naive | naive | locks | clean 1, failed 31 (lost_update 31) | clean 32 | 0.90 | 4 / 44 | - | 0 | 0 (0) | 0 | 0.10/0.00 | 0 | yes |
| 4 | transfer_shared_source | naive | naive | all_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.90 | 4 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | rereader | naive | none | clean 2, failed 30 (lost_update 30) | clean 32 | 0.77 | 6 / 40 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 4 | transfer_shared_source | rereader | naive | cas_available | clean 2, failed 30 (lost_update 30) | clean 32 | 0.77 | 6 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | rereader | naive | locks | clean 2, failed 30 (lost_update 30) | clean 32 | 0.77 | 6 / 44 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 4 | transfer_shared_source | rereader | naive | all_available | clean 2, failed 30 (lost_update 30) | clean 32 | 0.77 | 6 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | cas_retry | correct | cas_available | clean 32 | clean 32 | 0.25 | 5 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | cas_retry | correct | all_available | clean 32 | clean 32 | 0.25 | 5 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | lock_protected | correct | locks | clean 32 | clean 32 | 0.25 | 8 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | lock_protected | correct | all_available | clean 32 | clean 32 | 0.25 | 8 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 8 / 44 | 1.00/1.00/n/a | 0 | 94 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | transfer_shared_source | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 8 / 44 | 1.00/1.00/n/a | 0 | 94 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | transfer_shared_source | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 7 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 7 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | reacquire_no_reread | naive | locks | failed 32 (lost_update 32) | clean 32 | 0.89 | 12 / 44 | 1.00/1.00/0.00 | 228 | 203 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | transfer_shared_source | reacquire_no_reread | naive | all_available | failed 32 (lost_update 32) | clean 32 | 0.89 | 12 / 44 | 1.00/1.00/0.00 | 228 | 203 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | transfer_shared_source | lease_then_tokenless | naive | locks | clean 1, failed 31 (lost_update 31) | clean 32 | 0.78 | 10 / 44 | 1.00/1.00/0.00 | 0 | 94 (0) | 0 | 0.89/0.00 | 0 | yes |
| 4 | transfer_shared_source | lease_then_tokenless | naive | all_available | clean 1, failed 31 (lost_update 31) | clean 32 | 0.78 | 10 / 44 | 1.00/1.00/0.00 | 0 | 94 (0) | 0 | 0.90/0.00 | 0 | yes |
| 4 | transfer_shared_source | lock_own_first | probe | locks | clean 32 | clean 32 | 0.25 | 8 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | transfer_shared_source | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.25 | 8 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | budget_write_skew | naive | naive | none | clean 6, failed 26 (write_skew 26) | clean 32 | 0.65 | 6 / 40 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | budget_write_skew | naive | naive | cas_available | clean 6, failed 26 (write_skew 26) | clean 32 | 0.65 | 6 / 40 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | budget_write_skew | naive | naive | locks | clean 6, failed 26 (write_skew 26) | clean 32 | 0.65 | 6 / 44 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | budget_write_skew | naive | naive | all_available | clean 6, failed 26 (write_skew 26) | clean 32 | 0.65 | 6 / 44 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | budget_write_skew | rereader | naive | none | clean 7, failed 25 (write_skew 25) | clean 32 | 0.57 | 11 / 40 | - | 0 | 0 (0) | 0 | 0.43/0.00 | 0 | yes |
| 4 | budget_write_skew | rereader | naive | cas_available | clean 7, failed 25 (write_skew 25) | clean 32 | 0.57 | 11 / 40 | - | 0 | 0 (0) | 0 | 0.43/0.00 | 0 | yes |
| 4 | budget_write_skew | rereader | naive | locks | clean 7, failed 25 (write_skew 25) | clean 32 | 0.57 | 11 / 44 | - | 0 | 0 (0) | 0 | 0.43/0.00 | 0 | yes |
| 4 | budget_write_skew | rereader | naive | all_available | clean 7, failed 25 (write_skew 25) | clean 32 | 0.57 | 11 / 44 | - | 0 | 0 (0) | 0 | 0.43/0.00 | 0 | yes |
| 4 | budget_write_skew | cas_retry | naive | cas_available | clean 6, failed 26 (write_skew 26) | clean 32 | 0.65 | 6 / 40 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | budget_write_skew | cas_retry | naive | all_available | clean 6, failed 26 (write_skew 26) | clean 32 | 0.65 | 6 / 44 | - | 0 | 0 (0) | 0 | 0.35/0.00 | 0 | yes |
| 4 | budget_write_skew | promote_before_write | correct | cas_available | clean 32 | clean 32 | 0.25 | 21 / 40 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | budget_write_skew | promote_before_write | correct | all_available | clean 32 | clean 32 | 0.25 | 21 / 44 | - | 0 | 0 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | budget_write_skew | promote_after_write | naive | cas_available | clean 7, failed 25 (write_skew 25) | clean 32 | 0.61 | 17 / 40 | - | 0 | 0 (0) | 0 | 0.94/0.00 | 0 | yes |
| 4 | budget_write_skew | promote_after_write | naive | all_available | clean 7, failed 25 (write_skew 25) | clean 32 | 0.61 | 17 / 44 | - | 0 | 0 (0) | 0 | 0.94/0.00 | 0 | yes |
| 4 | budget_write_skew | verify_and_compensate | correct | none | clean 6, compensated 26 | clean 32 | 0.25 | 39 / 40 | - | 0 | 0 (0) | 0 | 0.94/0.00 | 0 | n/a (not required) |
| 4 | budget_write_skew | verify_and_compensate | correct | cas_available | clean 6, compensated 26 | clean 32 | 0.25 | 39 / 40 | - | 0 | 0 (0) | 0 | 0.94/0.00 | 0 | n/a (not required) |
| 4 | budget_write_skew | verify_and_compensate | correct | locks | clean 6, compensated 26 | clean 32 | 0.25 | 39 / 44 | - | 0 | 0 (0) | 0 | 0.94/0.00 | 0 | n/a (not required) |
| 4 | budget_write_skew | verify_and_compensate | correct | all_available | clean 6, compensated 26 | clean 32 | 0.25 | 39 / 44 | - | 0 | 0 (0) | 0 | 0.94/0.00 | 0 | n/a (not required) |
| 4 | budget_write_skew | lock_protected | correct | locks | clean 32 | clean 32 | 0.25 | 16 / 44 | 1.00/1.00/1.00 | 0 | 103 (15) | 0 | 0.75/0.00 | 0 | yes |
| 4 | budget_write_skew | lock_protected | correct | all_available | clean 32 | clean 32 | 0.25 | 16 / 44 | 1.00/1.00/1.00 | 0 | 103 (15) | 0 | 0.75/0.00 | 0 | yes |
| 4 | budget_write_skew | lock_writes_only | naive | locks | clean 6, failed 26 (write_skew 26) | clean 32 | 0.62 | 8 / 44 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.38/0.00 | 0 | yes |
| 4 | budget_write_skew | lock_writes_only | naive | all_available | clean 6, failed 26 (write_skew 26) | clean 32 | 0.62 | 8 / 44 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.38/0.00 | 0 | yes |
| 4 | budget_write_skew | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 17 / 44 | 1.00/1.00/n/a | 0 | 224 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | budget_write_skew | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 17 / 44 | 1.00/1.00/n/a | 0 | 224 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | budget_write_skew | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 17 / 44 | 1.00/1.00/n/a | 0 | 115 (21) | 0 | 0.75/0.00 | 0 | yes |
| 4 | budget_write_skew | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 17 / 44 | 1.00/1.00/n/a | 0 | 115 (21) | 0 | 0.75/0.00 | 0 | yes |
| 4 | budget_write_skew | reacquire_no_reread | naive | locks | failed 32 (write_skew 32) | clean 32 | 0.91 | 23 / 44 | 1.00/1.00/0.00 | 117 | 327 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | budget_write_skew | reacquire_no_reread | naive | all_available | failed 32 (write_skew 32) | clean 32 | 0.91 | 23 / 44 | 1.00/1.00/0.00 | 117 | 327 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | budget_write_skew | lease_then_tokenless | naive | locks | clean 1, failed 31 (write_skew 31) | clean 32 | 0.67 | 15 / 44 | 1.00/1.00/0.00 | 0 | 224 (0) | 0 | 0.83/0.00 | 0 | yes |
| 4 | budget_write_skew | lease_then_tokenless | naive | all_available | clean 1, failed 31 (write_skew 31) | clean 32 | 0.67 | 15 / 44 | 1.00/1.00/0.00 | 0 | 224 (0) | 0 | 0.83/0.00 | 0 | yes |
| 4 | budget_write_skew | lock_own_first | probe | locks | clean 32 | clean 32 | 0.00 | 19 / 44 | 1.00/0.95/n/a | 0 | 526 (493) | 32 | 1.00/0.00 | 0 | yes |
| 4 | budget_write_skew | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.00 | 19 / 44 | 1.00/0.95/n/a | 0 | 526 (493) | 32 | 1.00/0.00 | 0 | yes |
| 4 | joint_account_write_skew | naive | naive | none | failed 32 (write_skew 32) | clean 32 | 0.98 | 5 / 40 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 4 | joint_account_write_skew | naive | naive | cas_available | failed 32 (write_skew 32) | clean 32 | 0.98 | 5 / 40 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 4 | joint_account_write_skew | naive | naive | locks | failed 32 (write_skew 32) | clean 32 | 0.98 | 5 / 44 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 4 | joint_account_write_skew | naive | naive | all_available | failed 32 (write_skew 32) | clean 32 | 0.98 | 5 / 44 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 4 | joint_account_write_skew | rereader | naive | none | clean 1, failed 31 (write_skew 31) | clean 32 | 0.94 | 9 / 40 | - | 0 | 0 (0) | 0 | 0.29/0.00 | 0 | yes |
| 4 | joint_account_write_skew | rereader | naive | cas_available | clean 1, failed 31 (write_skew 31) | clean 32 | 0.94 | 9 / 40 | - | 0 | 0 (0) | 0 | 0.29/0.00 | 0 | yes |
| 4 | joint_account_write_skew | rereader | naive | locks | clean 1, failed 31 (write_skew 31) | clean 32 | 0.94 | 9 / 44 | - | 0 | 0 (0) | 0 | 0.29/0.00 | 0 | yes |
| 4 | joint_account_write_skew | rereader | naive | all_available | clean 1, failed 31 (write_skew 31) | clean 32 | 0.94 | 9 / 44 | - | 0 | 0 (0) | 0 | 0.29/0.00 | 0 | yes |
| 4 | joint_account_write_skew | cas_retry | naive | cas_available | failed 32 (write_skew 32) | clean 32 | 0.98 | 5 / 40 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 4 | joint_account_write_skew | cas_retry | naive | all_available | failed 32 (write_skew 32) | clean 32 | 0.98 | 5 / 44 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 4 | joint_account_write_skew | promote_before_write | correct | cas_available | clean 32 | clean 32 | 0.55 | 40 / 40 | - | 0 | 0 (0) | 0 | 0.79/0.00 | 0 | n/a (not required) |
| 4 | joint_account_write_skew | promote_before_write | correct | all_available | clean 32 | clean 32 | 0.55 | 44 / 44 | - | 0 | 0 (0) | 0 | 0.79/0.00 | 0 | n/a (not required) |
| 4 | joint_account_write_skew | promote_after_write | naive | cas_available | clean 13, failed 19 (write_skew 19) | clean 32 | 0.76 | 18 / 40 | - | 0 | 0 (0) | 0 | 0.98/0.00 | 0 | yes |
| 4 | joint_account_write_skew | promote_after_write | naive | all_available | clean 13, failed 19 (write_skew 19) | clean 32 | 0.76 | 18 / 44 | - | 0 | 0 (0) | 0 | 0.98/0.00 | 0 | yes |
| 4 | joint_account_write_skew | verify_and_compensate | correct | none | compensated 32 | clean 32 | 0.56 | 40 / 40 | - | 0 | 0 (0) | 0 | 0.98/0.00 | 0 | n/a (not required) |
| 4 | joint_account_write_skew | verify_and_compensate | correct | cas_available | compensated 32 | clean 32 | 0.56 | 40 / 40 | - | 0 | 0 (0) | 0 | 0.98/0.00 | 0 | n/a (not required) |
| 4 | joint_account_write_skew | verify_and_compensate | correct | locks | compensated 32 | clean 32 | 0.56 | 40 / 44 | - | 0 | 0 (0) | 0 | 0.98/0.00 | 0 | n/a (not required) |
| 4 | joint_account_write_skew | verify_and_compensate | correct | all_available | compensated 32 | clean 32 | 0.56 | 40 / 44 | - | 0 | 0 (0) | 0 | 0.98/0.00 | 0 | n/a (not required) |
| 4 | joint_account_write_skew | lock_protected | correct | locks | clean 32 | clean 32 | 0.56 | 13 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lock_protected | correct | all_available | clean 32 | clean 32 | 0.56 | 13 / 44 | 1.00/1.00/1.00 | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lock_writes_only | naive | locks | failed 32 (write_skew 32) | clean 32 | 0.98 | 7 / 44 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.29/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lock_writes_only | naive | all_available | failed 32 (write_skew 32) | clean 32 | 0.98 | 7 / 44 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.29/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lock_short_lease | probe | locks | clean 32 | clean 32 | 0.00 | 14 / 44 | 1.00/1.00/n/a | 0 | 202 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lock_short_lease | probe | all_available | clean 32 | clean 32 | 0.00 | 14 / 44 | 1.00/1.00/n/a | 0 | 202 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lock_no_fence | probe | locks | clean 32 | clean 32 | 0.00 | 13 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lock_no_fence | probe | all_available | clean 32 | clean 32 | 0.00 | 13 / 44 | 1.00/1.00/n/a | 0 | 96 (0) | 0 | 0.75/0.00 | 0 | yes |
| 4 | joint_account_write_skew | reacquire_no_reread | naive | locks | clean 1, failed 31 (write_skew 31) | clean 32 | 0.99 | 19 / 44 | 1.00/1.00/0.00 | 127 | 341 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | joint_account_write_skew | reacquire_no_reread | naive | all_available | clean 1, failed 31 (write_skew 31) | clean 32 | 0.99 | 19 / 44 | 1.00/1.00/0.00 | 127 | 341 (0) | 0 | 1.00/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lease_then_tokenless | naive | locks | clean 3, failed 29 (write_skew 29) | clean 32 | 0.89 | 13 / 44 | 1.00/1.00/0.00 | 0 | 202 (0) | 0 | 0.82/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lease_then_tokenless | naive | all_available | clean 3, failed 29 (write_skew 29) | clean 32 | 0.89 | 13 / 44 | 1.00/1.00/0.00 | 0 | 202 (0) | 0 | 0.82/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lock_own_first | probe | locks | clean 32 | clean 32 | 0.00 | 16 / 44 | 1.00/0.88/n/a | 0 | 527 (499) | 32 | 1.00/0.00 | 0 | yes |
| 4 | joint_account_write_skew | lock_own_first | probe | all_available | clean 32 | clean 32 | 0.00 | 16 / 44 | 1.00/0.88/n/a | 0 | 527 (499) | 32 | 1.00/0.00 | 0 | yes |

## Checker agreement (all validity episodes)

| | count |
|---|---|
| fs=False dsg=False | 16380 |
| fs=False dsg=True | 1992 |
| fs=True dsg=True | 5436 |

All-reads DSG vs fs disagreement classes (definitional; see score5):

| policy | side | class | episodes |
|---|---|---|---|
| cas_retry | dsg_only | clean | 546 |
| rereader | dsg_only | clean | 488 |
| verify_and_compensate | dsg_only | compensated | 396 |
| promote_before_write | dsg_only | clean | 256 |
| cas_claim | dsg_only | clean | 200 |
| promote_after_write | dsg_only | clean | 98 |
| lease_then_tokenless | dsg_only | clean | 6 |
| reacquire_no_reread | dsg_only | clean | 2 |

### Three verdicts: fs, all-reads DSG, per-write basis DSG

| | count |
|---|---|
| fs=False dsg=False basis=False | 16380 |
| fs=False dsg=True basis=False | 1564 |
| fs=False dsg=True basis=True | 428 |
| fs=True dsg=True basis=True | 5436 |

fs vs basis-DSG disagreements:

| policy | side | class | compensation_exposed | episodes |
|---|---|---|---|---|
| verify_and_compensate | basis_only | compensated | compensation_exposed | 288 |
| promote_before_write | basis_only | clean | - | 100 |
| promote_after_write | basis_only | clean | - | 24 |
| lease_then_tokenless | basis_only | clean | - | 6 |
| rereader | basis_only | clean | - | 4 |
| verify_and_compensate | basis_only | compensated | - | 4 |
| reacquire_no_reread | basis_only | clean | - | 2 |

## Write-skew protocol tail (n = 2, 8 instances x 50 schedules, contended)

| family | policy | config | outcomes | above 80 % of cap | cap endings | p95 | p99 | max / cap |
|---|---|---|---|---|---|---|---|---|
| budget_write_skew | promote_before_write | cas_available | clean 400 | 0/400 | 0 | 13 | 14 | 18 / 24 |
| budget_write_skew | promote_before_write | all_available | clean 400 | 0/400 | 0 | 13 | 14 | 18 / 28 |
| budget_write_skew | verify_and_compensate | none | clean 176, compensated 224 | 1/400 | 1 | 15 | 19 | 24 / 24 |
| budget_write_skew | verify_and_compensate | cas_available | clean 176, compensated 224 | 1/400 | 1 | 15 | 19 | 24 / 24 |
| budget_write_skew | verify_and_compensate | locks | clean 176, compensated 224 | 1/400 | 0 | 15 | 19 | 25 / 28 |
| budget_write_skew | verify_and_compensate | all_available | clean 176, compensated 224 | 1/400 | 0 | 15 | 19 | 25 / 28 |
| budget_write_skew | lock_protected | locks | clean 400 | 0/400 | 0 | 10 | 10 | 10 / 28 |
| budget_write_skew | lock_protected | all_available | clean 400 | 0/400 | 0 | 10 | 10 | 10 / 28 |
| joint_account_write_skew | promote_before_write | cas_available | clean 400 | 9/400 | 1 | 13 | 24 | 24 / 24 |
| joint_account_write_skew | promote_before_write | all_available | clean 400 | 5/400 | 0 | 13 | 24 | 25 / 28 |
| joint_account_write_skew | verify_and_compensate | none | clean 149, compensated 251 | 0/400 | 0 | 12 | 14 | 16 / 24 |
| joint_account_write_skew | verify_and_compensate | cas_available | clean 149, compensated 251 | 0/400 | 0 | 12 | 14 | 16 / 24 |
| joint_account_write_skew | verify_and_compensate | locks | clean 149, compensated 251 | 0/400 | 0 | 12 | 14 | 16 / 28 |
| joint_account_write_skew | verify_and_compensate | all_available | clean 149, compensated 251 | 0/400 | 0 | 12 | 14 | 16 / 28 |
| joint_account_write_skew | lock_protected | locks | clean 400 | 0/400 | 0 | 7 | 7 | 7 / 28 |
| joint_account_write_skew | lock_protected | all_available | clean 400 | 0/400 | 0 | 7 | 7 | 7 / 28 |

## Interleavings (naive policy, contended, n = 2, config none)

- **study2**: 224 episodes; first mover {'a1': 110, 'a0': 114}; every first read before every other agent's first write in 85%; 11 distinct patterns; top [('R0R1W0W1', 54), ('R1R0W1W0', 53), ('R0R1W1W0', 34), ('R1R0W0W1', 28), ('R0W0R1', 19)]; failure rate naive 0.754, rereader 0.558
- **study1_like**: 224 episodes; first mover {'a0': 116, 'a1': 108}; every first read before every other agent's first write in 100%; 4 distinct patterns; top [('R1R0W0W1', 62), ('R0R1W1W0', 58), ('R0R1W0W1', 54), ('R1R0W1W0', 50)]; failure rate naive 1.0, rereader 1.0
