"""Live Scanner — polls yfinance every 60s during NSE market hours and fires signals."""
import os
import time
import httpx
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime, time as dtime
import pytz
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

# Bring db engine in scope
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.client import engine
from strategies import STRATEGY_REGISTRY

NESTJS_URL = os.getenv("NESTJS_SIGNAL_URL", "http://localhost:3000/api/signals/new")
IST = pytz.timezone("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
POLL_INTERVAL = 60  # seconds


def is_market_open() -> bool:
    now = datetime.now(IST).time()
    weekday = datetime.now(IST).weekday()
    return weekday < 5 and MARKET_OPEN <= now <= MARKET_CLOSE


def get_active_configs():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT ac.id, ac."stockId", ac."strategyName", ac.timeframe, s.symbol
            FROM "ActiveConfiguration" ac
            JOIN "Stock" s ON s.id = ac."stockId"
            WHERE s."isActive" = true
        """)).fetchall()
    return rows


def fetch_live_candles(symbol: str, timeframe: str) -> pd.DataFrame:
    yf_symbol = symbol if symbol.endswith(".NS") else symbol + ".NS"
    interval_map = {"1D": "1d", "15m": "15m", "5m": "5m"}
    period_map = {"1D": "60d", "15m": "5d", "5m": "2d"}

    interval = interval_map.get(timeframe, "15m")
    period = period_map.get(timeframe, "5d")

    df = yf.download(yf_symbol, period=period, interval=interval, progress=False, auto_adjust=True)
    if df.empty:
        return df

    # Use previous complete candle (not the currently forming one)
    df = df.iloc[:-1]
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    return df


def check_and_fire_signal(config):
    stock_id = config[1]
    strategy_name = config[2]
    timeframe = config[3]
    symbol = config[4]

    if strategy_name not in STRATEGY_REGISTRY:
        print(f"  [WARN] Unknown strategy: {strategy_name}")
        return

    strategy = STRATEGY_REGISTRY[strategy_name]

    try:
        df = fetch_live_candles(symbol, timeframe)
        if df.empty or len(df) < 30:
            print(f"  [INFO] {symbol}: insufficient data ({len(df)} bars)")
            return

        df = strategy.generate_signals(df)
        latest = df.iloc[-1]

        if latest.get('signal', 0) == 0:
            print(f"  [INFO] {symbol} ({strategy_name}): No signal")
            return

        signal_type = "BUY" if latest['signal'] == 1 else "SELL"
        payload = {
            "stockId": stock_id,
            "strategyName": strategy_name,
            "signalType": signal_type,
            "entryPrice": round(float(latest['Close']), 2),
            "stopLoss": round(float(latest.get('stop_loss', latest['Close'] * 0.98)), 2),
            "target": round(float(latest.get('target', latest['Close'] * 1.04)), 2),
        }

        print(f"  🚨 SIGNAL: {signal_type} {symbol} @ ₹{payload['entryPrice']} ({strategy_name})")
        response = httpx.post(NESTJS_URL, json=payload, timeout=10)
        print(f"  ✅ Posted to NestJS: {response.status_code}")

    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")


def main():
    print("🚀 Live Scanner started")
    print(f"📡 Will POST signals to: {NESTJS_URL}")
    print(f"⏰ Market hours: {MARKET_OPEN} – {MARKET_CLOSE} IST")
    print("-" * 50)

    while True:
        now = datetime.now(IST)
        print(f"\n[{now.strftime('%H:%M:%S')} IST] Scanning...")

        if not is_market_open():
            print("  Market is CLOSED. Sleeping 60s...")
            time.sleep(60)
            continue

        configs = get_active_configs()
        if not configs:
            print("  No active configurations. Add some via the UI.")
        else:
            for config in configs:
                print(f"  Checking {config[4]} with {config[2]} ({config[3]})...")
                check_and_fire_signal(config)
                time.sleep(1)  # Brief pause between stocks

        print(f"  Done. Sleeping {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
