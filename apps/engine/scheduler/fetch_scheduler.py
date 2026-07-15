"""Automated historical-data fetcher.

Runs once per weekday AFTER market close and upserts OHLCV for every active stock,
so the backtest dataset stays fresh and intraday history accumulates over time
(yfinance caps 15m/5m to ~60 days per request; daily runs grow it past that).

Cadence is intentionally daily, not intraday: backtests only use completed bars,
and the current day's intraday candles are only whole after the 15:30 IST close.
Live signal generation fetches its own fresh candles separately (the scanner).

All knobs are env-driven:
  FETCH_RUN_HOUR_IST   (default 16)   hour (IST) to run the daily fetch
  FETCH_RUN_MINUTE_IST (default 0)    minute (IST)
  FETCH_TIMEFRAMES     (default 1D,15m,5m)
  FETCH_ON_START       (default true) also run once on container start (backfill)
"""
import os
import time
from datetime import datetime, time as dtime
import pytz
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

# Bring the engine package (db.client, routers.history) into scope.
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.client import engine
from routers.history import fetch_and_store

IST = pytz.timezone("Asia/Kolkata")

RUN_HOUR = int(os.getenv("FETCH_RUN_HOUR_IST", "16"))
RUN_MINUTE = int(os.getenv("FETCH_RUN_MINUTE_IST", "0"))
TIMEFRAMES = [t.strip() for t in os.getenv("FETCH_TIMEFRAMES", "1D,15m,5m").split(",") if t.strip()]
RUN_ON_START = os.getenv("FETCH_ON_START", "true").lower() != "false"
CHECK_INTERVAL = 60  # seconds between clock checks


def active_stocks():
    with engine.connect() as conn:
        rows = conn.execute(
            text('SELECT symbol FROM "Stock" WHERE "isActive" = true ORDER BY symbol ASC')
        ).fetchall()
    return [r[0] for r in rows]


def run_fetch(reason: str):
    symbols = active_stocks()
    now = datetime.now(IST)
    print(f"\n[{now:%Y-%m-%d %H:%M:%S} IST] 📥 Fetch run ({reason}) — "
          f"{len(symbols)} active stocks, timeframes {TIMEFRAMES}")
    ok = 0
    total_rows = 0
    for sym in symbols:
        try:
            res = fetch_and_store(sym, TIMEFRAMES)
            if "results" in res:
                rows = sum(v.get("rows", 0) for v in res["results"].values())
                total_rows += rows
                ok += 1
                print(f"   ✓ {sym}: {rows} rows")
            else:
                print(f"   ⚠️ {sym}: {res.get('error')}")
        except Exception as e:
            print(f"   ❌ {sym}: {e}")
    print(f"   Done: {ok}/{len(symbols)} stocks, {total_rows} rows upserted.")


def main():
    print("🗓️  Fetch scheduler started")
    print(f"   Daily run at {RUN_HOUR:02d}:{RUN_MINUTE:02d} IST (Mon–Fri); timeframes {TIMEFRAMES}")
    print(f"   Run-on-start backfill: {RUN_ON_START}")
    print("-" * 60)

    last_run_date = None
    if RUN_ON_START:
        try:
            run_fetch("startup backfill")
        except Exception as e:
            print(f"   startup fetch failed: {e}")
        # Only count the backfill as "today's run" if it happened at/after the
        # scheduled time. If it ran earlier, leave last_run_date=None so the
        # post-close scheduled run still fires today and captures complete bars.
        now = datetime.now(IST)
        if now.time() >= dtime(RUN_HOUR, RUN_MINUTE):
            last_run_date = now.date()

    while True:
        now = datetime.now(IST)
        is_weekday = now.weekday() < 5  # Mon=0 .. Fri=4
        due = now.time() >= dtime(RUN_HOUR, RUN_MINUTE)
        if is_weekday and due and last_run_date != now.date():
            try:
                run_fetch("scheduled daily")
            except Exception as e:
                print(f"   scheduled fetch failed: {e}")
            last_run_date = now.date()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
