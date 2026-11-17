"""
fx.py

Currency conversion for comparing tickers listed in different currencies
(e.g. a USD ticker vs. an INR or EUR ticker). Uses Yahoo Finance's FX
tickers (format "FROMTO=X", e.g. "EURUSD=X") and caches rates so you're
not re-fetching the same pair on every ticker.

Limitations:
- Uses the latest available FX rate, not a rate matched to any specific
  historical date - fine for "what is this worth today" comparisons, not
  for point-in-time historical backtests across currencies.
- If Yahoo doesn't have the pair listed, get_rate() returns None and
  callers should treat the conversion as unavailable rather than guessing.
"""

from typing import Optional
import yfinance as yf

from cache import DiskCache


class FXConverter:
    def __init__(self, cache: Optional[DiskCache] = None, ttl_seconds: int = 3600):
        self.cache = cache or DiskCache(ttl_seconds=ttl_seconds)

    def get_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        if not from_currency or not to_currency:
            return None
        if from_currency == to_currency:
            return 1.0

        pair = f"{from_currency}{to_currency}=X"
        cache_key = f"fx_{pair}"

        def fetch() -> Optional[float]:
            try:
                hist = yf.Ticker(pair).history(period="5d")
                if hist is None or hist.empty:
                    return None
                return float(hist["Close"].dropna().iloc[-1])
            except Exception as e:
                print(f"[warn] FX fetch failed for {pair}: {e}")
                return None

        return self.cache.get_or_fetch(cache_key, fetch)

    def convert(self, amount: Optional[float], from_currency: str, to_currency: str) -> Optional[float]:
        """Returns None (not a guessed value) if amount is None or the rate
        couldn't be fetched, so callers can tell 'unknown' apart from 0."""
        if amount is None:
            return None
        rate = self.get_rate(from_currency, to_currency)
        if rate is None:
            return None
        return amount * rate
