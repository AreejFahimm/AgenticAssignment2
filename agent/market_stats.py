"""Market price statistics (built by scripts/build_price_stats.py from the Kaggle datasets)."""
from __future__ import annotations

import json
from functools import lru_cache

from agent.config import ROOT


@lru_cache(maxsize=1)
def _stats() -> dict:
    p = ROOT / "data" / "processed" / "price_stats.json"
    return json.loads(p.read_text(encoding="utf-8"))["stats"] if p.exists() else {}


def market_band(skills: list[str], category: str | None, kind: str) -> dict | None:
    """Most specific band first (skill with n>=20), else category."""
    s = _stats()
    for key in [f"skill:{x}" for x in skills] + ([f"cat:{category}"] if category else []):
        b = s.get(key, {}).get(kind)
        if b and b["n"] >= 20:
            return dict(b, basis=key)
    return None
