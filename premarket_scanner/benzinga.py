"""Benzinga news catalysts, reduced to a one-sentence briefing per ticker."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

BENZINGA_NEWS_URL = "https://api.benzinga.com/api/v2/news"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
NO_CATALYST = "No recent Benzinga news catalyst found."


@dataclass
class Catalyst:
    sentence: str
    headline: str | None = None
    url: str | None = None
    source: str | None = None


def one_sentence(text: str, max_len: int = 220) -> str:
    """Strip HTML and return the first sentence, ending with a period."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text
    if len(sentence) > max_len:
        sentence = sentence[: max_len - 1].rsplit(" ", 1)[0] + "…"
    if sentence[-1] not in ".!?…":
        sentence += "."
    return sentence


class BenzingaClient:
    """Uses the Benzinga News API when a key is set, otherwise Benzinga
    articles syndicated on Yahoo Finance."""

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None,
                 timeout: float = 15):
        self.api_key = api_key
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "Mozilla/5.0 (premarket-scanner)")
        self.timeout = timeout

    def catalyst(self, ticker: str) -> Catalyst:
        fetchers = [self._from_benzinga_api] if self.api_key else []
        fetchers.append(self._from_yahoo_benzinga_feed)
        for fetch in fetchers:
            try:
                found = fetch(ticker)
            except (requests.RequestException, ValueError, KeyError) as exc:
                log.warning("Benzinga lookup for %s failed (%s): %s", ticker, fetch.__name__, exc)
                continue
            if found:
                return found
        return Catalyst(NO_CATALYST)

    def _from_benzinga_api(self, ticker: str) -> Catalyst | None:
        resp = self.session.get(
            BENZINGA_NEWS_URL,
            params={"token": self.api_key, "tickers": ticker, "pageSize": 5,
                    "sort": "created:desc", "displayOutput": "abstract"},
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        for item in resp.json() or []:
            title = item.get("title") or ""
            sentence = one_sentence(item.get("teaser") or "") or one_sentence(title)
            if sentence:
                return Catalyst(sentence, title or None, item.get("url"), "Benzinga API")
        return None

    def _from_yahoo_benzinga_feed(self, ticker: str) -> Catalyst | None:
        resp = self.session.get(
            YAHOO_SEARCH_URL,
            params={"q": ticker, "quotesCount": 0, "newsCount": 15},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        news = resp.json().get("news") or []
        news.sort(key=lambda n: n.get("providerPublishTime") or 0, reverse=True)
        for item in news:
            if "benzinga" not in (item.get("publisher") or "").lower():
                continue
            related = item.get("relatedTickers")
            if related and ticker not in related:
                continue
            title = item.get("title") or ""
            if title:
                return Catalyst(one_sentence(title), title, item.get("link"), "Benzinga via Yahoo Finance")
        return None
