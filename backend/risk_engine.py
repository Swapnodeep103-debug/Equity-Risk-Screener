"""
risk_engine.py

Computes time-series risk/return statistics for a price series, and combines
them with fundamentals (and optionally an LLM qualitative modifier) into a
single 0-100 composite score plus a list of human-readable risk flags.

The score is a heuristic, rule-based scoring model with hand-set weights.
It has NOT been backtested for predictive validity - treat it as a
transparent way to summarize the metrics below, not a proven signal.
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
from typing import Dict, Any


class QuantitativeRiskEngine:
    def __init__(self, risk_free_rate: float = 0.04):
        self.rf = risk_free_rate

    def evaluate_time_series(self, prices: pd.Series) -> Dict[str, float]:
        returns = prices.pct_change().dropna()
        if len(returns) < 30:
            return {}

        annual_return = returns.mean() * 252
        annual_volatility = returns.std() * np.sqrt(252)

        negative_returns = returns[returns < 0]
        downside_std = negative_returns.std() * np.sqrt(252) if len(negative_returns) > 0 else annual_volatility
        sortino = (annual_return - self.rf) / downside_std if downside_std > 0 else 0.0

        cum_returns = (1 + returns).cumprod()
        rolling_max = cum_returns.cummax()
        drawdowns = (cum_returns - rolling_max) / rolling_max
        max_drawdown = float(drawdowns.min())

        # Parametric 1-day 95% VaR, expressed as a positive expected-loss
        # magnitude: loss_threshold = -(mean - z * std). (The original version
        # of this code dropped the mean and wasn't signed as a loss.)
        var_95 = float(-(returns.mean() - norm.ppf(0.95) * returns.std()))

        insufficient_history = len(prices) < 200
        if insufficient_history:
            # Not enough history to trust a 200-day SMA - report neutral AND
            # say so explicitly, rather than let a NaN comparison silently
            # produce the same neutral value with no explanation.
            trend_score = 0.0
        else:
            sma_50 = prices.rolling(50).mean().iloc[-1]
            sma_200 = prices.rolling(200).mean().iloc[-1]
            latest_price = prices.iloc[-1]
            trend_score = 1.0 if latest_price > sma_50 > sma_200 else (
                -1.0 if latest_price < sma_50 < sma_200 else 0.0
            )

        return {
            "annual_return": annual_return,
            "annual_volatility": annual_volatility,
            "sortino": sortino,
            "max_drawdown": max_drawdown,
            "var_95": var_95,
            "trend_score": trend_score,
            "latest_price": float(prices.iloc[-1]),
            "insufficient_history": insufficient_history,
        }

    def compute_composite_score(
        self,
        quant_metrics: Dict[str, float],
        fundamentals: Dict[str, Any],
        qualitative_modifier: int = 0,
    ) -> "tuple[float, list]":
        score = 50.0
        flags = []

        if quant_metrics.get("insufficient_history"):
            flags.append("Less than 200 trading days of history - trend signal unreliable")

        if quant_metrics.get("trend_score", 0) == 1.0:
            score += 15
        elif quant_metrics.get("trend_score", 0) == -1.0:
            score -= 15
            flags.append("Sustained downward price trend below key SMAs")

        sortino = quant_metrics.get("sortino", 0)
        if sortino > 1.2:
            score += 15
        elif sortino < 0:
            score -= 15
            flags.append("Negative risk-adjusted returns (excess downside risk)")

        mdd = quant_metrics.get("max_drawdown", 0)
        if mdd < -0.40:
            score -= 15
            flags.append(f"High historical drawdown tail risk ({mdd:.1%})")
        elif mdd > -0.20:
            score += 10

        debt_equity = fundamentals.get("debt_to_equity")
        if debt_equity and debt_equity > 200:
            score -= 10
            flags.append(f"Elevated debt-to-equity ratio ({debt_equity:.1f})")

        rev_growth = fundamentals.get("revenue_growth")
        if rev_growth and rev_growth > 0.15:
            score += 10
        elif rev_growth and rev_growth < -0.05:
            score -= 10
            flags.append("Contracting top-line revenue")

        if fundamentals.get("currency_converted") and fundamentals.get("current_price") is None:
            flags.append("Currency conversion unavailable - price fields may be missing")

        score += qualitative_modifier

        return max(0.0, min(100.0, score)), flags
