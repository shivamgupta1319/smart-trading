"""Live Scanner — polls yfinance every 60s during NSE market hours and fires signals.

Implements a 3-Layer Smart Exit System:
  Layer 1 (Breakeven):    At 50% of target distance → SL moves to entry price
  Layer 2 (Profit Lock):  At 75% of target distance → SL locks 40% of unrealized profit
  Layer 3 (Reversal):     At 60%+ of target distance → detect reversal candle patterns → exit early
"""
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

# ── Smart Trailing SL Configuration ──
BREAKEVEN_THRESHOLD = 0.50   # Move SL to breakeven at 50% of target distance
PROFIT_LOCK_THRESHOLD = 0.75 # Lock profit at 75% of target distance
PROFIT_LOCK_PERCENT = 0.40   # Lock 40% of unrealized profit
REVERSAL_ZONE_START = 0.60   # Start checking for reversals at 60% of target distance

# Track trailing state per signal to avoid redundant API calls
# {signal_id: "INITIAL" | "BREAKEVEN" | "PROFIT_LOCK"}
trailing_state_cache = {}


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


def get_recent_candles(symbol: str, n: int = 10) -> pd.DataFrame:
    """Fetch the most recent N completed candles for reversal detection."""
    yf_symbol = symbol if symbol.endswith(".NS") else symbol + ".NS"
    try:
        df = yf.download(yf_symbol, period="5d", interval="15m", progress=False, auto_adjust=True)
        if df.empty:
            return df
        df = df.iloc[:-1]  # Exclude currently forming candle
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        return df.tail(n)
    except Exception as e:
        print(f"  [ERROR] fetching recent candles for {symbol}: {e}")
        return pd.DataFrame()


def detect_reversal(df: pd.DataFrame, is_buy: bool) -> tuple[bool, str]:
    """
    Detect reversal patterns in recent candles.
    Returns (is_reversal, reason_string).
    
    Checks for:
    1. Bearish/Bullish Engulfing
    2. Pin bar / long wick rejection
    3. RSI divergence (price new high but RSI lower)
    4. Volume spike + opposite direction candle
    """
    if df.empty or len(df) < 3:
        return False, ""

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    body_latest = abs(latest['Close'] - latest['Open'])
    body_prev = abs(prev['Close'] - prev['Open'])
    
    # Avoid division by zero
    if body_latest == 0:
        body_latest = 0.001

    # ── Check 1: Engulfing Pattern ──
    if is_buy:
        # Bearish engulfing: prev was green, latest is red and body covers prev body
        prev_green = prev['Close'] > prev['Open']
        latest_red = latest['Close'] < latest['Open']
        engulfing = (
            prev_green and latest_red and
            latest['Open'] >= prev['Close'] and
            latest['Close'] <= prev['Open'] and
            body_latest > body_prev
        )
        if engulfing:
            return True, "Bearish Engulfing candle"
    else:
        # Bullish engulfing: prev was red, latest is green and body covers prev body
        prev_red = prev['Close'] < prev['Open']
        latest_green = latest['Close'] > latest['Open']
        engulfing = (
            prev_red and latest_green and
            latest['Open'] <= prev['Close'] and
            latest['Close'] >= prev['Open'] and
            body_latest > body_prev
        )
        if engulfing:
            return True, "Bullish Engulfing candle (reversal for SELL)"

    # ── Check 2: Pin Bar / Long Wick Rejection ──
    if is_buy:
        # Upper wick much longer than body = rejection from highs
        upper_wick = latest['High'] - max(latest['Open'], latest['Close'])
        if upper_wick >= 2 * body_latest and latest['Close'] < latest['Open']:
            return True, "Pin bar rejection from highs"
    else:
        # Lower wick much longer than body = rejection from lows
        lower_wick = min(latest['Open'], latest['Close']) - latest['Low']
        if lower_wick >= 2 * body_latest and latest['Close'] > latest['Open']:
            return True, "Pin bar rejection from lows"

    # ── Check 3: RSI Divergence (simplified) ──
    if len(df) >= 5:
        try:
            rsi = ta.rsi(df['Close'], length=5)
            if rsi is not None and len(rsi) >= 2:
                rsi_latest = rsi.iloc[-1]
                rsi_prev_max = rsi.iloc[:-1].max()
                price_latest = latest['Close']
                price_prev_max = df['Close'].iloc[:-1].max()
                price_prev_min = df['Close'].iloc[:-1].min()
                
                if is_buy:
                    # Price making new high but RSI not → bearish divergence
                    if price_latest >= price_prev_max and rsi_latest < rsi_prev_max - 5:
                        return True, "RSI bearish divergence"
                else:
                    # Price making new low but RSI not → bullish divergence
                    rsi_prev_min = rsi.iloc[:-1].min()
                    if price_latest <= price_prev_min and rsi_latest > rsi_prev_min + 5:
                        return True, "RSI bullish divergence (reversal for SELL)"
        except Exception:
            pass  # RSI calculation can fail with insufficient data

    # ── Check 4: Volume Spike + Opposite Direction ──
    if len(df) >= 5:
        avg_volume = df['Volume'].iloc[:-1].mean()
        if avg_volume > 0 and latest['Volume'] > 1.5 * avg_volume:
            if is_buy and latest['Close'] < latest['Open']:
                return True, "Volume spike with bearish candle"
            elif not is_buy and latest['Close'] > latest['Open']:
                return True, "Volume spike with bullish candle (reversal for SELL)"

    return False, ""


def calculate_progress(entry: float, target: float, current: float, is_buy: bool) -> float:
    """
    Calculate how far price has moved from entry toward target (0.0 to 1.0+).
    Returns negative if price moved against the trade.
    """
    total_distance = abs(target - entry)
    if total_distance == 0:
        return 0.0
    
    if is_buy:
        moved = current - entry
    else:
        moved = entry - current
    
    return moved / total_distance


def update_trailing_sl(signal_id: int, new_sl: float, state: str, peak_price: float = None):
    """Send PATCH request to NestJS to update the trailing stop loss."""
    base_url = NESTJS_URL.replace('/signals/new', '/signals')
    payload = {
        "newStopLoss": round(new_sl, 2),
        "trailingState": state,
    }
    if peak_price is not None:
        payload["peakPrice"] = round(peak_price, 2)
    
    try:
        r = httpx.patch(f"{base_url}/{signal_id}/update-sl", json=payload, timeout=10)
        if r.status_code == 200:
            print(f"    ✅ Trailing SL updated: #{signal_id} → ₹{new_sl:.2f} ({state})")
        else:
            print(f"    ⚠️ Trailing SL update failed: {r.status_code}")
    except Exception as e:
        print(f"    [ERROR] updating trailing SL: {e}")


def auto_close_signals(cache):
    """
    Smart exit system with 3 layers:
    1. Breakeven protection at 50% of target
    2. Profit lock (40%) at 75% of target
    3. Reversal detection at 60%+ of target
    
    Falls back to original SL/TP hit logic.
    """
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
            
            entry = float(sig['entryPrice'])
            sl = float(sig['stopLoss'])
            tp = float(sig['target'])
            is_buy = sig['signalType'] == 'BUY'
            signal_id = sig['id']
            
            # Get current trailing state from cache (or from trade data)
            current_state = trailing_state_cache.get(signal_id, "INITIAL")
            
            # Calculate progress toward target
            progress = calculate_progress(entry, tp, latest_price, is_buy)
            
            should_close = False
            exit_price = latest_price
            close_reason = ""
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # LAYER 3: Reversal Detection (60%+ zone)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if progress >= REVERSAL_ZONE_START and not should_close:
                recent_df = get_recent_candles(symbol)
                if not recent_df.empty:
                    is_reversal, reason = detect_reversal(recent_df, is_buy)
                    if is_reversal:
                        should_close = True
                        exit_price = latest_price
                        close_reason = f"REVERSAL DETECTED ({reason}) at {progress*100:.0f}% of target"
                        trailing_state_cache[signal_id] = "REVERSAL_EXIT"
                        print(f"  ⚠️ REVERSAL: {symbol} — {reason} (progress: {progress*100:.0f}%)")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # LAYER 2: Profit Lock (75%+ zone)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if progress >= PROFIT_LOCK_THRESHOLD and current_state != "PROFIT_LOCK" and not should_close:
                # Lock 40% of unrealized profit by moving SL
                unrealized_per_unit = abs(latest_price - entry)
                lock_amount = unrealized_per_unit * PROFIT_LOCK_PERCENT
                
                if is_buy:
                    new_sl = entry + lock_amount
                else:
                    new_sl = entry - lock_amount
                
                # Only update if new SL is better than current SL
                sl_is_better = (is_buy and new_sl > sl) or (not is_buy and new_sl < sl)
                if sl_is_better:
                    print(f"  💰 PROFIT LOCK: {symbol} — SL ₹{sl:.2f} → ₹{new_sl:.2f} (locking 40% at {progress*100:.0f}%)")
                    update_trailing_sl(signal_id, new_sl, "PROFIT_LOCK", latest_price)
                    trailing_state_cache[signal_id] = "PROFIT_LOCK"
                    sl = new_sl  # Update local SL for subsequent checks
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # LAYER 1: Breakeven Protection (50%+ zone)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            elif progress >= BREAKEVEN_THRESHOLD and current_state == "INITIAL" and not should_close:
                # Move SL to entry price (breakeven)
                # Add a small buffer (0.1%) to account for spreads
                if is_buy:
                    new_sl = entry + (entry * 0.001)
                else:
                    new_sl = entry - (entry * 0.001)
                
                # Only update if new SL is better than current
                sl_is_better = (is_buy and new_sl > sl) or (not is_buy and new_sl < sl)
                if sl_is_better:
                    print(f"  🔒 BREAKEVEN: {symbol} — SL ₹{sl:.2f} → ₹{new_sl:.2f} (at {progress*100:.0f}%)")
                    update_trailing_sl(signal_id, new_sl, "BREAKEVEN", latest_price)
                    trailing_state_cache[signal_id] = "BREAKEVEN"
                    sl = new_sl
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # FALLBACK: Original SL/TP Hit Check
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if not should_close:
                if is_buy:
                    if latest_price <= sl:
                        should_close = True
                        exit_price = sl
                        state = trailing_state_cache.get(signal_id, "INITIAL")
                        if state == "BREAKEVEN":
                            close_reason = f"hit Breakeven SL (₹{sl})"
                        elif state == "PROFIT_LOCK":
                            close_reason = f"hit Profit-Lock SL (₹{sl})"
                        else:
                            close_reason = f"hit Stop Loss (₹{sl})"
                    elif latest_price >= tp:
                        should_close = True
                        exit_price = tp
                        close_reason = f"hit Target (₹{tp})"
                else:
                    if latest_price >= sl:
                        should_close = True
                        exit_price = sl
                        state = trailing_state_cache.get(signal_id, "INITIAL")
                        if state == "BREAKEVEN":
                            close_reason = f"hit Breakeven SL (₹{sl})"
                        elif state == "PROFIT_LOCK":
                            close_reason = f"hit Profit-Lock SL (₹{sl})"
                        else:
                            close_reason = f"hit Stop Loss (₹{sl})"
                    elif latest_price <= tp:
                        should_close = True
                        exit_price = tp
                        close_reason = f"hit Target (₹{tp})"
                    
            # Intraday auto square-off
            if not should_close and sig.get('holdDuration') == 'INTRADAY' and is_square_off_time:
                should_close = True
                exit_price = latest_price
                close_reason = "INTRADAY auto square-off (>= 15:15 IST)"
                    
            if should_close:
                progress_pct = progress * 100
                print(f"  🔒 AUTO-CLOSE {sig['signalType']} {symbol}: Price ₹{exit_price} {close_reason} (progress: {progress_pct:.0f}%)")
                httpx.patch(
                    f"{NESTJS_URL.replace('/signals/new', '/signals')}/{signal_id}/close",
                    json={"exitPrice": exit_price},
                    timeout=10
                )
                # Clean up trailing state cache
                trailing_state_cache.pop(signal_id, None)
            else:
                print(f"  📊 {symbol}: ₹{latest_price:.2f} (progress: {progress*100:.0f}% | state: {current_state})")
                
    except Exception as e:
        print(f"  [ERROR] auto-closing signals: {e}")


def main():
    print("🚀 Live Scanner started (Smart Trailing SL v2)")
    print(f"📡 Will POST signals to: {NESTJS_URL}")
    print(f"⏰ Market hours: {MARKET_OPEN} – {MARKET_CLOSE} IST")
    print(f"📐 Trailing config: Breakeven@{BREAKEVEN_THRESHOLD*100:.0f}% | ProfitLock@{PROFIT_LOCK_THRESHOLD*100:.0f}% (lock {PROFIT_LOCK_PERCENT*100:.0f}%) | Reversal@{REVERSAL_ZONE_START*100:.0f}%+")
    print("-" * 60)

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
        
        # 1. Smart auto-close with trailing SL + reversal detection
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
