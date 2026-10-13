"""Yahoo Finance data access: candidate tickers and pre-market quotes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://query1.finance.yahoo.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (premarket-scanner)"}

# Yahoo predefined screeners used to build the candidate universe.
DEFAULT_SCREENERS = (
    "day_gainers",
    "small_cap_gainers",
    "most_actives",
    "aggressive_small_caps",
)

# Plain US tickers such as AAPL or BRK-B; excludes ^INDEX, futures (=F), crypto (BTC-USD).
US_SYMBOL = re.compile(r"[A-Z]{1,5}(-[A-Z])?")


@dataclass
class PremarketQuote:
    ticker: str
    price: float
    previous_close: float
    premarket_volume: int

    @property
    def gap_percent(self) -> float:
        return (self.price - self.previous_close) / self.previous_close * 100


class YahooClient:
    def __init__(self, session: requests.Session | None = None, timeout: float = 15):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(BASE_URL + path, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def screener_symbols(self, screener_id: str, count: int = 100) -> list[str]:
        data = self._get(
            "/v1/finance/screener/predefined/saved",
            {"scrIds": screener_id, "count": count},
        )
        results = (data.get("finance") or {}).get("result") or []
        return [q["symbol"] for r in results for q in r.get("quotes", []) if q.get("symbol")]

    def trending_symbols(self, region: str = "US") -> list[str]:
        data = self._get(f"/v1/finance/trending/{region}")
        results = (data.get("finance") or {}).get("result") or []
        return [q["symbol"] for r in results for q in r.get("quotes", []) if q.get("symbol")]

    def candidate_symbols(
        self,
        screeners: Iterable[str] = DEFAULT_SCREENERS,
        extra: Iterable[str] = (),
    ) -> list[str]:
        """Union of Yahoo screeners, trending tickers and a user watchlist."""
        symbols: list[str] = []
        sources = [lambda s=s: self.screener_symbols(s) for s in screeners]
        sources.append(self.trending_symbols)
        for fetch in sources:
            try:
                symbols.extend(fetch())
            except (requests.RequestException, ValueError, KeyError) as exc:
                log.warning("Yahoo candidate source failed: %s", exc)
        symbols.extend(extra)
        # Keep US common-stock style symbols only (skip indices, futures, crypto, FX).
        seen: dict[str, None] = {}
        for sym in symbols:
            sym = sym.strip().upper()
            if US_SYMBOL.fullmatch(sym):
                seen.setdefault(sym, None)
        return list(seen)

    def premarket_quote(self, ticker: str) -> PremarketQuote | None:
        """Build a pre-market snapshot from today's 1-minute chart incl. extended hours."""
        data = self._get(
            f"/v8/finance/chart/{ticker}",
            {"interval": "1m", "range": "1d", "includePrePost": "true"},
        )
        return parse_premarket_chart(ticker, data)


def parse_premarket_chart(ticker: str, data: dict) -> PremarketQuote | None:
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        return None
    result = results[0]
    meta = result.get("meta", {})
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    pre = (meta.get("currentTradingPeriod") or {}).get("pre") or {}
    start, end = pre.get("start"), pre.get("end")
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    if not prev_close or start is None or end is None:
        return None

    last_price = None
    total_volume = 0
    for ts, close, vol in zip(timestamps, closes, volumes):
        if not (start <= ts < end):
            continue
        if close is not None:
            last_price = close
        if vol:
            total_volume += int(vol)
    if last_price is None:
        return None
    return PremarketQuote(ticker, float(last_price), float(prev_close), total_volume)
