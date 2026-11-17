"""
orchestrator.py

Top-level entry point that runs the full analysis for a list of tickers:

  EquitiesDataPipeline -> QuantitativeRiskEngine -> LLMAdversityAnalyzer
                                                 -> ranking.build_report

See README.md for usage and important limitations/disclaimers.
"""

import json
from typing import Dict, Any, List, Optional

from data_pipeline import EquitiesDataPipeline
from risk_engine import QuantitativeRiskEngine
from llm_analyzer import LLMAdversityAnalyzer
import ranking


class StockAnalysisOrchestrator:
    def __init__(
        self,
        target_currency: str = "USD",
        risk_free_rate: float = 0.04,
        llm_model: str = "gemma3:4b",
        cache_ttl_seconds: int = 3600,
    ):
        self.pipeline = EquitiesDataPipeline(target_currency, cache_ttl_seconds=cache_ttl_seconds)
        self.risk_engine = QuantitativeRiskEngine(risk_free_rate)
        self.llm = LLMAdversityAnalyzer(llm_model)

    def analyze(self, tickers: List[str], period: str = "3y", use_llm: bool = True) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        price_data = self.pipeline.fetch_historical_prices(tickers, period=period)

        for ticker in tickers:
            df = price_data.get(ticker)
            if df is None or "Close" not in df.columns:
                results[ticker] = {"error": "no price data available"}
                continue

            fundamentals = self.pipeline.fetch_fundamentals(ticker)
            quant_metrics = self.risk_engine.evaluate_time_series(df["Close"])

            if not quant_metrics:
                results[ticker] = {"error": "insufficient price history for analysis"}
                continue

            # First pass (no qualitative modifier yet) just to generate flags
            # that get handed to the LLM as context.
            _, quant_flags = self.risk_engine.compute_composite_score(quant_metrics, fundamentals)

            qualitative_modifier = 0
            llm_result: Optional[dict] = None
            if use_llm:
                llm_result = self.llm.analyze_company_risks(ticker, fundamentals, quant_flags)
                qualitative_modifier = llm_result.get("qualitative_score_modifier", 0)

            final_score, flags = self.risk_engine.compute_composite_score(
                quant_metrics, fundamentals, qualitative_modifier
            )

            results[ticker] = {
                "score": final_score,
                "flags": flags,
                "quant_metrics": quant_metrics,
                "fundamentals": fundamentals,
                "llm_analysis": llm_result,
            }

        return results

    def analyze_and_report(
        self, tickers: List[str], period: str = "3y", use_llm: bool = True, price_tiers: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        results = self.analyze(tickers, period=period, use_llm=use_llm)
        return ranking.build_report(results, price_tiers=price_tiers)


if __name__ == "__main__":
    orchestrator = StockAnalysisOrchestrator(target_currency="USD")
    report = orchestrator.analyze_and_report(
        ["AAPL", "MSFT", "TSLA"], period="3y", use_llm=False, price_tiers=[100, 300]
    )
    print(json.dumps(report, indent=2, default=str))
