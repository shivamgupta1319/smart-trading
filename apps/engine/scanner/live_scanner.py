"""Live Scanner — polls yfinance every 60s during NSE market hours and fires signals.

Implements a 3-Layer Smart Exit System:
  Layer 1 (Breakeven):    At 50% of target distance → SL moves to entry price
  Layer 2 (Profit Lock):  At 75% of target distance → SL locks 40% of unrealized profit
  Layer 3 (Reversal):     At 80%+ of target distance → detect reversal candle patterns → exit early
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
# Shared API key sent to the NestJS API (no-op when unset / API auth disabled).
NEST_HEADERS = {"x-api-key": os.getenv("API_KEY")} if os.getenv("API_KEY") else {}
# Positions smaller than this never partial-exit (booking 35% of 1-2 shares is moot).
MIN_QTY_FOR_PARTIAL = int(os.getenv("MIN_QTY_FOR_PARTIAL", "3"))
IST = pytz.timezone("Asia/Kolkata")


def _signals_base() -> str:
    return NESTJS_URL.replace("/signals/new", "/signals")


def book_partial(signal_id, percent, exit_price, reason) -> bool:
    """Book a partial exit and RECONCILE: only return True if the API confirms it.
    Prevents the scanner's in-memory state from advancing past a failed PATCH."""
    try:
        r = httpx.patch(
            f"{_signals_base()}/{signal_id}/partial-close",
            json={"percent": percent, "exitPrice": exit_price, "reason": reason},
            headers=NEST_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return True
        print(f"    ⚠️ partial-close #{signal_id} failed: HTTP {r.status_code} — will retry next poll")
        return False
    except Exception as e:
        print(f"    [ERROR] partial-close #{signal_id}: {e} — will retry next poll")
        return False


def close_trade(signal_id, exit_price) -> bool:
    try:
        r = httpx.patch(
            f"{_signals_base()}/{signal_id}/close",
            json={"exitPrice": exit_price}, headers=NEST_HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return True
        print(f"    ⚠️ close #{signal_id} failed: HTTP {r.status_code} — will retry next poll")
        return False
    except Exception as e:
        print(f"    [ERROR] close #{signal_id}: {e} — will retry next poll")
        return False
MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
POLL_INTERVAL = 100  # seconds

# ── Smart Trailing SL Configuration ──
BREAKEVEN_THRESHOLD = 0.50   # Move SL to breakeven at 50% of target distance
PROFIT_LOCK_THRESHOLD = 0.75 # Lock profit at 75% of target distance
PROFIT_LOCK_PERCENT = 0.40   # Lock 40% of unrealized profit
REVERSAL_ZONE_START = 0.80   # Start checking for reversals at 80% of target distance

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
        df = strategy._apply_bucket_target(df)  # bucket reward:risk override (matches backtest)
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
        
        now_ist = datetime.now(IST)
        if hold_duration == "INTRADAY" and now_ist.hour >= 15:
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
        response = httpx.post(NESTJS_URL, json=payload, headers=NEST_HEADERS, timeout=10)
        print(f"  ✅ Posted to NestJS: {response.status_code}")
        
        # Mark this candle as fired
        last_fired_times[cache_key] = candle_time

    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")


def get_live_price(symbol: str) -> float:
    # Routes to the configured broker (Dhan/Upstox) when available, else yfinance.
    try:
        from brokers import get_live_price as _broker_live_price
        q = _broker_live_price(symbol)
        if q and q.get("price"):
            return q["price"]
        return None
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

    # ── Check 4: Volume Exhaustion ──
    if len(df) >= 5:
        avg_vol = df['Volume'].iloc[:-1].mean()
        if avg_vol > 0:
            latest_vol = latest['Volume']
            prev_vol = prev['Volume']
            if latest_vol >= 1.8 * avg_vol or prev_vol >= 1.8 * avg_vol:
                if is_buy and latest['Close'] < latest['Open']:
                    return True, "Volume exhaustion (Bearish)"
                elif not is_buy and latest['Close'] > latest['Open']:
                    return True, "Volume exhaustion (Bullish)"

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
        r = httpx.patch(f"{base_url}/{signal_id}/update-sl", json=payload, headers=NEST_HEADERS, timeout=10)
        if r.status_code == 200:
            print(f"    ✅ Trailing SL updated: #{signal_id} → ₹{new_sl:.2f} ({state})")
        else:
            print(f"    ⚠️ Trailing SL update failed: {r.status_code}")
    except Exception as e:
        print(f"    [ERROR] updating trailing SL: {e}")


def auto_close_signals(cache):
    """
    Smart 3-Phase exit system:
    - Phase 1 (0-49%): Original SL
    - Phase 2 (50-74%): SL to Breakeven, book 35%
    - Phase 3 (75-99%): Trail SL below candle lows, book 35%
    - Reversal Detection (>=80%): Exit remaining on volume exhaustion
    """
    api_url = NESTJS_URL.replace("/signals/new", "/signals/active")
    now_time = datetime.now(IST).time()
    is_square_off_time = now_time >= dtime(15, 15)

    try:
        r = httpx.get(api_url, headers=NEST_HEADERS, timeout=10)
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
            
            trade = sig.get('trade')
            if not trade or trade['status'] != 'OPEN':
                continue
            
            qty = int(trade['quantity'])
            remaining_qty = int(trade.get('remainingQty', qty))
            
            if remaining_qty == 0:
                continue
            
            entry = float(trade['entryPrice'])
            sl = float(trade['stopLoss'])
            tp = float(sig['target'])
            is_buy = trade['signalType'] == 'BUY'
            signal_id = sig['id']
            
            current_state = trade.get('trailingState', "INITIAL")
            progress = calculate_progress(entry, tp, latest_price, is_buy)
            
            should_close = False
            exit_price = latest_price
            close_reason = ""
            
            recent_df = get_recent_candles(symbol)
            if not recent_df.empty:
                prev_low = recent_df['Low'].iloc[-2] if len(recent_df) >= 2 else recent_df['Low'].iloc[-1]
                prev_high = recent_df['High'].iloc[-2] if len(recent_df) >= 2 else recent_df['High'].iloc[-1]
            else:
                prev_low = latest_price
                prev_high = latest_price
            
            # NOTE: gate every transition on the state at the START of this poll
            # (`original_state`) and use elif, so a single poll advances AT MOST
            # one phase. The old code mutated current_state then re-checked it in
            # the same poll, cascading INITIAL→PHASE2→PHASE3 and booking 70% at
            # one price. Partials are also reconciled: SL/state only advance if
            # the partial-close PATCH actually succeeded.
            original_state = current_state
            hold_duration = sig.get('holdDuration') or "UNKNOWN"

            if hold_duration == "INTRADAY":
                # ── INTRADAY: 3-phase partial booking + breakeven + trail + reversal ──
                # ── PHASE 1 -> PHASE 2 (50%+): SL to breakeven, book 35% ──
                if original_state == "INITIAL" and progress >= 0.50:
                    booked = True
                    if qty >= MIN_QTY_FOR_PARTIAL:
                        print(f"  💰 PHASE 2 PARTIAL: {symbol} — Booking 35% at {progress*100:.0f}%")
                        booked = book_partial(signal_id, 0.35, latest_price, "Phase 2 Partial (50% Target)")
                    if booked:
                        be_sl = entry + (entry * 0.001) if is_buy else entry - (entry * 0.001)
                        sl_better = (is_buy and be_sl > sl) or (not is_buy and be_sl < sl)
                        new_sl = be_sl if sl_better else sl
                        update_trailing_sl(signal_id, new_sl, "PHASE2", latest_price)
                        sl = new_sl
                        current_state = "PHASE2"

                # ── PHASE 2 -> PHASE 3 (75%+): trail below candle, book another 35% ──
                elif original_state == "PHASE2" and progress >= 0.75:
                    booked = True
                    if qty >= MIN_QTY_FOR_PARTIAL:
                        print(f"  💰 PHASE 3 PARTIAL: {symbol} — Booking 35% at {progress*100:.0f}%")
                        booked = book_partial(signal_id, 0.35, latest_price, "Phase 3 Partial (75% Target)")
                    if booked:
                        trail_sl = prev_low - (prev_low * 0.001) if is_buy else prev_high + (prev_high * 0.001)
                        sl_better = (is_buy and trail_sl > sl) or (not is_buy and trail_sl < sl)
                        new_sl = trail_sl if sl_better else sl
                        update_trailing_sl(signal_id, new_sl, "PHASE3", latest_price)
                        sl = new_sl
                        current_state = "PHASE3"

                # PHASE 3 TRAILING (update SL with candle lows)
                if current_state == "PHASE3":
                    trail_sl = prev_low - (prev_low * 0.001) if is_buy else prev_high + (prev_high * 0.001)
                    sl_better = (is_buy and trail_sl > sl) or (not is_buy and trail_sl < sl)
                    if sl_better:
                        update_trailing_sl(signal_id, trail_sl, "PHASE3", latest_price)
                        sl = trail_sl

                # LAYER 3: Reversal Detection (80%+)
                if progress >= REVERSAL_ZONE_START and not should_close:
                    if not recent_df.empty:
                        is_reversal, reason = detect_reversal(recent_df, is_buy)
                        if is_reversal:
                            should_close = True
                            exit_price = latest_price
                            close_reason = f"REVERSAL DETECTED ({reason}) at {progress*100:.0f}%"

            else:
                # ── SWING / MID / LONG: ATR chandelier trailing stop, no partials,
                # no reversal. Exit happens below at the fixed target OR trailed SL.
                peak = float(trade.get('peakPrice') or entry)
                peak = max(peak, latest_price) if is_buy else min(peak, latest_price)
                atr_val = None
                if not recent_df.empty and len(recent_df) >= 2:
                    try:
                        atr_series = ta.atr(recent_df['High'], recent_df['Low'], recent_df['Close'], length=14)
                        if atr_series is not None and not atr_series.dropna().empty:
                            atr_val = float(atr_series.dropna().iloc[-1])
                    except Exception:
                        atr_val = None
                if atr_val and atr_val > 0:
                    from backtest_config import trail_mult_for_bucket
                    mult = trail_mult_for_bucket(hold_duration)
                    new_sl = peak - mult * atr_val if is_buy else peak + mult * atr_val
                    sl_better = (is_buy and new_sl > sl) or (not is_buy and new_sl < sl)
                    if sl_better:
                        update_trailing_sl(signal_id, new_sl, "TRAILING", peak)
                        sl = new_sl

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # SL / TP / Intraday Hit Check
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if not should_close:
                if is_buy:
                    if latest_price <= sl:
                        should_close = True
                        exit_price = sl
                        close_reason = f"hit SL/Trailing SL (₹{sl})"
                    elif latest_price >= tp:
                        should_close = True
                        exit_price = tp
                        close_reason = f"hit Target (₹{tp})"
                else:
                    if latest_price >= sl:
                        should_close = True
                        exit_price = sl
                        close_reason = f"hit SL/Trailing SL (₹{sl})"
                    elif latest_price <= tp:
                        should_close = True
                        exit_price = tp
                        close_reason = f"hit Target (₹{tp})"
                    
            if not should_close and sig.get('holdDuration') == 'INTRADAY' and is_square_off_time:
                should_close = True
                exit_price = latest_price
                close_reason = "INTRADAY auto square-off (>= 15:15 IST)"
                    
            if should_close:
                print(f"  🔒 AUTO-CLOSE {sig['signalType']} {symbol}: Price ₹{exit_price} {close_reason} (progress: {progress*100:.0f}%)")
                close_trade(signal_id, exit_price)
                
    except Exception as e:
        print(f"  [ERROR] auto-closing signals: {e}")


def main():
    print("🚀 Live Scanner started (Smart Trailing SL v2)")
    print(f"📡 Will POST signals to: {NESTJS_URL}")
    print(f"⏰ Market hours: {MARKET_OPEN} – {MARKET_CLOSE} IST")
    # Actual exit system (3-phase): SL→breakeven & book 35% at 50%, trail below
    # candles & book 35% at 75%, reversal-exit the remainder at 80%+.
    print(f"📐 3-Phase exit: BE+35%@50% | Trail+35%@75% | Reversal@{REVERSAL_ZONE_START*100:.0f}%+ | min qty for partials: {MIN_QTY_FOR_PARTIAL}")
    print("-" * 60)

    last_fired_times = {}
    cycle = 0

    while True:
        now = datetime.now(IST)
        cycle += 1
        cycle_start = time.monotonic()
        print(f"\n[{now.strftime('%H:%M:%S')} IST] ❤️  heartbeat cycle #{cycle} — scanning...")

        if not is_market_open():
            print("  Market is CLOSED. Sleeping 60s...")
            time.sleep(60)
            continue

        configs = get_active_configs()
        cache = {}

        # 1. Smart auto-close with trailing SL + reversal detection
        auto_close_signals(cache)

        # 2. Check for new setups
        if now.time() < dtime(9, 30):
            print("  Skipping new setups before 9:30 AM IST (avoiding fake opening moves).")
        elif now.time() >= dtime(15, 15):
            print("  Skipping new setups after 3:15 PM IST (market closing soon).")
        elif not configs:
            print("  No active configurations. Add some via the UI.")
        else:
            for config in configs:
                print(f"  Checking {config[4]} with {config[2]} ({config[3]})...")
                check_and_fire_signal(config, cache, last_fired_times)
                time.sleep(1)  # Brief pause between stocks

        elapsed = time.monotonic() - cycle_start
        # Stall detection: if a cycle takes longer than the poll interval, the
        # scanner is falling behind (too many configs / slow yfinance).
        if elapsed > POLL_INTERVAL:
            print(f"  ⚠️ STALL: cycle #{cycle} took {elapsed:.0f}s > poll interval {POLL_INTERVAL}s — scanner is behind.")
        else:
            print(f"  Done in {elapsed:.1f}s ({len(configs)} configs). Sleeping {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
