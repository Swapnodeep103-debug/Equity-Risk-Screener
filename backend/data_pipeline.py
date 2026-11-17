"""
data_pipeline.py

Fetches price history and fundamentals from yfinance, with:
- disk caching (avoids re-hitting Yahoo on every run / rate limits)
- per-ticker error handling (one bad ticker doesn't kill a batch run)
- currency conversion for price-like fields, via FXConverter
"""

import yfinance as yf
import pandas as pd
from typing import Dict, Any, List

from cache import DiskCache
from fx import FXConverter


class EquitiesDataPipeline:
    def __init__(self, target_currency: str = "USD", cache_ttl_seconds: int = 3600):
        self.target_currency = target_currency
        self.cache = DiskCache(ttl_seconds=cache_ttl_seconds)
        self.fx = FXConverter(cache=self.cache)

    def fetch_historical_prices(self, tickers: List[str], period: str = "3y") -> Dict[str, pd.DataFrame]:
        data = {}
        for ticker in tickers:
            cache_key = f"prices_{ticker}_{period}"
            df = self.cache.get(cache_key)

            if df is None:
                try:
                    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
                except Exception as e:
                    print(f"[warn] price fetch failed for {ticker}: {e}")
                    continue

                if df is None or df.empty:
                    print(f"[warn] no price data returned for {ticker}")
                    continue

                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                self.cache.set(cache_key, df)

            data[ticker] = df
        return data

    def fetch_fundamentals(self, ticker: str) -> Dict[str, Any]:
        cache_key = f"fundamentals_{ticker}"
        info = self.cache.get(cache_key)

        if info is None:
            try:
                info = yf.Ticker(ticker).info or {}
            except Exception as e:
                print(f"[warn] fundamentals fetch failed for {ticker}: {e}")
                info = {}
            # Only cache a successful, non-empty result. Caching {} here would
            # mean a transient failure (rate limit, network blip) gets treated
            # as a confirmed "no data" for the full TTL, blocking retries.
            if info:
                self.cache.set(cache_key, info)

        native_currency = info.get("currency", self.target_currency)
        needs_conversion = native_currency != self.target_currency

        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        target_price = info.get("targetMeanPrice")
        free_cashflow = info.get("freeCashflow")

        def maybe_convert(amount):
            if not needs_conversion:
                return amount
            return self.fx.convert(amount, native_currency, self.target_currency)

        return {
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            # Ratios below are unit-less / already comparable across currencies,
            # so they are NOT converted - only monetary amounts and prices are.
            "debt_to_equity": info.get("debtToEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margins": info.get("profitMargins"),
            "beta": info.get("beta", 1.0),
            "short_ratio": info.get("shortRatio", 0.0),
            "native_currency": native_currency,
            "target_currency": self.target_currency,
            "currency_converted": needs_conversion,
            "free_cashflow": maybe_convert(free_cashflow),
            "free_cashflow_native": free_cashflow,
            "target_price": maybe_convert(target_price),
            "target_price_native": target_price,
            "current_price": maybe_convert(current_price),
            "current_price_native": current_price,
        }
