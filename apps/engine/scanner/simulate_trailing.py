"""
Smart Trailing SL Simulator v2 — 3-Phase Exit Framework
Based on research doc: docs/trade_protection.md

Implements the upgraded 3-phase system:
  Phase 1 (0-49%):   Hold full position, original SL active
  Phase 2 (50-74%):  SL → Breakeven + Book 35% of position
  Phase 3 (75-99%):  Trail SL below candle lows + Book another 35%
  Target hit:        Exit final 30%

Replays all closed trades against historical 5m candle data to compare
actual P&L vs what the 3-phase system would have produced.
"""
import os
import sys
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime, timedelta
from sqlalchemy import text
from dotenv import load_dotenv

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from db.client import engine

# ── 3-Phase Configuration ──
PHASE2_TRIGGER = 0.50         # 50% progress → breakeven + partial exit
PHASE3_TRIGGER = 0.75         # 75% progress → trail candle lows + partial exit
PHASE2_EXIT_PCT = 0.35        # Book 35% of position at phase 2
PHASE3_EXIT_PCT = 0.35        # Book another 35% at phase 3
FINAL_LOT_PCT = 0.30          # Let final 30% ride to target
REVERSAL_ZONE_START = 0.80    # Reversal pattern detection from 80%+


def detect_reversal(candles: pd.DataFrame, is_buy: bool) -> tuple:
    """Detect strong reversal patterns — engulfing + pin bar only (no volume spike)."""
    if candles.empty or len(candles) < 3:
        return False, ""

    latest = candles.iloc[-1]
    prev = candles.iloc[-2]

    body_latest = abs(latest['Close'] - latest['Open'])
    body_prev = abs(prev['Close'] - prev['Open'])
    if body_latest == 0:
        body_latest = 0.001

    # Engulfing
    if is_buy:
        prev_green = prev['Close'] > prev['Open']
        latest_red = latest['Close'] < latest['Open']
        if (prev_green and latest_red and
            latest['Open'] >= prev['Close'] and
            latest['Close'] <= prev['Open'] and
            body_latest > body_prev):
            return True, "Bearish Engulfing"
    else:
        prev_red = prev['Close'] < prev['Open']
        latest_green = latest['Close'] > latest['Open']
        if (prev_red and latest_green and
            latest['Open'] <= prev['Close'] and
            latest['Close'] >= prev['Open'] and
            body_latest > body_prev):
            return True, "Bullish Engulfing"

    # Pin bar
    if is_buy:
        upper_wick = latest['High'] - max(latest['Open'], latest['Close'])
        if upper_wick >= 2 * body_latest and latest['Close'] < latest['Open']:
            return True, "Pin bar rejection"
    else:
        lower_wick = min(latest['Open'], latest['Close']) - latest['Low']
        if lower_wick >= 2 * body_latest and latest['Close'] > latest['Open']:
            return True, "Pin bar rejection"

    # RSI divergence
    if len(candles) >= 5:
        try:
            rsi = ta.rsi(candles['Close'], length=5)
            if rsi is not None and len(rsi) >= 2:
                rsi_latest = rsi.iloc[-1]
                rsi_prev_max = rsi.iloc[:-1].max()
                price_latest = latest['Close']
                price_prev_max = candles['Close'].iloc[:-1].max()
                price_prev_min = candles['Close'].iloc[:-1].min()

                if is_buy:
                    if price_latest >= price_prev_max and rsi_latest < rsi_prev_max - 5:
                        return True, "RSI bearish divergence"
                else:
                    rsi_prev_min = rsi.iloc[:-1].min()
                    if price_latest <= price_prev_min and rsi_latest > rsi_prev_min + 5:
                        return True, "RSI bullish divergence"
        except Exception:
            pass

    # Volume spike exhaustion (Identified from backtest pattern)
    # Institutional profit booking: Massive volume (>=1.8x) near target, followed by opposite color candle
    if len(candles) >= 5:
        avg_vol = candles['Volume'].iloc[:-1].mean()
        if avg_vol > 0:
            latest_vol = latest['Volume']
            prev_vol = prev['Volume']
            
            # Check if volume spiked significantly on this or the previous candle
            if latest_vol >= 1.8 * avg_vol or prev_vol >= 1.8 * avg_vol:
                if is_buy and latest['Close'] < latest['Open']:
                    return True, "Volume exhaustion (Bearish)"
                elif not is_buy and latest['Close'] > latest['Open']:
                    return True, "Volume exhaustion (Bullish)"

    return False, ""


def simulate_trade_3phase(trade: dict, candles: pd.DataFrame) -> dict:
    """
    Simulate the 3-Phase Exit Framework on a single trade.

    Tracks 3 lots of the position independently:
      Lot A (35%): Exits at Phase 2 (50% progress) at current price
      Lot B (35%): Exits at Phase 3 (75% progress) or via candle-low trail
      Lot C (30%): Rides to full target or gets trailed out

    Returns combined P&L across all lots.
    """
    entry = trade['entryPrice']
    original_sl = trade['stopLoss']
    tp = trade['target']
    is_buy = trade['signalType'] == 'BUY'
    total_qty = trade['quantity']
    entry_time = trade['entryTime']

    # Split into 3 lots
    qty_a = round(total_qty * PHASE2_EXIT_PCT)   # 35% — exits at 50%
    qty_b = round(total_qty * PHASE3_EXIT_PCT)   # 35% — exits at 75% or trailed
    qty_c = total_qty - qty_a - qty_b             # 30% — rides to target

    # Per-lot tracking
    lot_a_exit = None
    lot_b_exit = None
    lot_c_exit = None
    lot_a_reason = ""
    lot_b_reason = ""
    lot_c_reason = ""

    # Global SL starts at original
    sl = original_sl
    state = "PHASE1"
    trail_sl_b = None   # Trailing SL for lot B (candle low based)
    trail_sl_c = None   # Trailing SL for lot C

    # ── Find entry candle index ──
    import pytz
    entry_idx = None
    if hasattr(entry_time, 'tzinfo') and entry_time.tzinfo is None:
        entry_time_aware = pytz.utc.localize(entry_time)
    else:
        entry_time_aware = entry_time

    for i, (idx, row) in enumerate(candles.iterrows()):
        try:
            if idx >= entry_time_aware:
                entry_idx = i
                break
        except TypeError:
            ct = idx.replace(tzinfo=None) if hasattr(idx, 'replace') else idx
            et = entry_time_aware.replace(tzinfo=None)
            if ct >= et:
                entry_idx = i
                break

    if entry_idx is None:
        for i, (idx, row) in enumerate(candles.iterrows()):
            if abs(row['Close'] - entry) / entry < 0.005:
                entry_idx = i
                break

    if entry_idx is None:
        entry_idx = 0

    # ── Walk through candles ──
    for i in range(entry_idx + 1, len(candles)):
        row = candles.iloc[i]
        price = row['Close']
        high = row['High']
        low = row['Low']

        check_price_sl = low if is_buy else high
        check_price_tp = high if is_buy else low

        # Progress toward target
        total_dist = abs(tp - entry)
        if total_dist == 0:
            progress = 0
        else:
            moved = (price - entry) if is_buy else (entry - price)
            progress = moved / total_dist

        # Previous candle low/high for trailing
        prev_candle = candles.iloc[i - 1] if i > 0 else row
        prev_low = prev_candle['Low']
        prev_high = prev_candle['High']

        # ── PHASE 1 → PHASE 2 transition (50% progress) ──
        if state == "PHASE1" and progress >= PHASE2_TRIGGER:
            state = "PHASE2"
            # Move SL to breakeven for remaining lots
            be_sl = entry + (entry * 0.001) if is_buy else entry - (entry * 0.001)
            sl_better = (is_buy and be_sl > sl) or (not is_buy and be_sl < sl)
            if sl_better:
                sl = be_sl

            # ── Book Lot A at current price ──
            if lot_a_exit is None:
                lot_a_exit = price
                lot_a_reason = f"Phase 2 partial @{progress*100:.0f}%"

        # ── PHASE 2 → PHASE 3 transition (75% progress) ──
        if state == "PHASE2" and progress >= PHASE3_TRIGGER:
            state = "PHASE3"

            # ── Book Lot B at current price ──
            if lot_b_exit is None:
                lot_b_exit = price
                lot_b_reason = f"Phase 3 partial @{progress*100:.0f}%"

            # Set initial trailing SL for Lot C below previous candle low
            if is_buy:
                trail_sl_c = prev_low - (prev_low * 0.001)  # tiny buffer
            else:
                trail_sl_c = prev_high + (prev_high * 0.001)

        # ── PHASE 3: Trail SL below candle lows for remaining Lot C ──
        if state == "PHASE3" and lot_c_exit is None and trail_sl_c is not None:
            # Update trailing SL to latest candle low/high (only moves favorably)
            if is_buy:
                new_trail = prev_low - (prev_low * 0.001)
                if new_trail > trail_sl_c:
                    trail_sl_c = new_trail
            else:
                new_trail = prev_high + (prev_high * 0.001)
                if new_trail < trail_sl_c:
                    trail_sl_c = new_trail

            # Check if trailing SL is hit for Lot C
            if is_buy and check_price_sl <= trail_sl_c:
                lot_c_exit = trail_sl_c
                lot_c_reason = f"Candle-low trail @{progress*100:.0f}%"
            elif not is_buy and check_price_sl >= trail_sl_c:
                lot_c_exit = trail_sl_c
                lot_c_reason = f"Candle-high trail @{progress*100:.0f}%"

        # ── Reversal detection at 80%+ for Lot C ──
        if state == "PHASE3" and lot_c_exit is None and progress >= REVERSAL_ZONE_START:
            lookback = candles.iloc[max(0, i - 9):i + 1]
            is_rev, reason = detect_reversal(lookback, is_buy)
            if is_rev:
                lot_c_exit = price
                lot_c_reason = f"REVERSAL ({reason}) @{progress*100:.0f}%"

        # ── Check target hit for Lot C ──
        if lot_c_exit is None:
            if is_buy and check_price_tp >= tp:
                lot_c_exit = tp
                lot_c_reason = "Target hit"
            elif not is_buy and check_price_tp <= tp:
                lot_c_exit = tp
                lot_c_reason = "Target hit"

        # ── Original SL hit check (Phase 1) — all remaining lots exit ──
        if state == "PHASE1":
            if (is_buy and check_price_sl <= sl) or (not is_buy and check_price_sl >= sl):
                exit_p = sl
                if lot_a_exit is None:
                    lot_a_exit = exit_p
                    lot_a_reason = "SL hit (Phase 1)"
                if lot_b_exit is None:
                    lot_b_exit = exit_p
                    lot_b_reason = "SL hit (Phase 1)"
                if lot_c_exit is None:
                    lot_c_exit = exit_p
                    lot_c_reason = "SL hit (Phase 1)"
                break

        # ── Breakeven SL hit check (Phase 2/3) ──
        if state in ("PHASE2", "PHASE3") and sl != original_sl:
            if (is_buy and check_price_sl <= sl) or (not is_buy and check_price_sl >= sl):
                if lot_b_exit is None:
                    lot_b_exit = sl
                    lot_b_reason = f"Breakeven SL hit ({state})"
                if lot_c_exit is None and trail_sl_c is None:
                    lot_c_exit = sl
                    lot_c_reason = f"Breakeven SL hit ({state})"
                # If all lots filled, stop
                if lot_a_exit and lot_b_exit and lot_c_exit:
                    break

        # All lots exited?
        if lot_a_exit and lot_b_exit and lot_c_exit:
            break

    # ── EOD close for any remaining lots ──
    eod_price = candles.iloc[-1]['Close']
    if lot_a_exit is None:
        lot_a_exit = eod_price
        lot_a_reason = "EOD close"
    if lot_b_exit is None:
        lot_b_exit = eod_price
        lot_b_reason = "EOD close"
    if lot_c_exit is None:
        lot_c_exit = eod_price
        lot_c_reason = "EOD close"

    # ── Calculate combined P&L ──
    if is_buy:
        pnl_a = (lot_a_exit - entry) * qty_a
        pnl_b = (lot_b_exit - entry) * qty_b
        pnl_c = (lot_c_exit - entry) * qty_c
    else:
        pnl_a = (entry - lot_a_exit) * qty_a
        pnl_b = (entry - lot_b_exit) * qty_b
        pnl_c = (entry - lot_c_exit) * qty_c

    total_pnl = pnl_a + pnl_b + pnl_c

    # Determine the final state label
    if state == "PHASE1":
        final_state = "SL_HIT"
    elif lot_c_reason.startswith("Target"):
        final_state = "FULL_TARGET"
    elif lot_c_reason.startswith("REVERSAL"):
        final_state = "REVERSAL_EXIT"
    elif lot_c_reason.startswith("Candle"):
        final_state = "TRAIL_EXIT"
    else:
        final_state = state

    # Build primary exit reason (most informative lot)
    primary_reason = lot_c_reason if lot_c_exit != eod_price else (lot_b_reason if lot_b_exit != eod_price else lot_a_reason)

    return {
        'sim_pnl': round(total_pnl, 2),
        'sim_state': final_state,
        'sim_exit_reason': primary_reason,
        'lot_a': {'qty': qty_a, 'exit': round(lot_a_exit, 2), 'pnl': round(pnl_a, 2), 'reason': lot_a_reason},
        'lot_b': {'qty': qty_b, 'exit': round(lot_b_exit, 2), 'pnl': round(pnl_b, 2), 'reason': lot_b_reason},
        'lot_c': {'qty': qty_c, 'exit': round(lot_c_exit, 2), 'pnl': round(pnl_c, 2), 'reason': lot_c_reason},
        'trailing_sl': round(trail_sl_c, 2) if trail_sl_c else round(sl, 2),
    }


def fetch_intraday_candles(symbol: str, trade_date: datetime) -> pd.DataFrame:
    """Fetch 5m candles for a specific date from yfinance."""
    yf_symbol = symbol if symbol.endswith(".NS") else symbol + ".NS"
    start = trade_date.strftime('%Y-%m-%d')
    end = (trade_date + timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        df = yf.download(yf_symbol, start=start, end=end, interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            df = yf.download(yf_symbol, start=start, end=end, interval="15m", progress=False, auto_adjust=True)
        if not df.empty:
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        return df
    except Exception as e:
        print(f"  [ERROR] fetching candles for {symbol} on {trade_date.date()}: {e}")
        return pd.DataFrame()


def main():
    print("=" * 100)
    print("🔬 3-PHASE EXIT SIMULATOR v2 — Partial Booking + Candle-Low Trailing")
    print("=" * 100)
    print(f"Phase 2 @{PHASE2_TRIGGER*100:.0f}%: BE + Book {PHASE2_EXIT_PCT*100:.0f}% | "
          f"Phase 3 @{PHASE3_TRIGGER*100:.0f}%: Trail + Book {PHASE3_EXIT_PCT*100:.0f}% | "
          f"Final {FINAL_LOT_PCT*100:.0f}% rides | Reversal @{REVERSAL_ZONE_START*100:.0f}%+")
    print()

    # Fetch all closed trades
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, symbol, "strategyName", "signalType", "entryPrice", "stopLoss", target, 
                   "exitPrice", pnl, outcome, quantity, "holdDuration", "entryTime", "exitTime"
            FROM "Trade" 
            WHERE status = 'CLOSED' AND outcome IS NOT NULL
            ORDER BY id ASC
        """)).fetchall()

    columns = ['id', 'symbol', 'strategyName', 'signalType', 'entryPrice', 'stopLoss',
               'target', 'exitPrice', 'pnl', 'outcome', 'quantity', 'holdDuration',
               'entryTime', 'exitTime']
    trades = [dict(zip(columns, row)) for row in rows]

    print(f"Found {len(trades)} closed trades to simulate.\n")

    candle_cache = {}
    results = []

    for i, trade in enumerate(trades):
        symbol = trade['symbol']
        entry_time = trade['entryTime']
        trade_date = entry_time if isinstance(entry_time, datetime) else datetime.fromisoformat(str(entry_time))
        cache_key = (symbol, trade_date.date())

        print(f"[{i+1}/{len(trades)}] {trade['signalType']} {symbol} ({trade['strategyName']}) — Entry ₹{trade['entryPrice']}", end="")

        if cache_key not in candle_cache:
            candle_cache[cache_key] = fetch_intraday_candles(symbol, trade_date)
        candles = candle_cache[cache_key]

        if candles.empty or len(candles) < 5:
            print(f" — ⚠️ Insufficient candle data, skipping")
            continue

        sim = simulate_trade_3phase(trade, candles)

        actual_pnl = trade['pnl'] or 0
        sim_pnl = sim['sim_pnl']
        diff = sim_pnl - actual_pnl

        results.append({
            'id': trade['id'],
            'symbol': symbol,
            'strategy': trade['strategyName'],
            'type': trade['signalType'],
            'entry': trade['entryPrice'],
            'qty': trade['quantity'],
            'actual_exit': trade['exitPrice'],
            'actual_pnl': actual_pnl,
            'actual_outcome': trade['outcome'],
            'sim_pnl': sim_pnl,
            'sim_reason': sim['sim_exit_reason'],
            'sim_state': sim['sim_state'],
            'lot_a': sim['lot_a'],
            'lot_b': sim['lot_b'],
            'lot_c': sim['lot_c'],
            'diff': diff,
        })

        emoji = "✅" if diff > 0 else ("➖" if abs(diff) < 10 else "❌")
        print(f" — Actual: ₹{actual_pnl:.0f} vs 3Phase: ₹{sim_pnl:.0f} ({emoji} {'+' if diff >= 0 else ''}₹{diff:.0f})")
        # Detail line
        la, lb, lc = sim['lot_a'], sim['lot_b'], sim['lot_c']
        print(f"        Lot A({la['qty']}): ₹{la['pnl']:.0f} [{la['reason']}] | "
              f"Lot B({lb['qty']}): ₹{lb['pnl']:.0f} [{lb['reason']}] | "
              f"Lot C({lc['qty']}): ₹{lc['pnl']:.0f} [{lc['reason']}]")

    # ── Summary ──
    if not results:
        print("\n⚠️ No trades could be simulated.")
        return

    print("\n" + "=" * 100)
    print("📊 COMPARISON SUMMARY — 3-Phase vs Actual")
    print("=" * 100)

    total_actual = sum(r['actual_pnl'] for r in results)
    total_sim = sum(r['sim_pnl'] for r in results)
    total_diff = total_sim - total_actual

    actual_wins = sum(1 for r in results if r['actual_pnl'] > 0)
    actual_losses = sum(1 for r in results if r['actual_pnl'] < 0)
    sim_wins = sum(1 for r in results if r['sim_pnl'] > 0)
    sim_losses = sum(1 for r in results if r['sim_pnl'] < 0)
    sim_breakeven = sum(1 for r in results if abs(r['sim_pnl']) < 50)

    improved = sum(1 for r in results if r['diff'] > 10)
    worsened = sum(1 for r in results if r['diff'] < -10)
    unchanged = len(results) - improved - worsened

    saved_trades = [r for r in results if r['actual_outcome'] == 'LOSS' and r['sim_pnl'] >= -50]

    # Lot-level stats
    lot_a_total = sum(r['lot_a']['pnl'] for r in results)
    lot_b_total = sum(r['lot_b']['pnl'] for r in results)
    lot_c_total = sum(r['lot_c']['pnl'] for r in results)

    print(f"\n{'Metric':<30} {'Actual':>15} {'3-Phase':>15} {'Difference':>15}")
    print("-" * 75)
    print(f"{'Total P&L':.<30} {'₹' + f'{total_actual:.0f}':>15} {'₹' + f'{total_sim:.0f}':>15} {'₹' + f'{total_diff:+.0f}':>15}")
    print(f"{'Wins':.<30} {actual_wins:>15} {sim_wins:>15} {sim_wins - actual_wins:>+15}")
    print(f"{'Losses':.<30} {actual_losses:>15} {sim_losses:>15} {sim_losses - actual_losses:>+15}")
    print(f"{'Near-Breakeven (±₹50)':.<30} {'':>15} {sim_breakeven:>15}")
    print(f"{'Win Rate':.<30} {actual_wins/len(results)*100:>14.1f}% {sim_wins/len(results)*100:>14.1f}%")

    print(f"\n📦 Lot-Level P&L Breakdown:")
    print(f"   Lot A (35% @ 50%):  ₹{lot_a_total:+.0f}")
    print(f"   Lot B (35% @ 75%):  ₹{lot_b_total:+.0f}")
    print(f"   Lot C (30% rider):  ₹{lot_c_total:+.0f}")

    print(f"\n📈 Trades IMPROVED: {improved}")
    print(f"📉 Trades WORSENED: {worsened}")
    print(f"➖ Trades UNCHANGED: {unchanged}")

    if saved_trades:
        print(f"\n🔒 Trades SAVED from loss: {len(saved_trades)}")
        for r in saved_trades:
            print(f"   #{r['id']} {r['symbol']} — was ₹{r['actual_pnl']:.0f} (LOSS) → now ₹{r['sim_pnl']:.0f} [{r['sim_reason']}]")

    results_sorted = sorted(results, key=lambda r: r['diff'], reverse=True)
    print(f"\n🏆 Top 5 BIGGEST IMPROVEMENTS:")
    for r in results_sorted[:5]:
        if r['diff'] <= 0:
            break
        print(f"   #{r['id']} {r['type']} {r['symbol']} ({r['strategy']})")
        print(f"      Actual: ₹{r['actual_pnl']:.0f} → 3Phase: ₹{r['sim_pnl']:.0f} (saved ₹{r['diff']:.0f}) [{r['sim_reason']}]")

    print(f"\n⚠️ Top 5 BIGGEST REGRESSIONS:")
    for r in results_sorted[-5:]:
        if r['diff'] >= 0:
            continue
        print(f"   #{r['id']} {r['type']} {r['symbol']} ({r['strategy']})")
        print(f"      Actual: ₹{r['actual_pnl']:.0f} → 3Phase: ₹{r['sim_pnl']:.0f} (lost ₹{abs(r['diff']):.0f}) [{r['sim_reason']}]")

    print(f"\n{'=' * 100}")
    net_emoji = "✅" if total_diff > 0 else "❌"
    print(f"{net_emoji} NET IMPACT: ₹{total_diff:+.0f} ({'BETTER' if total_diff > 0 else 'WORSE'} with 3-Phase Exit)")
    print(f"{'=' * 100}")


if __name__ == "__main__":
    main()
