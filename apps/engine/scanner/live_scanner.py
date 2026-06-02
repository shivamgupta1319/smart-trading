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
from strategies import STRATEGY_REGISTRY, STRATEGY_HOLD_DURATIONS

NESTJS_URL = os.getenv("NESTJS_SIGNAL_URL", "http://localhost:3000/api/signals/new")
IST = pytz.timezone("Asia/Kolkata")
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
POLL_INTERVAL = 100  # seconds


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
    period_map = {"1D": "150d", "15m": "10d", "5m": "5d"}

    interval = interval_map.get(timeframe, "15m")
    period = period_map.get(timeframe, "10d")

    df = yf.download(yf_symbol, period=period, interval=interval, progress=False, auto_adjust=True)
    if df.empty:
        return df

    # Use previous complete candle (not the currently forming one)
    df = df.iloc[:-1]
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    return df


def check_and_fire_signal(config, cache, last_fired_times):
    stock_id = config[1]
    strategy_name = config[2]
    timeframe = config[3]
    symbol = config[4]

    if strategy_name not in STRATEGY_REGISTRY:
        print(f"  [WARN] Unknown strategy: {strategy_name}")
        return

    strategy = STRATEGY_REGISTRY[strategy_name]

    try:
        cache_key = (symbol, timeframe)
        if cache_key not in cache:
            cache[cache_key] = fetch_live_candles(symbol, timeframe)
        df = cache[cache_key]
        
        if df.empty or len(df) < 30:
            print(f"  [INFO] {symbol}: insufficient data ({len(df)} bars)")
            return

        df = strategy.generate_signals(df)
        latest = df.iloc[-1]
        candle_time = latest.name

        if latest.get('signal', 0) == 0:
            print(f"  [INFO] {symbol} ({strategy_name}): No signal")
            return
            
        # Prevent duplicate signals for the exact same candle
        last_fired = last_fired_times.get(cache_key)
        if last_fired == candle_time:
            print(f"  [INFO] {symbol} ({strategy_name}): Signal already fired for this candle")
            return

        hold_duration = STRATEGY_HOLD_DURATIONS.get(strategy_name, "UNKNOWN")
        
        now = datetime.now()
        if hold_duration == "INTRADAY" and now.hour >= 15:
            print(f"  [INFO] {symbol} ({strategy_name}): Skipped INTRADAY signal after 3:00 PM")
            return

        signal_type = "BUY" if latest['signal'] == 1 else "SELL"
        payload = {
            "stockId": stock_id,
            "strategyName": strategy_name,
            "signalType": signal_type,
            "entryPrice": round(float(latest['Close']), 2),
            "stopLoss": round(float(latest.get('stop_loss', latest['Close'] * 0.98)), 2),
            "target": round(float(latest.get('target', latest['Close'] * 1.04)), 2),
            "holdDuration": STRATEGY_HOLD_DURATIONS.get(strategy_name, "UNKNOWN"),
        }

        print(f"  🚨 SIGNAL: {signal_type} {symbol} @ ₹{payload['entryPrice']} ({strategy_name})")
        response = httpx.post(NESTJS_URL, json=payload, timeout=10)
        print(f"  ✅ Posted to NestJS: {response.status_code}")
        
        # Mark this candle as fired
        last_fired_times[cache_key] = candle_time

    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")


def get_live_price(symbol: str) -> float:
    yf_symbol = symbol if symbol.endswith(".NS") else symbol + ".NS"
    try:
        ticker = yf.Ticker(yf_symbol)
        return ticker.fast_info.last_price
    except Exception as e:
        print(f"  [ERROR] fetching live price for {symbol}: {e}")
        return None

def auto_close_signals(cache):
    api_url = NESTJS_URL.replace("/signals/new", "/signals/active")
    now_time = datetime.now(IST).time()
    is_square_off_time = now_time >= dtime(15, 15)

    try:
        r = httpx.get(api_url, timeout=10)
        if r.status_code != 200:
            return
        active_signals = r.json()
        for sig in active_signals:
            symbol = sig.get('stock', {}).get('symbol') or sig.get('symbol')
            if not symbol:
                continue
            
            latest_price = get_live_price(symbol)
            if not latest_price:
                continue
            
            sl = float(sig['stopLoss'])
            tp = float(sig['target'])
            is_buy = sig['signalType'] == 'BUY'
            
            should_close = False
            exit_price = latest_price
            close_reason = ""

            if is_buy:
                if latest_price <= sl:
                    should_close = True
                    exit_price = sl
                    close_reason = f"hit Stop Loss (₹{sl})"
                elif latest_price >= tp:
                    should_close = True
                    exit_price = tp
                    close_reason = f"hit Target (₹{tp})"
            else:
                if latest_price >= sl:
                    should_close = True
                    exit_price = sl
                    close_reason = f"hit Stop Loss (₹{sl})"
                elif latest_price <= tp:
                    should_close = True
                    exit_price = tp
                    close_reason = f"hit Target (₹{tp})"
                    
            if not should_close and sig.get('holdDuration') == 'INTRADAY' and is_square_off_time:
                should_close = True
                exit_price = latest_price
                close_reason = "INTRADAY auto square-off (>= 15:15 IST)"
                    
            if (should_close):
                print(f"  🔒 AUTO-CLOSE {sig['signalType']} {symbol}: Price ₹{exit_price} {close_reason}")
                httpx.patch(f"{NESTJS_URL.replace('/signals/new', '/signals')}/{sig['id']}/close", json={"exitPrice": exit_price}, timeout=10)
    except Exception as e:
        print(f"  [ERROR] auto-closing signals: {e}")


def main():
    print("🚀 Live Scanner started")
    print(f"📡 Will POST signals to: {NESTJS_URL}")
    print(f"⏰ Market hours: {MARKET_OPEN} – {MARKET_CLOSE} IST")
    print("-" * 50)

    last_fired_times = {}

    while True:
        now = datetime.now(IST)
        print(f"\n[{now.strftime('%H:%M:%S')} IST] Scanning...")

        if not is_market_open():
            print("  Market is CLOSED. Sleeping 60s...")
            time.sleep(60)
            continue

        configs = get_active_configs()
        cache = {}
        
        # 1. Auto-close signals that hit SL/TP
        auto_close_signals(cache)
        
        # 2. Check for new setups
        if not configs:
            print("  No active configurations. Add some via the UI.")
        else:
            for config in configs:
                print(f"  Checking {config[4]} with {config[2]} ({config[3]})...")
                check_and_fire_signal(config, cache, last_fired_times)
                time.sleep(1)  # Brief pause between stocks

        print(f"  Done. Sleeping {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
