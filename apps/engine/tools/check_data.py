"""Check every active stock's stored candles and refresh its "needs review" mark.

    python tools/check_data.py            # report, and update Stock.dataFlag
    python tools/check_data.py --repair TRENT,XYZ   # first re-download those stocks' daily
                                                      # history in full (fixes a series
                                                      # stitched across a split)

For each stock it prints rows that would be left out by the candle checks (they are only
counted here; nothing is deleted) and every daily move above 20% that nobody has reviewed
in config/known_price_actions.json.
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_checks import clean_candles  # noqa: E402
from db.client import engine  # noqa: E402
from routers.history import fetch_and_store, update_data_flag  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repair", default="", help="comma-separated symbols to re-download in full (daily)")
    args = ap.parse_args()

    for symbol in [s.strip().upper() for s in args.repair.split(",") if s.strip()]:
        res = fetch_and_store(symbol, ["1D"], incremental=False)
        print(f"repair {symbol}: {res.get('results', res)}")

    with engine.connect() as conn:
        stocks = conn.execute(text('SELECT id, symbol FROM "Stock" WHERE "isActive" ORDER BY symbol')).fetchall()
    flagged = 0
    for stock_id, symbol in stocks:
        notes = []
        for tf in ("1D", "15m", "5m"):
            with engine.connect() as conn:
                rows = conn.execute(text(
                    'SELECT timestamp, open, high, low, close, volume FROM "HistoricalData" '
                    'WHERE "stockId" = :sid AND timeframe = :tf ORDER BY timestamp'
                ), {"sid": stock_id, "tf": tf}).fetchall()
            if not rows:
                notes.append(f"{tf}: no candles")
                continue
            df = pd.DataFrame(rows, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            _, problems = clean_candles(df.set_index("timestamp"), tf)
            notes += [f"{tf} {p}" for p in problems]
        jumps = update_data_flag(stock_id, symbol)
        if jumps:
            flagged += 1
            notes.append("NEEDS REVIEW: " + "; ".join(jumps))
        if notes:
            print(f"{symbol}: " + " | ".join(notes))
    print(f"{len(stocks)} stocks checked, {flagged} need a price move reviewed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
