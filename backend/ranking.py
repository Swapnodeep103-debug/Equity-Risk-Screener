"""
ranking.py

Turns the raw per-ticker analysis results into something usable:
- a ranked list by composite score
- descriptive score bands (not "buy/sell" labels - see DISCLAIMER)
- price/budget tiers, so a user with a smaller per-share budget can see
  which higher-scoring names are actually affordable per share
- a risk-flagged view, combining quantitative flags and LLM-identified risks

None of this constitutes investment advice - it's a structured view of what
the scoring model computed, described in DISCLAIMER below.
"""

from typing import Dict, Any, List, Optional

DISCLAIMER = (
    "These groupings describe how each stock scored on the model's "
    "quantitative and qualitative criteria. They are not investment advice "
    "and not a recommendation to buy, hold, or sell any security. The "
    "scoring weights are hand-set and have not been backtested."
)


def rank_by_score(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    ranked = [{"ticker": t, **r} for t, r in results.items() if "score" in r]
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked


def bucket_by_score(results: Dict[str, Any]) -> Dict[str, List[str]]:
    bands = {
        "strong_score_70_100": [],
        "moderate_score_40_69": [],
        "weak_score_0_39": [],
        "excluded_insufficient_data": [],
    }
    for ticker, r in results.items():
        if "score" not in r:
            bands["excluded_insufficient_data"].append(ticker)
            continue
        score = r["score"]
        if score >= 70:
            bands["strong_score_70_100"].append(ticker)
        elif score >= 40:
            bands["moderate_score_40_69"].append(ticker)
        else:
            bands["weak_score_0_39"].append(ticker)
    return bands


def bucket_by_price_tier(results: Dict[str, Any], tiers: Optional[List[float]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Groups tickers by current share price (in target_currency) into budget
    tiers, e.g. tiers=[50, 200, 1000] -> "<=50", "50-200", "200-1000", ">1000".
    Useful for "what fits a smaller per-share budget" style views.
    """
    if not tiers:
        tiers = [50, 200, 1000]
    tiers = sorted(tiers)

    labels = [f"<={tiers[0]}"] + [f"{tiers[i]}-{tiers[i+1]}" for i in range(len(tiers) - 1)] + [f">{tiers[-1]}"]
    buckets: Dict[str, List[Dict[str, Any]]] = {label: [] for label in labels}
    buckets["unknown_price"] = []

    for ticker, r in results.items():
        if "score" not in r:
            continue
        price = r.get("fundamentals", {}).get("current_price")
        if price is None:
            buckets["unknown_price"].append({"ticker": ticker, "score": r["score"]})
            continue

        placed = False
        for i, cap in enumerate(tiers):
            if price <= cap:
                buckets[labels[i]].append({"ticker": ticker, "score": r["score"], "price": price})
                placed = True
                break
        if not placed:
            buckets[labels[-1]].append({"ticker": ticker, "score": r["score"], "price": price})

    for label in buckets:
        buckets[label].sort(key=lambda x: x["score"], reverse=True)

    return buckets


def flagged_for_risk(results: Dict[str, Any], min_flags: int = 1) -> List[Dict[str, Any]]:
    """Tickers with at least `min_flags` combined quantitative + LLM risk flags."""
    flagged = []
    for ticker, r in results.items():
        if "flags" not in r:
            continue
        flags = list(r["flags"])
        if r.get("llm_analysis"):
            flags += r["llm_analysis"].get("macro_adversities", [])
        if len(flags) >= min_flags:
            flagged.append({"ticker": ticker, "score": r.get("score"), "flags": flags})
    flagged.sort(key=lambda x: len(x["flags"]), reverse=True)
    return flagged


def build_report(results: Dict[str, Any], price_tiers: Optional[List[float]] = None) -> Dict[str, Any]:
    return {
        "disclaimer": DISCLAIMER,
        "ranked": rank_by_score(results),
        "score_bands": bucket_by_score(results),
        "price_tiers": bucket_by_price_tier(results, price_tiers),
        "risk_flagged": flagged_for_risk(results),
    }
