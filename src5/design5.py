"""Study 2 design constants: configurations, scheduler defaults, the call cap.

Call cap (review T2 F3, T4 M7): Study 1 capped every agent at 12 executed tool calls at every n and config,
so no protective protocol fitted at n = 8 and the cap decided outcomes. Study 2 scales the cap with the
agent count and the configuration:

    call_cap(n, config) = 8 * n + 8 + (4 if the configuration offers locks else 0)
        n = 2: 24 (none, cas_available), 28 (locks, all_available)
        n = 4: 40 / 44

(V2, with a think gap before every completion: the protocols' worst cases at n = 2 on the validity seeds are 18
calls (verify_and_compensate) and 13 (promote_before_write); on a larger sample (8 instances x 50 schedules) their
livelock tail puts 0.25-2.3 % of write-skew episodes above 80 % of the cap and at most 0.25 % at it
(validity/validity.md, "tail"). At n = 4 the write-skew protocols thrash past any affordable cap, so Study 2 runs
write-skew templates at n = 2 only.)

It is validated by ``validity5.py``: every correct reference protocol must finish on every contended
template and control, in every Study 2 configuration that offers its primitive, using at most
``CAP_MARGIN`` (80 %) of the cap, over every instance and schedule of the validity run (README,
"Reference policy validity table"). The model loop allows ``cap + 1`` completions (the extra one tells
"wanted another call" from "finished"), exactly as in Study 1.
"""

from __future__ import annotations

from typing import Any, Dict

from world5 import CoordinationConfig, STUDY2_CONFIGS

CONFIGS = STUDY2_CONFIGS                 # none, cas_available, locks, all_available
CAP_MARGIN = 0.8
SCHEDULE_DEFAULTS: Dict[str, Any] = {"gap_min": 0, "gap_max": 4, "start_jitter": 6, "latency_p": 0.3, "latency_max": 2,
                                     "stall_rounds": 6, "max_rounds": 3000}
SCHEDULE_SPACE = "src5-schedule-v1"


def call_cap(n: int, config: str) -> int:
    """Executed tool calls allowed per agent (see module docstring)."""
    coord = CoordinationConfig.from_names(config)
    return 8 * n + 8 + (4 if coord.locks else 0)
