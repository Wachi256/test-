"""Pre-market gap scanner: filter, enrich with news, print and save to JSON."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .benzinga import BenzingaClient
from .yahoo import PremarketQuote, YahooClient

log = logging.getLogger(__name__)
MARKET_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Criteria:
    min_gap_percent: float = 5.0
    min_price: float = 3.0
    min_premarket_volume: int = 50_000

    def matches(self, q: PremarketQuote) -> bool:
        return (
            q.gap_percent > self.min_gap_percent
            and q.price > self.min_price
            and q.premarket_volume > self.min_premarket_volume
        )


def scan(yahoo: YahooClient, benzinga: BenzingaClient, criteria: Criteria,
         watchlist: list[str] | None = None, workers: int = 8) -> list[dict]:
    symbols = yahoo.candidate_symbols(extra=watchlist or [])
    if not symbols:
        raise RuntimeError("No candidate tickers: Yahoo Finance unreachable and no watchlist")
    log.info("Checking %d candidate tickers", len(symbols))

    def fetch(sym: str) -> PremarketQuote | None:
        try:
            return yahoo.premarket_quote(sym)
        except (requests.RequestException, ValueError, KeyError) as exc:
            log.warning("Quote for %s failed: %s", sym, exc)
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        quotes = [q for q in pool.map(fetch, symbols) if q and criteria.matches(q)]
    quotes.sort(key=lambda q: q.gap_percent, reverse=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        catalysts = list(pool.map(lambda q: benzinga.catalyst(q.ticker), quotes))

    return [
        {
            "ticker": q.ticker,
            "price": round(q.price, 2),
            "previous_close": round(q.previous_close, 2),
            "gap_percent": round(q.gap_percent, 2),
            "premarket_volume": q.premarket_volume,
            "catalyst": c.sentence,
            "news_headline": c.headline,
            "news_url": c.url,
            "news_source": c.source,
        }
        for q, c in zip(quotes, catalysts)
    ]


def format_table(rows: list[dict], scan_date: str) -> str:
    header = f"PRE-MARKET GAP SCANNER — {scan_date}"
    if not rows:
        return f"{header}\nNo stocks matched the criteria."
    lines = [
        header,
        f"{'Ticker':<7} {'Price':>9} {'Gap %':>8}  Catalyst",
        "-" * 90,
    ]
    for r in rows:
        lines.append(
            f"{r['ticker']:<7} {'$' + format(r['price'], ',.2f'):>9} "
            f"{'+' + format(r['gap_percent'], '.2f') + '%':>8}  {r['catalyst']}"
        )
    lines.append(f"\n{len(rows)} stock(s) matched.")
    return "\n".join(lines)


def save_json(rows: list[dict], criteria: Criteria, out_dir: Path,
              now: datetime | None = None) -> Path:
    now = (now or datetime.now(MARKET_TZ)).astimezone(MARKET_TZ)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"premarket_scan_{now:%Y-%m-%d}.json"
    payload = {
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(timespec="seconds"),
        "criteria": {
            "min_gap_percent": criteria.min_gap_percent,
            "min_price": criteria.min_price,
            "min_premarket_volume": criteria.min_premarket_volume,
        },
        "count": len(rows),
        "results": rows,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
