"""CLI entry point: python -m premarket_scanner"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from .benzinga import BenzingaClient
from .scanner import MARKET_TZ, Criteria, format_table, save_json, scan
from .yahoo import YahooClient


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scan US stocks gapping up in pre-market.")
    p.add_argument("--min-gap", type=float, default=5.0, help="minimum gap %% (default 5)")
    p.add_argument("--min-price", type=float, default=3.0, help="minimum price $ (default 3)")
    p.add_argument("--min-volume", type=int, default=50_000,
                   help="minimum pre-market volume (default 50000)")
    p.add_argument("--watchlist", type=Path, help="extra tickers file, one per line")
    p.add_argument("--out-dir", type=Path, default=Path("results"))
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")

    watchlist = []
    if args.watchlist and args.watchlist.exists():
        watchlist = [ln.split("#")[0].strip() for ln in args.watchlist.read_text().splitlines()]
        watchlist = [t for t in watchlist if t]

    criteria = Criteria(args.min_gap, args.min_price, args.min_volume)
    try:
        rows = scan(YahooClient(), BenzingaClient(os.environ.get("BENZINGA_API_KEY")),
                    criteria, watchlist)
    except RuntimeError as exc:
        print(f"Scan failed: {exc}", file=sys.stderr)
        return 1

    now = datetime.now(MARKET_TZ)
    print(format_table(rows, now.strftime("%Y-%m-%d")))
    path = save_json(rows, criteria, args.out_dir, now)
    print(f"\nSaved to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
