"""Study 4 spend gate: no paid call before the OSF registration is confirmed archived.

The OSF registration is embargoed, so its API record is readable only when signed in. After filing, the OSF API record
of the registration (``GET https://api.osf.io/v2/registrations/<id>/``, read in the author's signed-in browser) is saved
byte for byte as ``.study4_osf_api.json`` next to ``src7/``, and ``.study4_registered`` is written with:

    osf: https://osf.io/<id>
    archiving: complete
    api_sha256: <sha256 of .study4_osf_api.json>
    checked_utc: <time of the API read>

:func:`check` refuses unless both files exist, the hash matches, and the saved record shows the registration with
``archiving`` false, not withdrawn, no pending approval, a ``date_registered``, a title naming Study 4, and an id that
is not one of the Study 1 to 3 registrations. ``run_conc_study4.sh``, ``run7.py`` and the batch driver call it before
any paid call (never in ``--dry-run``)::

    python3 src7/gate7.py            # prints OK or the reason, exit 0 or 3
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARKER = os.path.join(ROOT, ".study4_registered")
API_FILE = os.path.join(ROOT, ".study4_osf_api.json")
PRIOR_IDS = ("a5vec", "zj3an", "3pa4k")  # Studies 1, 2 and 3


def check(root: str = ROOT) -> List[str]:
    """Reasons to refuse (empty: the registration is confirmed archived)."""
    marker, api_file = os.path.join(root, ".study4_registered"), os.path.join(root, ".study4_osf_api.json")
    if not os.path.isfile(marker):
        return [".study4_registered is missing: Study 4 is not registered yet"]
    if not os.path.isfile(api_file):
        return [".study4_osf_api.json (the saved OSF API record) is missing"]
    lines = dict(ln.split(":", 1) for ln in open(marker).read().splitlines() if ":" in ln)
    lines = {k.strip(): v.strip() for k, v in lines.items()}
    bad: List[str] = []
    m = re.fullmatch(r"https://osf\.io/([a-z0-9]{5})/?", lines.get("osf", ""))
    if not m:
        return ["the marker has no 'osf: https://osf.io/<id>' line"]
    rid = m.group(1)
    if rid in PRIOR_IDS:
        bad.append(f"osf.io/{rid} is an earlier study's registration")
    if lines.get("archiving") != "complete":
        bad.append("the marker lacks 'archiving: complete'")
    raw = open(api_file, "rb").read()
    if lines.get("api_sha256") != hashlib.sha256(raw).hexdigest():
        bad.append("api_sha256 in the marker does not match .study4_osf_api.json")
    try:
        data = json.loads(raw)["data"]
        attr = data["attributes"]
    except Exception as e:  # noqa: BLE001
        return bad + [f".study4_osf_api.json is not an OSF registration record ({type(e).__name__})"]
    if data.get("id") != rid or data.get("type") != "registrations":
        bad.append(f"the saved record is {data.get('type')}/{data.get('id')}, not registrations/{rid}")
    if attr.get("archiving") is not False:
        bad.append(f"archiving is {attr.get('archiving')!r}, not false")
    for k in ("withdrawn", "pending_registration_approval", "pending_embargo_approval", "pending_withdrawal"):
        if attr.get(k):
            bad.append(f"{k} is true")
    if not attr.get("date_registered"):
        bad.append("no date_registered")
    if "Study 4" not in str(attr.get("title", "")):
        bad.append("the registration title does not name Study 4")
    return bad


def require(dry_run: bool) -> List[str]:
    """For the runners: nothing to check in a dry run."""
    return [] if dry_run else check()


def main() -> int:
    bad = check()
    if bad:
        print("REFUSING (no paid call): " + "; ".join(bad))
        return 3
    print("OK: the Study 4 registration is confirmed archived")
    return 0


if __name__ == "__main__":
    sys.exit(main())
