"""Decision node + Pricing Strategist. Rules and thresholds come from config.yaml (no hard-coded policy)."""
from __future__ import annotations

import json
import time

from agent.config import ROOT, load_config
from agent.handoffs import BidDecision, PriceQuote
from agent.market_stats import market_band
from agent.runtime import rt_of, tr


def _profile(persona: str) -> dict:
    return json.loads((ROOT / "data" / "personas" / persona / "profile.json").read_text(encoding="utf-8"))


async def decide(state, config):
    t, cfg = time.time(), load_config()
    risk, fit, spec = state["risk_report"], state["fit_report"], state["job_spec"]
    th, reasons = cfg["thresholds"], []
    action = "bid"
    if risk["scam"] or risk["score"] > th["maximum_risk_score"]:
        action, reasons = "skip", [f"risk {risk['score']:.2f}: {', '.join(risk['flags']) or 'high risk'}"]
    elif fit["score"] < th["skip_if_fit_below"] or fit["refused"]:
        action, reasons = "skip", [f"fit {fit['score']:.2f} below {th['skip_if_fit_below']} (no supporting evidence)" if fit["refused"] else f"fit {fit['score']:.2f} below {th['skip_if_fit_below']}"]
    elif fit["score"] < th["minimum_fit_score"]:
        action, reasons = "watch", [f"fit {fit['score']:.2f} in watch band"]
    else:
        prof = _profile(state["persona"])
        top = spec.get("budget_max") or spec.get("budget_min") or 0
        floor = prof["hourly_rate_usd"] * cfg["pricing"]["floor_hourly_multiplier"] if spec["budget_type"] == "hourly" else prof["minimum_project_budget_usd"]
        if top and top < floor:
            action, reasons = "skip", [f"budget {top} below floor {floor:.0f}"]
        else:
            reasons = [f"fit {fit['score']:.2f}, risk {risk['score']:.2f}", *fit["reasons"]]
    d = BidDecision(action=action, reasons=reasons, fit_score=fit["score"], risk_score=risk["score"])
    status = {"skip": "skipped", "watch": "watching", "bid": "running"}[action]
    return dict(decision=d.model_dump(), status=status, steps=1, trace=[tr("decide", t, action=action)])


async def pricing(state, config):
    t, rt, cfg = time.time(), rt_of(config), load_config()
    pc, spec, job = cfg["pricing"], state["job_spec"], state["job"]
    prof = _profile(state["persona"])
    kind = "hourly" if spec["budget_type"] == "hourly" else "fixed"
    band = market_band(spec["required_skills"], spec.get("category"), kind)
    client_spend = 0
    if job.get("client_id"):
        try:
            h = await rt.hub.call("risk_assessor", "marketplace.get_client_history", {"client_id": job["client_id"]}, user=state["user_id"])
            client_spend = h.get("total_spent_usd", 0)
        except Exception:  # noqa: BLE001 pricing degrades to market-only
            pass
    pct = pc["high_spend_percentile"] if client_spend >= pc["high_spend_client_usd"] else pc["default_bid_percentile"]
    floor = prof["hourly_rate_usd"] * pc["floor_hourly_multiplier"] if kind == "hourly" else prof["minimum_project_budget_usd"]
    if band:
        target = band["p25"] + (band["p75"] - band["p25"]) * pct * 2 if pct <= 0.5 else band["median"] + (band["p75"] - band["median"]) * (pct - 0.5) * 2
    else:
        target = floor * 1.2
    cap = spec.get("budget_max")
    bid = max(target, floor)
    if cap:
        bid = min(bid, cap)
        bid = max(bid, min(floor, cap))
    bid = round(bid, 2)
    connects = int(job.get("connects_cost") or 0)
    value = (0.1 + 0.4 * state["fit_report"]["score"]) * (cap or bid * 10 if kind == "fixed" else bid * 20)
    ev_ratio = value / max(connects * 0.15, 0.01)  # ~$0.15 per Connect
    worth = connects <= pc["max_connects_per_bid"] and ev_ratio >= pc["min_expected_value_ratio"]
    q = PriceQuote(bid_amount=max(bid, 1.0), band_low=band["p25"] if band else None, band_high=band["p75"] if band else None,
                   connects_cost=connects, worth_connects=worth,
                   rationale=(f"{kind} bid at market {int(pct*100)}th pct of {band['basis']} (n={band['n']}) clamped to floor {floor:.0f}"
                              if band else "no market data; floor x1.2") + f"; Connects {connects} (cap {pc['max_connects_per_bid']}), EV ratio {ev_ratio:.1f}")
    out = dict(price_quote=q.model_dump(), steps=1, trace=[tr("pricing", t, bid=q.bid_amount, connects=connects, worth=worth)])
    if not worth:
        out.update(status="skipped", decision=dict(state["decision"], action="skip", reasons=state["decision"]["reasons"] + [f"Connects not worth it: cost {connects} / cap {pc['max_connects_per_bid']}, EV ratio {ev_ratio:.1f}"]))
    return out
