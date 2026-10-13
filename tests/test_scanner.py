import json
from datetime import datetime

from premarket_scanner.benzinga import NO_CATALYST, BenzingaClient, one_sentence
from premarket_scanner.scanner import MARKET_TZ, Criteria, format_table, save_json, scan
from premarket_scanner.yahoo import PremarketQuote, YahooClient, parse_premarket_chart

PRE_START, PRE_END = 1_000, 2_000


def chart(prev_close, bars):
    """bars: list of (timestamp, close, volume)."""
    return {"chart": {"result": [{
        "meta": {"chartPreviousClose": prev_close,
                 "currentTradingPeriod": {"pre": {"start": PRE_START, "end": PRE_END}}},
        "timestamp": [b[0] for b in bars],
        "indicators": {"quote": [{"close": [b[1] for b in bars],
                                  "volume": [b[2] for b in bars]}]},
    }]}}


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.headers = {}

    def get(self, url, params=None, **kwargs):
        for key, data in self.routes.items():
            if key in url or (params and params.get("q") == key) or (
                    params and params.get("scrIds") == key):
                return FakeResponse(data(params) if callable(data) else data)
        raise AssertionError(f"unexpected url {url} {params}")


def test_parse_premarket_chart_uses_only_premarket_bars():
    data = chart(10.0, [(900, 9.0, 999_999), (1_100, 10.8, 30_000),
                        (1_200, None, 0), (1_500, 11.0, 25_000), (2_100, 12.0, 1)])
    q = parse_premarket_chart("ABC", data)
    assert q == PremarketQuote("ABC", 11.0, 10.0, 55_000)
    assert round(q.gap_percent, 2) == 10.0


def test_parse_premarket_chart_without_premarket_bars():
    assert parse_premarket_chart("ABC", chart(10.0, [(2_500, 11.0, 100)])) is None


def test_criteria_thresholds_are_strict():
    c = Criteria()
    assert c.matches(PremarketQuote("A", 10.6, 10.0, 50_001))
    assert not c.matches(PremarketQuote("A", 10.5, 10.0, 60_000))  # exactly 5%
    assert not c.matches(PremarketQuote("A", 3.0, 2.0, 60_000))     # price not > $3
    assert not c.matches(PremarketQuote("A", 12.0, 10.0, 50_000))   # volume not > 50k


def test_one_sentence():
    assert one_sentence("<p>Shares rise after FDA approval. More text.</p>") == \
        "Shares rise after FDA approval."
    assert one_sentence("Q3 beat on revenue") == "Q3 beat on revenue."
    assert one_sentence("") == ""


def test_scan_end_to_end(tmp_path):
    routes = {
        "day_gainers": {"finance": {"result": [{"quotes": [
            {"symbol": "GAP"}, {"symbol": "LOWV"}, {"symbol": "^GSPC"}, {"symbol": "BTC-USD"}]}]}},
        "small_cap_gainers": {"finance": {"result": [{"quotes": [{"symbol": "PENNY"}]}]}},
        "most_actives": {"finance": {"result": []}},
        "aggressive_small_caps": {"finance": {"result": []}},
        "/trending/": {"finance": {"result": [{"quotes": [{"symbol": "GAP"}]}]}},
        "/chart/GAP": chart(20.0, [(1_100, 23.0, 80_000)]),
        "/chart/LOWV": chart(20.0, [(1_100, 23.0, 10_000)]),
        "/chart/PENNY": chart(1.0, [(1_100, 2.0, 900_000)]),
        "/chart/BIG": chart(100.0, [(1_100, 106.0, 70_000)]),
        "GAP": {"news": [
            {"publisher": "Reuters", "title": "Ignored.", "providerPublishTime": 5},
            {"publisher": "Benzinga", "title": "GAP soars after earnings beat. Details inside",
             "link": "https://bz/1", "providerPublishTime": 4, "relatedTickers": ["GAP"]}]},
        "BIG": {"news": []},
    }
    session = FakeSession(routes)
    rows = scan(YahooClient(session), BenzingaClient(session=session), Criteria(),
                watchlist=["big"], workers=2)

    assert [r["ticker"] for r in rows] == ["GAP", "BIG"]  # sorted by gap desc
    assert rows[0]["gap_percent"] == 15.0
    assert rows[0]["catalyst"] == "GAP soars after earnings beat."
    assert rows[0]["news_source"] == "Benzinga via Yahoo Finance"
    assert rows[1]["catalyst"] == NO_CATALYST

    table = format_table(rows, "2026-10-13")
    assert "GAP" in table and "$23.00" in table and "+15.00%" in table

    path = save_json(rows, Criteria(), tmp_path, datetime(2026, 10, 13, 8, 30, tzinfo=MARKET_TZ))
    assert path.name == "premarket_scan_2026-10-13.json"
    saved = json.loads(path.read_text())
    assert saved["date"] == "2026-10-13" and saved["count"] == 2


def test_benzinga_api_preferred_when_key_set():
    session = FakeSession({"api.benzinga.com": [
        {"title": "XYZ jumps", "teaser": "XYZ wins $2B Navy contract. Shares up.",
         "url": "https://bz/2"}]})
    c = BenzingaClient("key", session=session).catalyst("XYZ")
    assert c.sentence == "XYZ wins $2B Navy contract."
    assert c.source == "Benzinga API"
