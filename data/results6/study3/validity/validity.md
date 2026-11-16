# Reference policy validity table (4 instances x 8 schedules per cell)

Lock columns (contended): attempted / granted share of agents, effective share of the agents that were granted a lock and committed a write; fenced writes with a stale basis; lock waits (423 after the full wait); deadlock episodes. Exposure (Round 3): share of agents with a peer-caused contention signal, contended / control (the control must be 0); cap-truncated failed episodes (contended).

| n | family | policy | role | config@start | contended outcomes | control | fulfilled (cont.) | max (p95) calls / cap | lock att/gr/eff | stale-basis fenced | waits (423) | deadlocks | exposure c/k | cap-trunc | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | inventory_last_unit | naive | naive | none@together | clean 9, failed 23 (lost_update 23) | clean 32 | 0.86 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | cas_available@together | clean 9, failed 23 (lost_update 23) | clean 32 | 0.86 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | locks_s2text@together | clean 9, failed 23 (lost_update 23) | clean 32 | 0.86 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | locks@together | clean 9, failed 23 (lost_update 23) | clean 32 | 0.86 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | all_available@together | clean 9, failed 23 (lost_update 23) | clean 32 | 0.86 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | locks@staggered | clean 29, failed 3 (lost_update 3) | clean 32 | 0.55 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.45/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | all_available@staggered | clean 29, failed 3 (lost_update 3) | clean 32 | 0.55 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | none@together | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | cas_available@together | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | locks_s2text@together | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | locks@together | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | all_available@together | clean 11, failed 21 (lost_update 21) | clean 32 | 0.83 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | locks@staggered | clean 27, failed 5 (lost_update 5) | clean 32 | 0.58 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.42/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | all_available@staggered | clean 27, failed 5 (lost_update 5) | clean 32 | 0.58 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | cas_retry | correct | cas_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | cas_retry | correct | all_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | cas_retry | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | all_available@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | locks@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | all_available@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 14 (0) | 0 | 0.92/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 14 (0) | 0 | 0.92/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | all_available@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | locks@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | all_available@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | locks_s2text@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.52/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | locks@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.52/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | all_available@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.58/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | locks@staggered | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 14 (0) | 0 | 0.53/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | all_available@staggered | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 14 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | all_available@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | locks@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | all_available@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | none@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | cas_available@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | locks_s2text@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | locks@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | all_available@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | locks@staggered | clean 32 | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | all_available@staggered | clean 32 | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | none@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | cas_available@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | locks_s2text@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | locks@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.17/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | all_available@together | clean 11, failed 21 (lost_update 21) | clean 32 | 1.00 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | locks@staggered | clean 27, failed 5 (lost_update 5) | clean 32 | 1.00 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.42/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | all_available@staggered | clean 27, failed 5 (lost_update 5) | clean 32 | 1.00 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | cas_retry | correct | cas_available@together | clean 32 | clean 32 | 1.00 | 4 (4) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | cas_retry | correct | all_available@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | cas_retry | correct | all_available@staggered | clean 32 | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | locks@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | all_available@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | locks@staggered | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | all_available@staggered | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | all_available@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 14 (0) | 0 | 0.89/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 14 (0) | 0 | 0.89/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | all_available@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 65 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 65 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 65 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | locks@staggered | clean 3, failed 29 (lost_update 29) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 52 (0) | 0 | 0.95/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | all_available@staggered | clean 3, failed 29 (lost_update 29) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 52 (0) | 0 | 0.95/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | locks_s2text@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | locks@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | all_available@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | locks@staggered | clean 6, failed 26 (lost_update 26) | clean 32 | 0.91 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 14 (0) | 0 | 0.59/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | all_available@staggered | clean 6, failed 26 (lost_update 26) | clean 32 | 0.91 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 14 (0) | 0 | 0.61/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | locks@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | all_available@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | locks@staggered | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | all_available@staggered | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | none@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | cas_available@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | locks_s2text@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | locks@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | all_available@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | locks@staggered | clean 32 | clean 32 | 0.50 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | all_available@staggered | clean 32 | clean 32 | 0.50 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | none@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | cas_available@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | locks_s2text@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | locks@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | all_available@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | locks@staggered | clean 29, failed 3 (lost_update 3) | clean 32 | 0.55 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.45/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | all_available@staggered | clean 29, failed 3 (lost_update 3) | clean 32 | 0.55 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_retry | correct | cas_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_retry | correct | all_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_retry | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | all_available@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | locks@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | all_available@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 14 (0) | 0 | 0.89/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 14 (0) | 0 | 0.89/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | all_available@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | none@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | cas_available@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | locks_s2text@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | locks@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | all_available@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | locks@staggered | clean 32 | clean 32 | 0.50 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | all_available@staggered | clean 32 | clean 32 | 0.50 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_claim | correct | cas_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_claim | correct | all_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | cas_claim | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | locks@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 62 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | all_available@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 62 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 28 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 28 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 28 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | locks@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 14 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | all_available@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 14 (0) | 0 | 0.52/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | all_available@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | locks@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | all_available@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 25 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | none@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | cas_available@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | locks_s2text@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | locks@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | all_available@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | locks@staggered | clean 28, failed 4 (lost_update 4) | clean 32 | 0.56 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.44/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | all_available@staggered | clean 28, failed 4 (lost_update 4) | clean 32 | 0.56 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | none@together | clean 15, failed 17 (lost_update 17) | clean 32 | 0.77 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | cas_available@together | clean 15, failed 17 (lost_update 17) | clean 32 | 0.77 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | locks_s2text@together | clean 15, failed 17 (lost_update 17) | clean 32 | 0.77 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | locks@together | clean 15, failed 17 (lost_update 17) | clean 32 | 0.77 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | all_available@together | clean 15, failed 17 (lost_update 17) | clean 32 | 0.77 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | locks@staggered | clean 26, failed 6 (lost_update 6) | clean 32 | 0.59 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.41/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | all_available@staggered | clean 26, failed 6 (lost_update 6) | clean 32 | 0.59 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_retry | correct | cas_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_retry | correct | all_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_retry | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | all_available@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | locks@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | all_available@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 13 (0) | 0 | 0.89/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 13 (0) | 0 | 0.89/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | all_available@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | none@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | cas_available@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | locks_s2text@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | locks@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | all_available@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | locks@staggered | clean 28, failed 4 (lost_update 4) | clean 32 | 0.56 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.44/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | all_available@staggered | clean 28, failed 4 (lost_update 4) | clean 32 | 0.56 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_claim | correct | cas_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_claim | correct | all_available@together | clean 32 | clean 32 | 0.50 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | cas_claim | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 71 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 71 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 71 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | locks@staggered | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 7 (7) / 28 | 1.00/1.00/0.00 | 63 | 58 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | all_available@staggered | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 7 (7) / 28 | 1.00/1.00/0.00 | 63 | 58 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | locks_s2text@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 28 (0) | 0 | 0.52/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | locks@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 28 (0) | 0 | 0.52/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | all_available@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 28 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | locks@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 13 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | all_available@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 13 (0) | 0 | 0.52/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | all_available@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 31 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | locks@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | all_available@staggered | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 27 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | none@together | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 4 (4) / 24 | - | 0 | 0 (0) | 0 | 0.03/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | cas_available@together | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 4 (4) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | locks_s2text@together | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.03/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | locks@together | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.03/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | all_available@together | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | locks@staggered | clean 19, failed 13 (lost_update 13) | clean 32 | 0.70 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.30/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | all_available@staggered | clean 19, failed 13 (lost_update 13) | clean 32 | 0.70 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | none@together | clean 4, failed 28 (lost_update 28) | clean 32 | 0.94 | 6 (6) / 24 | - | 0 | 0 (0) | 0 | 0.06/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | cas_available@together | clean 4, failed 28 (lost_update 28) | clean 32 | 0.94 | 6 (6) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | locks_s2text@together | clean 4, failed 28 (lost_update 28) | clean 32 | 0.94 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.06/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | locks@together | clean 4, failed 28 (lost_update 28) | clean 32 | 0.94 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.06/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | all_available@together | clean 4, failed 28 (lost_update 28) | clean 32 | 0.94 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | locks@staggered | clean 12, failed 20 (lost_update 20) | clean 32 | 0.81 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.19/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | all_available@staggered | clean 12, failed 20 (lost_update 20) | clean 32 | 0.81 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | cas_retry | correct | cas_available@together | clean 32 | clean 32 | 0.50 | 5 (5) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | cas_retry | correct | all_available@together | clean 32 | clean 32 | 0.50 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | cas_retry | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | all_available@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | locks@staggered | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | all_available@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 15 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 15 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | all_available@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 58 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 58 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 58 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | locks@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 41 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | all_available@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 41 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.58/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | locks@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 15 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | all_available@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 15 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | all_available@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | locks@staggered | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | all_available@staggered | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | none@together | clean 9, failed 23 (write_skew 23) | clean 32 | 0.86 | 4 (4) / 24 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | cas_available@together | clean 9, failed 23 (write_skew 23) | clean 32 | 0.86 | 4 (4) / 24 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | locks_s2text@together | clean 9, failed 23 (write_skew 23) | clean 32 | 0.86 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | locks@together | clean 9, failed 23 (write_skew 23) | clean 32 | 0.86 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | all_available@together | clean 9, failed 23 (write_skew 23) | clean 32 | 0.86 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | locks@staggered | clean 28, failed 4 (write_skew 4) | clean 32 | 0.56 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.44/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | all_available@staggered | clean 28, failed 4 (write_skew 4) | clean 32 | 0.56 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.44/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | none@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 7 (7) / 24 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | cas_available@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 7 (7) / 24 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | locks_s2text@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 7 (7) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | locks@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 7 (7) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | all_available@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 7 (7) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | locks@staggered | clean 26, failed 6 (write_skew 6) | clean 32 | 0.59 | 7 (7) / 28 | - | 0 | 0 (0) | 0 | 0.41/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | all_available@staggered | clean 26, failed 6 (write_skew 6) | clean 32 | 0.59 | 7 (7) / 28 | - | 0 | 0 (0) | 0 | 0.41/0.00 | 0 | yes |
| 2 | budget_write_skew | cas_retry | naive | cas_available@together | clean 9, failed 23 (write_skew 23) | clean 32 | 0.86 | 4 (4) / 24 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | budget_write_skew | cas_retry | naive | all_available@together | clean 9, failed 23 (write_skew 23) | clean 32 | 0.86 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.14/0.00 | 0 | yes |
| 2 | budget_write_skew | cas_retry | naive | all_available@staggered | clean 28, failed 4 (write_skew 4) | clean 32 | 0.56 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.44/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_before_write | correct | cas_available@together | clean 32 | clean 32 | 0.50 | 13 (13) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_before_write | correct | all_available@together | clean 32 | clean 32 | 0.50 | 13 (13) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_before_write | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 15 (14) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_after_write | naive | cas_available@together | clean 11, failed 21 (write_skew 21) | clean 32 | 0.83 | 12 (7) / 24 | - | 0 | 0 (0) | 0 | 0.83/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_after_write | naive | all_available@together | clean 11, failed 21 (write_skew 21) | clean 32 | 0.83 | 12 (7) / 28 | - | 0 | 0 (0) | 0 | 0.83/0.00 | 0 | yes |
| 2 | budget_write_skew | promote_after_write | naive | all_available@staggered | clean 28, failed 4 (write_skew 4) | clean 32 | 0.56 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | none@together | clean 9, compensated 23 | clean 32 | 0.50 | 15 (15) / 24 | - | 0 | 0 (0) | 0 | 0.83/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | cas_available@together | clean 9, compensated 23 | clean 32 | 0.50 | 15 (15) / 24 | - | 0 | 0 (0) | 0 | 0.83/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | locks_s2text@together | clean 9, compensated 23 | clean 32 | 0.50 | 15 (15) / 28 | - | 0 | 0 (0) | 0 | 0.83/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | locks@together | clean 9, compensated 23 | clean 32 | 0.50 | 15 (15) / 28 | - | 0 | 0 (0) | 0 | 0.83/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | all_available@together | clean 9, compensated 23 | clean 32 | 0.50 | 15 (15) / 28 | - | 0 | 0 (0) | 0 | 0.83/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | locks@staggered | clean 28, compensated 4 | clean 32 | 0.50 | 16 (15) / 28 | - | 0 | 0 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | all_available@staggered | clean 28, compensated 4 | clean 32 | 0.50 | 16 (15) / 28 | - | 0 | 0 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | all_available@together | clean 32 | clean 32 | 0.50 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | locks@staggered | clean 32 | clean 32 | 0.50 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | locks_s2text@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 6 (6) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | locks@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 6 (6) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | all_available@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 6 (6) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | locks@staggered | clean 26, failed 6 (write_skew 6) | clean 32 | 0.59 | 6 (6) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.92/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | all_available@staggered | clean 26, failed 6 (write_skew 6) | clean 32 | 0.59 | 6 (6) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.92/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 11 (11) / 28 | 1.00/1.00/n/a | 0 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 11 (11) / 28 | 1.00/1.00/n/a | 0 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | all_available@together | clean 32 | clean 32 | 0.00 | 11 (11) / 28 | 1.00/1.00/n/a | 0 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 11 (11) / 28 | 1.00/1.00/n/a | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 11 (11) / 28 | 1.00/1.00/n/a | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 10 (10) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 10 (10) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | all_available@together | clean 32 | clean 32 | 0.00 | 10 (10) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 10 (10) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 10 (10) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | locks_s2text@together | clean 1, failed 31 (write_skew 31) | clean 32 | 0.98 | 15 (15) / 28 | 1.00/1.00/0.00 | 63 | 87 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | locks@together | clean 1, failed 31 (write_skew 31) | clean 32 | 0.98 | 15 (15) / 28 | 1.00/1.00/0.00 | 63 | 87 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | all_available@together | clean 1, failed 31 (write_skew 31) | clean 32 | 0.98 | 15 (15) / 28 | 1.00/1.00/0.00 | 63 | 87 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | locks@staggered | failed 32 (write_skew 32) | clean 32 | 1.00 | 15 (15) / 28 | 1.00/1.00/0.00 | 64 | 59 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | all_available@staggered | failed 32 (write_skew 32) | clean 32 | 1.00 | 15 (15) / 28 | 1.00/1.00/0.00 | 64 | 59 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | locks_s2text@together | clean 2, failed 30 (write_skew 30) | clean 32 | 0.97 | 11 (11) / 28 | 1.00/1.00/0.00 | 0 | 57 (0) | 0 | 0.52/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | locks@together | clean 2, failed 30 (write_skew 30) | clean 32 | 0.97 | 11 (11) / 28 | 1.00/1.00/0.00 | 0 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | all_available@together | clean 2, failed 30 (write_skew 30) | clean 32 | 0.97 | 11 (11) / 28 | 1.00/1.00/0.00 | 0 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | locks@staggered | clean 2, failed 30 (write_skew 30) | clean 32 | 0.97 | 11 (11) / 28 | 1.00/1.00/0.00 | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | all_available@staggered | clean 2, failed 30 (write_skew 30) | clean 32 | 0.97 | 11 (11) / 28 | 1.00/1.00/0.00 | 0 | 28 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.02 | 13 (13) / 28 | 1.00/1.00/1.00 | 0 | 251 (232) | 31 | 0.98/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.02 | 13 (13) / 28 | 1.00/1.00/1.00 | 0 | 251 (232) | 31 | 0.98/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | all_available@together | clean 32 | clean 32 | 0.02 | 13 (13) / 28 | 1.00/1.00/1.00 | 0 | 251 (232) | 31 | 0.98/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | locks@staggered | clean 32 | clean 32 | 0.33 | 13 (13) / 28 | 1.00/1.00/1.00 | 0 | 128 (82) | 11 | 0.67/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | all_available@staggered | clean 32 | clean 32 | 0.33 | 13 (13) / 28 | 1.00/1.00/1.00 | 0 | 128 (82) | 11 | 0.67/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | none@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | cas_available@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | locks_s2text@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | locks@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | all_available@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | locks@staggered | clean 27, failed 5 (write_skew 5) | clean 32 | 0.58 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.42/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | all_available@staggered | clean 27, failed 5 (write_skew 5) | clean 32 | 0.58 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.42/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | none@together | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 5 (5) / 24 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | cas_available@together | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 5 (5) / 24 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | locks_s2text@together | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | locks@together | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | all_available@together | clean 13, failed 19 (write_skew 19) | clean 32 | 0.80 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | locks@staggered | clean 28, failed 4 (write_skew 4) | clean 32 | 0.56 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.44/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | all_available@staggered | clean 28, failed 4 (write_skew 4) | clean 32 | 0.56 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.44/0.00 | 0 | yes |
| 2 | joint_account_write_skew | cas_retry | naive | cas_available@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 24 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | cas_retry | naive | all_available@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | cas_retry | naive | all_available@staggered | clean 27, failed 5 (write_skew 5) | clean 32 | 0.58 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.42/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_before_write | correct | cas_available@together | clean 32 | clean 32 | 0.50 | 24 (13) / 24 | - | 0 | 0 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_before_write | correct | all_available@together | clean 32 | clean 32 | 0.50 | 24 (13) / 28 | - | 0 | 0 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_before_write | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 12 (12) / 28 | - | 0 | 0 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_after_write | naive | cas_available@together | clean 18, failed 14 (write_skew 14) | clean 32 | 0.72 | 10 (6) / 24 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_after_write | naive | all_available@together | clean 18, failed 14 (write_skew 14) | clean 32 | 0.72 | 10 (6) / 28 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | joint_account_write_skew | promote_after_write | naive | all_available@staggered | clean 29, failed 3 (write_skew 3) | clean 32 | 0.55 | 11 (6) / 28 | - | 0 | 0 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | none@together | clean 14, compensated 18 | clean 32 | 0.50 | 12 (11) / 24 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | cas_available@together | clean 14, compensated 18 | clean 32 | 0.50 | 12 (11) / 24 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | locks_s2text@together | clean 14, compensated 18 | clean 32 | 0.50 | 12 (11) / 28 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | locks@together | clean 14, compensated 18 | clean 32 | 0.50 | 12 (11) / 28 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | all_available@together | clean 14, compensated 18 | clean 32 | 0.50 | 12 (11) / 28 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | locks@staggered | clean 27, compensated 5 | clean 32 | 0.50 | 10 (9) / 28 | - | 0 | 0 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | all_available@staggered | clean 27, compensated 5 | clean 32 | 0.50 | 10 (9) / 28 | - | 0 | 0 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 7 (7) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 7 (7) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | all_available@together | clean 32 | clean 32 | 0.50 | 7 (7) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | locks@staggered | clean 32 | clean 32 | 0.50 | 7 (7) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 7 (7) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | locks_s2text@together | clean 15, failed 17 (write_skew 17) | clean 32 | 0.77 | 5 (5) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | locks@together | clean 15, failed 17 (write_skew 17) | clean 32 | 0.77 | 5 (5) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | all_available@together | clean 15, failed 17 (write_skew 17) | clean 32 | 0.77 | 5 (5) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | locks@staggered | clean 29, failed 3 (write_skew 3) | clean 32 | 0.55 | 5 (5) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.73/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | all_available@staggered | clean 29, failed 3 (write_skew 3) | clean 32 | 0.55 | 5 (5) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.73/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 43 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 43 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | all_available@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 43 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 23 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 23 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | all_available@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | locks_s2text@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 (11) / 28 | 1.00/1.00/0.00 | 64 | 76 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | locks@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 (11) / 28 | 1.00/1.00/0.00 | 64 | 76 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | all_available@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 (11) / 28 | 1.00/1.00/0.00 | 64 | 76 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | locks@staggered | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 (11) / 28 | 1.00/1.00/0.00 | 64 | 53 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | all_available@staggered | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 (11) / 28 | 1.00/1.00/0.00 | 64 | 53 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | locks_s2text@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 9 (9) / 28 | 1.00/1.00/0.00 | 0 | 43 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | locks@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 9 (9) / 28 | 1.00/1.00/0.00 | 0 | 43 (0) | 0 | 0.73/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | all_available@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 9 (9) / 28 | 1.00/1.00/0.00 | 0 | 43 (0) | 0 | 0.73/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | locks@staggered | clean 2, failed 30 (write_skew 30) | clean 32 | 0.97 | 9 (9) / 28 | 1.00/1.00/0.00 | 0 | 23 (0) | 0 | 0.58/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | all_available@staggered | clean 2, failed 30 (write_skew 30) | clean 32 | 0.97 | 9 (9) / 28 | 1.00/1.00/0.00 | 0 | 23 (0) | 0 | 0.58/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.23 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 196 (178) | 23 | 0.86/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.23 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 196 (178) | 23 | 0.86/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | all_available@together | clean 32 | clean 32 | 0.23 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 196 (178) | 23 | 0.86/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | locks@staggered | clean 32 | clean 32 | 0.50 | 10 (7) / 28 | 1.00/1.00/1.00 | 0 | 58 (7) | 1 | 0.52/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | all_available@staggered | clean 32 | clean 32 | 0.50 | 10 (7) / 28 | 1.00/1.00/1.00 | 0 | 58 (7) | 1 | 0.52/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | none@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 4 (4) / 24 | - | 0 | 0 (0) | 0 | 0.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | cas_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 4 (4) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | locks@staggered | clean 12, failed 20 (lost_update 20) | clean 32 | 0.81 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.19/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | all_available@staggered | clean 12, failed 20 (lost_update 20) | clean 32 | 0.81 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | none@together | clean 6, failed 26 (lost_update 26) | clean 32 | 0.91 | 6 (6) / 24 | - | 0 | 0 (0) | 0 | 0.09/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | cas_available@together | clean 6, failed 26 (lost_update 26) | clean 32 | 0.91 | 6 (6) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | locks_s2text@together | clean 6, failed 26 (lost_update 26) | clean 32 | 0.91 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.09/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | locks@together | clean 6, failed 26 (lost_update 26) | clean 32 | 0.91 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.09/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | all_available@together | clean 6, failed 26 (lost_update 26) | clean 32 | 0.91 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | locks@staggered | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | all_available@staggered | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | cas_retry | correct | cas_available@together | clean 32 | clean 32 | 0.50 | 5 (5) / 24 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | cas_retry | correct | all_available@together | clean 32 | clean 32 | 0.50 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | cas_retry | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_protected | correct | all_available@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_protected | correct | locks@staggered | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_protected | correct | all_available@staggered | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 29 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 29 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_short_lease | probe | all_available@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 29 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_short_lease | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 21 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_short_lease | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 21 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_no_fence | probe | all_available@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_no_fence | probe | locks@staggered | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_no_fence | probe | all_available@staggered | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 56 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 56 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | reacquire_no_reread | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 56 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | reacquire_no_reread | naive | locks@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 43 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | reacquire_no_reread | naive | all_available@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 43 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lease_then_tokenless | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 29 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lease_then_tokenless | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 29 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lease_then_tokenless | naive | all_available@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 29 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | transfer_same_amount | lease_then_tokenless | naive | locks@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 21 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lease_then_tokenless | naive | all_available@staggered | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 21 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_own_first | probe | all_available@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_own_first | probe | locks@staggered | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_own_first | probe | all_available@staggered | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |

## Checker agreement (all validity episodes)

| | count |
|---|---|
| fs=False dsg=False | 21130 |
| fs=False dsg=True | 1542 |
| fs=True dsg=True | 4976 |

All-reads DSG vs fs disagreement classes (definitional; see score6):

| policy | side | class | episodes |
|---|---|---|---|
| rereader | dsg_only | clean | 614 |
| cas_retry | dsg_only | clean | 328 |
| verify_and_compensate | dsg_only | compensated | 223 |
| promote_before_write | dsg_only | clean | 188 |
| promote_after_write | dsg_only | clean | 109 |
| cas_claim | dsg_only | clean | 80 |

### Three verdicts: fs, all-reads DSG, per-write basis DSG

| | count |
|---|---|
| fs=False dsg=False basis=False | 21130 |
| fs=False dsg=True basis=False | 1386 |
| fs=False dsg=True basis=True | 156 |
| fs=True dsg=True basis=True | 4976 |

fs vs basis-DSG disagreements:

| policy | side | class | compensation_exposed | episodes |
|---|---|---|---|---|
| verify_and_compensate | basis_only | compensated | compensation_exposed | 132 |
| promote_before_write | basis_only | clean | - | 24 |

## Write-skew protocol tail (n = 2, 8 instances x 50 schedules, contended)

| family | policy | config | outcomes | above 80 % of cap | cap endings | p95 | p99 | max / cap |
|---|---|---|---|---|---|---|---|---|
| budget_write_skew | promote_before_write | cas_available | clean 400 | 1/400 | 1 | 13 | 15 | 24 / 24 |
| budget_write_skew | promote_before_write | all_available | clean 400 | 1/400 | 0 | 13 | 15 | 26 / 28 |
| budget_write_skew | verify_and_compensate | none | clean 170, compensated 230 | 1/400 | 1 | 16 | 19 | 24 / 24 |
| budget_write_skew | verify_and_compensate | cas_available | clean 170, compensated 230 | 1/400 | 1 | 16 | 19 | 24 / 24 |
| budget_write_skew | verify_and_compensate | locks_s2text | clean 170, compensated 230 | 1/400 | 0 | 16 | 19 | 25 / 28 |
| budget_write_skew | verify_and_compensate | locks | clean 170, compensated 230 | 1/400 | 0 | 16 | 19 | 25 / 28 |
| budget_write_skew | verify_and_compensate | all_available | clean 170, compensated 230 | 1/400 | 0 | 16 | 19 | 25 / 28 |
| budget_write_skew | lock_protected | locks_s2text | clean 400 | 0/400 | 0 | 10 | 10 | 10 / 28 |
| budget_write_skew | lock_protected | locks | clean 400 | 0/400 | 0 | 10 | 10 | 10 / 28 |
| budget_write_skew | lock_protected | all_available | clean 400 | 0/400 | 0 | 10 | 10 | 10 / 28 |
| joint_account_write_skew | promote_before_write | cas_available | clean 400 | 6/400 | 1 | 12 | 23 | 24 / 24 |
| joint_account_write_skew | promote_before_write | all_available | clean 400 | 4/400 | 0 | 12 | 23 | 25 / 28 |
| joint_account_write_skew | verify_and_compensate | none | clean 151, compensated 249 | 0/400 | 0 | 10 | 15 | 19 / 24 |
| joint_account_write_skew | verify_and_compensate | cas_available | clean 151, compensated 249 | 0/400 | 0 | 10 | 15 | 19 / 24 |
| joint_account_write_skew | verify_and_compensate | locks_s2text | clean 151, compensated 249 | 0/400 | 0 | 10 | 15 | 19 / 28 |
| joint_account_write_skew | verify_and_compensate | locks | clean 151, compensated 249 | 0/400 | 0 | 10 | 15 | 19 / 28 |
| joint_account_write_skew | verify_and_compensate | all_available | clean 151, compensated 249 | 0/400 | 0 | 10 | 15 | 19 / 28 |
| joint_account_write_skew | lock_protected | locks_s2text | clean 400 | 0/400 | 0 | 7 | 7 | 7 / 28 |
| joint_account_write_skew | lock_protected | locks | clean 400 | 0/400 | 0 | 7 | 7 | 7 / 28 |
| joint_account_write_skew | lock_protected | all_available | clean 400 | 0/400 | 0 | 7 | 7 | 7 / 28 |

## Interleavings (naive policy, contended, n = 2, config none)

- **study3_together**: 256 episodes; first mover {'a1': 125, 'a0': 131}; every first read before every other agent's first write in 81%; 12 distinct patterns; top [('R0R1W0W1', 62), ('R1R0W1W0', 57), ('R0R1W1W0', 33), ('R1R0W0W1', 33), ('R1W1R0', 19)]; failure rate naive 0.723, rereader 0.648
- **study1_like**: 256 episodes; first mover {'a1': 117, 'a0': 139}; every first read before every other agent's first write in 100%; 4 distinct patterns; top [('R0R1W0W1', 73), ('R1R0W0W1', 66), ('R0R1W1W0', 63), ('R1R0W1W0', 54)]; failure rate naive 1.0, rereader 1.0
