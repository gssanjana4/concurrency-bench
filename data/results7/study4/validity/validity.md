# Reference policy validity table (4 instances x 8 schedules per cell)

Lock columns (contended): attempted / granted share of agents, effective share of the agents that were granted a lock and committed a write; fenced writes with a stale basis; lock waits (423 after the full wait); deadlock episodes. Exposure (Round 3): share of agents with a peer-caused contention signal, contended / control (the control must be 0); cap-truncated failed episodes (contended).

| n | family | policy | role | config@start | contended outcomes | control | fulfilled (cont.) | max (p95) calls / cap | lock att/gr/eff | stale-basis fenced | waits (423) | deadlocks | exposure c/k | cap-trunc | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | inventory_last_unit | naive | naive | locks_s2text@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | locks_instr@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | locks_signals@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | inventory_last_unit | naive | naive | locks@together | clean 10, failed 22 (lost_update 22) | clean 32 | 0.84 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.16/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | locks_s2text@together | clean 14, failed 18 (lost_update 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | locks_instr@together | clean 14, failed 18 (lost_update 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | locks_signals@together | clean 14, failed 18 (lost_update 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | inventory_last_unit | rereader | naive | locks@together | clean 14, failed 18 (lost_update 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | locks_instr@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | locks_signals@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 31 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | locks_instr@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | locks_signals@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 69 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | locks_s2text@together | clean 4, failed 28 (lost_update 28) | clean 32 | 0.94 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | locks_instr@together | clean 4, failed 28 (lost_update 28) | clean 32 | 0.94 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | locks_signals@together | clean 4, failed 28 (lost_update 28) | clean 32 | 0.94 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | inventory_last_unit | lease_then_tokenless | naive | locks@together | clean 4, failed 28 (lost_update 28) | clean 32 | 0.94 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 31 (0) | 0 | 0.56/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | locks_instr@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | locks_signals@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_last_unit | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | locks_s2text@together | clean 12, failed 20 (lost_update 20) | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.19/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | locks_instr@together | clean 12, failed 20 (lost_update 20) | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.19/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | locks_signals@together | clean 12, failed 20 (lost_update 20) | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.19/0.00 | 0 | yes |
| 2 | inventory_still_valid | naive | naive | locks@together | clean 12, failed 20 (lost_update 20) | clean 32 | 1.00 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.19/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | locks_s2text@together | clean 15, failed 17 (lost_update 17) | clean 32 | 1.00 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | locks_instr@together | clean 15, failed 17 (lost_update 17) | clean 32 | 1.00 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | locks_signals@together | clean 15, failed 17 (lost_update 17) | clean 32 | 1.00 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | inventory_still_valid | rereader | naive | locks@together | clean 15, failed 17 (lost_update 17) | clean 32 | 1.00 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.23/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | locks_instr@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | locks_signals@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_protected | correct | locks@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 61 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | locks_instr@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 61 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | locks_signals@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 61 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_still_valid | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 61 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | locks_s2text@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | locks_instr@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | locks_signals@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | inventory_still_valid | lease_then_tokenless | naive | locks@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | locks_instr@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | locks_signals@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | inventory_still_valid | lock_own_first | probe | locks@together | clean 32 | clean 32 | 1.00 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | locks_s2text@together | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | locks_instr@together | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | locks_signals@together | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | seat_same | naive | naive | locks@together | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | locks_s2text@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | locks_instr@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | locks_signals@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | seat_same | rereader | naive | locks@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | locks_instr@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | locks_signals@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.97/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.97/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.97/0.00 | 0 | yes |
| 2 | seat_same | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.97/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | locks_s2text@together | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | locks_instr@together | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | locks_signals@together | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | seat_same | naive_claim | naive | locks@together | clean 7, failed 25 (lost_update 25) | clean 32 | 0.89 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.11/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 76 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | locks_instr@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 76 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | locks_signals@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 76 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 76 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | locks_s2text@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 32 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | locks_instr@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 32 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | locks_signals@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 32 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | seat_same | lease_then_tokenless | naive | locks@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 32 (0) | 0 | 0.55/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | locks_instr@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | locks_signals@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | seat_same | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | locks_s2text@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | locks_instr@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | locks_signals@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | ticket_same | naive | naive | locks@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | locks_s2text@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | locks_instr@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | locks_signals@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | rereader | naive | locks@together | clean 16, failed 16 (lost_update 16) | clean 32 | 0.75 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | locks_instr@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | locks_signals@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 5 (5) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 0.98/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 4 (4) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | locks_s2text@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | locks_instr@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | locks_signals@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | ticket_same | naive_claim | naive | locks@together | clean 13, failed 19 (lost_update 19) | clean 32 | 0.80 | 2 (2) / 28 | - | 0 | 0 (0) | 0 | 0.20/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 70 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | locks_instr@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 70 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | locks_signals@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 70 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | ticket_same | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 7 (7) / 28 | 1.00/1.00/0.00 | 64 | 70 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | locks_s2text@together | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.53/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | locks_instr@together | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.53/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | locks_signals@together | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.53/0.00 | 0 | yes |
| 2 | ticket_same | lease_then_tokenless | naive | locks@together | clean 2, failed 30 (lost_update 30) | clean 32 | 0.97 | 7 (7) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.53/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | locks_instr@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | locks_signals@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | ticket_same | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 4 (4) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | locks_s2text@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.02/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | locks_instr@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.02/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | locks_signals@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.02/0.00 | 0 | yes |
| 2 | transfer_shared_source | naive | naive | locks@together | clean 1, failed 31 (lost_update 31) | clean 32 | 0.98 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.02/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | locks_s2text@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.05/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | locks_instr@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.05/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | locks_signals@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.05/0.00 | 0 | yes |
| 2 | transfer_shared_source | rereader | naive | locks@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.05/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | locks_instr@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | locks_signals@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | locks_instr@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | locks_signals@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 57 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | locks_instr@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | locks_signals@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lease_then_tokenless | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | locks_instr@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | locks_signals@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_shared_source | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | locks_s2text@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | locks_instr@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | locks_signals@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | naive | naive | locks@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | locks_s2text@together | clean 19, failed 13 (write_skew 13) | clean 32 | 0.70 | 7 (7) / 28 | - | 0 | 0 (0) | 0 | 0.30/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | locks_instr@together | clean 19, failed 13 (write_skew 13) | clean 32 | 0.70 | 7 (7) / 28 | - | 0 | 0 (0) | 0 | 0.30/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | locks_signals@together | clean 19, failed 13 (write_skew 13) | clean 32 | 0.70 | 7 (7) / 28 | - | 0 | 0 (0) | 0 | 0.30/0.00 | 0 | yes |
| 2 | budget_write_skew | rereader | naive | locks@together | clean 19, failed 13 (write_skew 13) | clean 32 | 0.70 | 7 (7) / 28 | - | 0 | 0 (0) | 0 | 0.30/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | locks_s2text@together | clean 17, compensated 15 | clean 32 | 0.50 | 19 (18) / 28 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | locks_instr@together | clean 17, compensated 15 | clean 32 | 0.50 | 19 (18) / 28 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | locks_signals@together | clean 17, compensated 15 | clean 32 | 0.50 | 19 (18) / 28 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | budget_write_skew | verify_and_compensate | correct | locks@together | clean 17, compensated 15 | clean 32 | 0.50 | 19 (18) / 28 | - | 0 | 0 (0) | 0 | 0.72/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | locks_instr@together | clean 32 | clean 32 | 0.50 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | locks_signals@together | clean 32 | clean 32 | 0.50 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | locks_s2text@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 6 (6) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | locks_instr@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 6 (6) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | locks_signals@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 6 (6) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_writes_only | naive | locks@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 6 (6) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 11 (11) / 28 | 1.00/1.00/n/a | 0 | 50 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 11 (11) / 28 | 1.00/1.00/n/a | 0 | 50 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 11 (11) / 28 | 1.00/1.00/n/a | 0 | 50 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 11 (11) / 28 | 1.00/1.00/n/a | 0 | 50 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 10 (10) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 10 (10) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 10 (10) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 10 (10) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | locks_s2text@together | clean 1, failed 31 (write_skew 31) | clean 32 | 0.98 | 15 (15) / 28 | 1.00/1.00/0.00 | 63 | 80 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | locks_instr@together | clean 1, failed 31 (write_skew 31) | clean 32 | 0.98 | 15 (15) / 28 | 1.00/1.00/0.00 | 63 | 80 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | locks_signals@together | clean 1, failed 31 (write_skew 31) | clean 32 | 0.98 | 15 (15) / 28 | 1.00/1.00/0.00 | 63 | 80 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | reacquire_no_reread | naive | locks@together | clean 1, failed 31 (write_skew 31) | clean 32 | 0.98 | 15 (15) / 28 | 1.00/1.00/0.00 | 63 | 80 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | locks_s2text@together | clean 3, failed 29 (write_skew 29) | clean 32 | 0.95 | 11 (11) / 28 | 1.00/1.00/0.00 | 0 | 50 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | locks_instr@together | clean 3, failed 29 (write_skew 29) | clean 32 | 0.95 | 11 (11) / 28 | 1.00/1.00/0.00 | 0 | 50 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | locks_signals@together | clean 3, failed 29 (write_skew 29) | clean 32 | 0.95 | 11 (11) / 28 | 1.00/1.00/0.00 | 0 | 50 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lease_then_tokenless | naive | locks@together | clean 3, failed 29 (write_skew 29) | clean 32 | 0.95 | 11 (11) / 28 | 1.00/1.00/0.00 | 0 | 50 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.03 | 13 (13) / 28 | 1.00/1.00/1.00 | 0 | 247 (220) | 30 | 0.97/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | locks_instr@together | clean 32 | clean 32 | 0.03 | 13 (13) / 28 | 1.00/1.00/1.00 | 0 | 247 (220) | 30 | 0.97/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | locks_signals@together | clean 32 | clean 32 | 0.03 | 13 (13) / 28 | 1.00/1.00/1.00 | 0 | 247 (220) | 30 | 0.97/0.00 | 0 | yes |
| 2 | budget_write_skew | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.03 | 13 (13) / 28 | 1.00/1.00/1.00 | 0 | 247 (220) | 30 | 0.97/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | locks_s2text@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | locks_instr@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | locks_signals@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | naive | naive | locks@together | clean 14, failed 18 (write_skew 18) | clean 32 | 0.78 | 3 (3) / 28 | - | 0 | 0 (0) | 0 | 0.22/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | locks_s2text@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | locks_instr@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | locks_signals@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | joint_account_write_skew | rereader | naive | locks@together | clean 17, failed 15 (write_skew 15) | clean 32 | 0.73 | 5 (5) / 28 | - | 0 | 0 (0) | 0 | 0.27/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | locks_s2text@together | clean 14, compensated 18 | clean 32 | 0.50 | 12 (10) / 28 | - | 0 | 0 (0) | 0 | 0.69/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | locks_instr@together | clean 14, compensated 18 | clean 32 | 0.50 | 12 (10) / 28 | - | 0 | 0 (0) | 0 | 0.69/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | locks_signals@together | clean 14, compensated 18 | clean 32 | 0.50 | 12 (10) / 28 | - | 0 | 0 (0) | 0 | 0.69/0.00 | 0 | yes |
| 2 | joint_account_write_skew | verify_and_compensate | correct | locks@together | clean 14, compensated 18 | clean 32 | 0.50 | 12 (10) / 28 | - | 0 | 0 (0) | 0 | 0.69/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 7 (7) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | locks_instr@together | clean 32 | clean 32 | 0.50 | 7 (7) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | locks_signals@together | clean 32 | clean 32 | 0.50 | 7 (7) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 7 (7) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | locks_s2text@together | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 5 (5) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | locks_instr@together | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 5 (5) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.25/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | locks_signals@together | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 5 (5) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.95/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_writes_only | naive | locks@together | clean 16, failed 16 (write_skew 16) | clean 32 | 0.75 | 5 (5) / 28 | 1.00/1.00/1.00 | 0 | 0 (0) | 0 | 0.95/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 47 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 47 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 47 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 47 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | locks_s2text@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 (11) / 28 | 1.00/1.00/0.00 | 64 | 79 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | locks_instr@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 (11) / 28 | 1.00/1.00/0.00 | 64 | 79 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | locks_signals@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 (11) / 28 | 1.00/1.00/0.00 | 64 | 79 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | reacquire_no_reread | naive | locks@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 11 (11) / 28 | 1.00/1.00/0.00 | 64 | 79 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | locks_s2text@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 9 (9) / 28 | 1.00/1.00/0.00 | 0 | 47 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | locks_instr@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 9 (9) / 28 | 1.00/1.00/0.00 | 0 | 47 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | locks_signals@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 9 (9) / 28 | 1.00/1.00/0.00 | 0 | 47 (0) | 0 | 0.75/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lease_then_tokenless | naive | locks@together | failed 32 (write_skew 32) | clean 32 | 1.00 | 9 (9) / 28 | 1.00/1.00/0.00 | 0 | 47 (0) | 0 | 0.75/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.38 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 186 (155) | 21 | 0.83/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | locks_instr@together | clean 32 | clean 32 | 0.38 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 186 (155) | 21 | 0.83/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | locks_signals@together | clean 32 | clean 32 | 0.38 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 186 (155) | 21 | 0.83/0.00 | 0 | yes |
| 2 | joint_account_write_skew | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.38 | 10 (10) / 28 | 1.00/1.00/1.00 | 0 | 186 (155) | 21 | 0.83/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | locks_s2text@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.05/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | locks_instr@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.05/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | locks_signals@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.05/0.00 | 0 | yes |
| 2 | transfer_same_amount | naive | naive | locks@together | clean 3, failed 29 (lost_update 29) | clean 32 | 0.95 | 4 (4) / 28 | - | 0 | 0 (0) | 0 | 0.05/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | locks_s2text@together | clean 8, failed 24 (lost_update 24) | clean 32 | 0.88 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.12/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | locks_instr@together | clean 8, failed 24 (lost_update 24) | clean 32 | 0.88 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.12/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | locks_signals@together | clean 8, failed 24 (lost_update 24) | clean 32 | 0.88 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.12/0.00 | 0 | yes |
| 2 | transfer_same_amount | rereader | naive | locks@together | clean 8, failed 24 (lost_update 24) | clean 32 | 0.88 | 6 (6) / 28 | - | 0 | 0 (0) | 0 | 0.12/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_protected | correct | locks_s2text@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_protected | correct | locks_instr@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_protected | correct | locks_signals@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_protected | correct | locks@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_short_lease | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_short_lease | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_short_lease | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_short_lease | probe | locks@together | clean 32 | clean 32 | 0.00 | 8 (8) / 28 | 1.00/1.00/n/a | 0 | 30 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_no_fence | probe | locks_s2text@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_no_fence | probe | locks_instr@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_no_fence | probe | locks_signals@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_no_fence | probe | locks@together | clean 32 | clean 32 | 0.00 | 7 (7) / 28 | 1.00/1.00/n/a | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | reacquire_no_reread | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 51 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | reacquire_no_reread | naive | locks_instr@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 51 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | reacquire_no_reread | naive | locks_signals@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 51 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | reacquire_no_reread | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 12 (12) / 28 | 1.00/1.00/0.00 | 128 | 51 (0) | 0 | 1.00/0.00 | 0 | yes |
| 2 | transfer_same_amount | lease_then_tokenless | naive | locks_s2text@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lease_then_tokenless | naive | locks_instr@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lease_then_tokenless | naive | locks_signals@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lease_then_tokenless | naive | locks@together | failed 32 (lost_update 32) | clean 32 | 1.00 | 10 (10) / 28 | 1.00/1.00/0.00 | 0 | 30 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_own_first | probe | locks_s2text@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_own_first | probe | locks_instr@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_own_first | probe | locks_signals@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |
| 2 | transfer_same_amount | lock_own_first | probe | locks@together | clean 32 | clean 32 | 0.50 | 8 (8) / 28 | 1.00/1.00/1.00 | 0 | 32 (0) | 0 | 0.50/0.00 | 0 | yes |

## Checker agreement (all validity episodes)

| | count |
|---|---|
| fs=False dsg=False | 13792 |
| fs=False dsg=True | 536 |
| fs=True dsg=True | 3592 |

All-reads DSG vs fs disagreement classes (definitional; see score7):

| policy | side | class | episodes |
|---|---|---|---|
| rereader | dsg_only | clean | 404 |
| verify_and_compensate | dsg_only | compensated | 132 |

### Three verdicts: fs, all-reads DSG, per-write basis DSG

| | count |
|---|---|
| fs=False dsg=False basis=False | 13792 |
| fs=False dsg=True basis=False | 468 |
| fs=False dsg=True basis=True | 68 |
| fs=True dsg=True basis=True | 3592 |

fs vs basis-DSG disagreements:

| policy | side | class | compensation_exposed | episodes |
|---|---|---|---|---|
| verify_and_compensate | basis_only | compensated | compensation_exposed | 68 |

## Write-skew protocol tail (n = 2, 8 instances x 50 schedules, contended)

| family | policy | config | outcomes | above 80 % of cap | cap endings | p95 | p99 | max / cap |
|---|---|---|---|---|---|---|---|---|
| budget_write_skew | verify_and_compensate | locks_s2text | clean 189, compensated 211 | 2/400 | 0 | 16 | 19 | 24 / 28 |
| budget_write_skew | verify_and_compensate | locks_instr | clean 189, compensated 211 | 2/400 | 0 | 16 | 19 | 24 / 28 |
| budget_write_skew | verify_and_compensate | locks_signals | clean 189, compensated 211 | 2/400 | 0 | 16 | 19 | 24 / 28 |
| budget_write_skew | verify_and_compensate | locks | clean 189, compensated 211 | 2/400 | 0 | 16 | 19 | 24 / 28 |
| budget_write_skew | lock_protected | locks_s2text | clean 400 | 0/400 | 0 | 10 | 10 | 10 / 28 |
| budget_write_skew | lock_protected | locks_instr | clean 400 | 0/400 | 0 | 10 | 10 | 10 / 28 |
| budget_write_skew | lock_protected | locks_signals | clean 400 | 0/400 | 0 | 10 | 10 | 10 / 28 |
| budget_write_skew | lock_protected | locks | clean 400 | 0/400 | 0 | 10 | 10 | 10 / 28 |
| joint_account_write_skew | verify_and_compensate | locks_s2text | clean 159, compensated 241 | 0/400 | 0 | 12 | 15 | 15 / 28 |
| joint_account_write_skew | verify_and_compensate | locks_instr | clean 159, compensated 241 | 0/400 | 0 | 12 | 15 | 15 / 28 |
| joint_account_write_skew | verify_and_compensate | locks_signals | clean 159, compensated 241 | 0/400 | 0 | 12 | 15 | 15 / 28 |
| joint_account_write_skew | verify_and_compensate | locks | clean 159, compensated 241 | 0/400 | 0 | 12 | 15 | 15 / 28 |
| joint_account_write_skew | lock_protected | locks_s2text | clean 400 | 0/400 | 0 | 7 | 7 | 7 / 28 |
| joint_account_write_skew | lock_protected | locks_instr | clean 400 | 0/400 | 0 | 7 | 7 | 7 / 28 |
| joint_account_write_skew | lock_protected | locks_signals | clean 400 | 0/400 | 0 | 7 | 7 | 7 / 28 |
| joint_account_write_skew | lock_protected | locks | clean 400 | 0/400 | 0 | 7 | 7 | 7 / 28 |

## Interleavings (naive policy, contended, n = 2, config none)

- **study4_together**: 256 episodes; first mover {'a1': 120, 'a0': 136}; every first read before every other agent's first write in 81%; 12 distinct patterns; top [('R0R1W0W1', 60), ('R1R0W1W0', 57), ('R1R0W0W1', 36), ('R0R1W1W0', 26), ('R1W1R0', 21)]; failure rate naive 0.699, rereader 0.578
- **study1_like**: 256 episodes; first mover {'a1': 138, 'a0': 118}; every first read before every other agent's first write in 100%; 4 distinct patterns; top [('R0R1W1W0', 71), ('R1R0W1W0', 67), ('R0R1W0W1', 63), ('R1R0W0W1', 55)]; failure rate naive 1.0, rereader 1.0
