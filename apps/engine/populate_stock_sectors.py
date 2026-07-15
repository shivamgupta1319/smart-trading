"""Backfill Stock.sector for the tradeable universe so the portfolio risk engine can
bucket open positions by sector (previously everything was "Unknown" because only
NseStock carried a sector tag).

For each Stock row without a sector: reuse the NseStock tag if it's already populated,
otherwise pull `info["sector"]` from yfinance. Writes Stock.sector directly via the DB.

Run inside the engine container:
    docker exec smart-trading-v2-engine python populate_stock_sectors.py
"""
import time
import random
import logging

import yfinance as yf
from db.client import execute_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

_UNSET = ("", "Unknown", None)


def _pending_stocks():
    rows = execute_query(
        'SELECT id, symbol FROM "Stock" WHERE sector IS NULL OR sector = \'\' ORDER BY symbol'
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _nsestock_sector(symbol: str):
    row = execute_query(
        'SELECT sector FROM "NseStock" WHERE symbol = :s LIMIT 1', {"s": symbol}
    ).fetchone()
    if row and row[0] and row[0] not in _UNSET:
        return row[0]
    return None


def _yf_sector(symbol: str):
    try:
        info = yf.Ticker(f"{symbol}.NS").info
        sector = info.get("sector")
        return sector if sector else None
    except Exception as e:  # noqa: BLE001
        if "Rate limited" in str(e) or "429" in str(e):
            logging.warning(f"Rate limit hit at {symbol}. Sleeping 60s...")
            time.sleep(60)
        else:
            logging.error(f"yfinance lookup failed for {symbol}: {e}")
        return None


def _set_sector(symbol: str, sector: str):
    execute_query(
        'UPDATE "Stock" SET sector = :sec WHERE symbol = :s',
        {"sec": sector, "s": symbol},
    )


def main():
    pending = _pending_stocks()
    logging.info(f"Stocks missing sector: {len(pending)}")
    updated = 0
    for i, (_, symbol) in enumerate(pending):
        sector = _nsestock_sector(symbol) or _yf_sector(symbol) or "Unknown"
        _set_sector(symbol, sector)
        logging.info(f"[{i + 1}/{len(pending)}] {symbol} -> {sector}")
        updated += 1
        # Only sleep when we actually hit yfinance (NseStock reuse is free).
        time.sleep(random.uniform(0.3, 1.0))
    logging.info(f"Finished. Updated {updated} stocks.")


if __name__ == "__main__":
    main()
