"""Spend accounting across every spend log, with a total cap and per-provider-family caps (Study 3, src6).

Derived from src5/budget5.py; only the families and the default caps changed (plan6.py, registration "Starting and
stopping rules"):

    anthropic  (Claude Haiku 4.5, Claude Sonnet 5; Message Batches)   default cap  $29.50
    openrouter (Qwen3.6-27B; sync, routed to Alibaba)                  default cap  $15.50
    total                                                              default cap  $45  (approved budget $50)

A spend entry's family is its ``provider_family`` field (written by model_agent6 and the batch driver), or, for
older entries, derived from its ``model``. Every runner (run6, the batch driver) reads *all* logs named on its
command line plus its own, so one set of caps spans every output directory.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Iterable, Mapping, Optional

from model_agent6 import BudgetExceeded, SpendTracker, provider_family

FAMILIES = ("anthropic", "openrouter")
DEFAULT_FAMILY_CAPS: Dict[str, float] = {"anthropic": 29.5, "openrouter": 15.5}
DEFAULT_TOTAL_CAP = 45.0


def entry_family(e: Mapping) -> str:
    return e.get("provider_family") or provider_family(str(e.get("model", "")))


def spend_by_model(paths: Iterable[str]) -> Dict[str, float]:
    """Spend per model id over every log."""
    return _accumulate(paths, lambda e: str(e.get("model", "")))


def spend_by_family(paths: Iterable[str]) -> Dict[str, float]:
    return _accumulate(paths, entry_family, init={f: 0.0 for f in FAMILIES})


def _accumulate(paths: Iterable[str], key, init: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    out: Dict[str, float] = dict(init or {})
    seen = set()
    for p in paths:
        ap = os.path.abspath(p)
        if ap in seen or not os.path.exists(ap):
            continue
        seen.add(ap)
        with open(ap) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                k = key(e)
                out[k] = out.get(k, 0.0) + float(e.get("cost_usd") or 0.0)
    return out


def parse_family_caps(specs: Iterable[str]) -> Dict[str, float]:
    caps = dict(DEFAULT_FAMILY_CAPS)
    for s in specs:
        if not s:
            continue
        k, _, v = s.partition("=")
        if k not in FAMILIES:
            raise SystemExit(f"unknown provider family {k!r} in --family-cap (known: {FAMILIES})")
        caps[k] = float(v)
    return caps


class Budget:
    """Total cap, per-family caps and an optional per-model cap (``model_cap`` USD for ``model``, counted over every
    log): the runner gives each model's core block a sub-cap so one expensive model cannot use up the core budget
    of the cheaper models in its family."""

    def __init__(self, total_cap: Optional[float], family_caps: Mapping[str, float], model: Optional[str] = None,
                 model_cap: Optional[float] = None) -> None:
        self.total_cap = total_cap
        self.family_caps = dict(family_caps)
        self.model = model
        self.model_cap = model_cap
        self.model_spent = 0.0

    def left(self, family: str, spent: Mapping[str, float]) -> float:
        tot = sum(spent.get(f, 0.0) for f in FAMILIES)
        lefts = [float("inf")]
        if self.total_cap is not None:
            lefts.append(self.total_cap - tot)
        if family in self.family_caps:
            lefts.append(self.family_caps[family] - spent.get(family, 0.0))
        if self.model_cap is not None:
            lefts.append(self.model_cap - self.model_spent)
        return min(lefts)

    def refresh_model(self, paths: Iterable[str]) -> None:
        if self.model is not None:
            self.model_spent = spend_by_model(paths).get(self.model, 0.0)

    def describe(self, spent: Mapping[str, float]) -> str:
        parts = [f"{f} ${spent.get(f, 0.0):.4f}/${self.family_caps.get(f, float('inf')):.2f}" for f in FAMILIES]
        tot = f"total ${sum(spent.values()):.4f}" + (f"/${self.total_cap:.2f}" if self.total_cap is not None else "")
        return "; ".join(parts + [tot])


class BudgetTracker(SpendTracker):
    """The frozen-style SpendTracker for this directory's log, raising BudgetExceeded when the entry's family
    cap or the total cap (counting every other log too) is passed."""

    def __init__(self, path: Optional[str], other_logs: Iterable[str], budget: Budget) -> None:
        super().__init__(path, None)
        self.budget = budget
        self.base = spend_by_family([p for p in other_logs if not path or os.path.abspath(p) != os.path.abspath(path)])
        own = spend_by_family([path]) if path else {}
        self.fam = {f: self.base.get(f, 0.0) + own.get(f, 0.0) for f in FAMILIES}
        budget.refresh_model(list(other_logs) + ([path] if path else []))

    def spent(self) -> Dict[str, float]:
        return dict(self.fam)

    def record(self, entry) -> None:
        fam = entry_family(entry)
        self.fam[fam] = self.fam.get(fam, 0.0) + float(entry.get("cost_usd") or 0.0)
        if self.budget.model is not None and entry.get("model") == self.budget.model:
            self.budget.model_spent += float(entry.get("cost_usd") or 0.0)
        super().record(entry)
        if self.budget.left(fam, self.fam) < 0:
            raise BudgetExceeded(f"spend passed a cap: {self.budget.describe(self.fam)}")
