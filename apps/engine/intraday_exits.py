"""Shared intraday exit primitives — the SINGLE source of truth for the live
scanner's 3-phase exit and the backtest that models it.

The live scanner (`scanner/live_scanner.py`) and the backtest simulation
(`strategies/base.py`) both import from here so the two can never drift. Keep
this module pure: no network, no DB, no I/O — only OHLCV math on pandas frames
and plain scalars.

The 3-phase intraday exit (buy shown; short is the mirror):
  * PHASE 1 (0–49% of the way to target): original stop.
  * PHASE 2 (>= 50%): book 35%, move the stop to breakeven (entry ± 0.1%).
  * PHASE 3 (>= 75%): book another 35%, trail the stop below the previous
    candle's low (± 0.1%).
  * Reversal zone (>= 80%): exit the remainder on a reversal candle pattern.
Plus a hard 15:15 IST square-off of anything still open (intraday is MIS).
"""
import os
from datetime import time as dtime

import pandas_ta as ta

# ── Phase triggers: fraction of the entry→target distance ───────────────────
PHASE2_TRIGGER = 0.50        # book 35% + stop to breakeven
PHASE3_TRIGGER = 0.75        # book another 35% + start the candle trail
REVERSAL_ZONE_START = 0.80   # begin reversal-pattern checks on the remainder

# ── Sizing / offsets ────────────────────────────────────────────────────────
PARTIAL_FRACTION = 0.35      # fraction of the ORIGINAL qty booked at each phase
BREAKEVEN_OFFSET = 0.001     # breakeven stop sits 0.1% the safe side of entry
TRAIL_OFFSET = 0.001         # phase-3 trail sits 0.1% below/above the prev candle
# Positions smaller than this never partial-exit (booking 35% of 1-2 shares is moot).
MIN_QTY_FOR_PARTIAL = int(os.getenv("MIN_QTY_FOR_PARTIAL", "3"))

# Hard square-off: intraday (MIS) is force-closed at/after 15:15 IST.
SQUARE_OFF_TIME = dtime(15, 15)


def calculate_progress(entry: float, target: float, current: float, is_buy: bool) -> float:
    """How far price has moved from entry toward target (0.0 to 1.0+).
    Negative if price moved against the trade."""
    total_distance = abs(target - entry)
    if total_distance == 0:
        return 0.0
    moved = current - entry if is_buy else entry - current
    return moved / total_distance


def progress_price(entry: float, target: float, fraction: float, is_buy: bool) -> float:
    """The price at which `calculate_progress` equals `fraction` — i.e. the level
    that triggers a phase transition. Inverse of `calculate_progress`."""
    distance = abs(target - entry) * fraction
    return entry + distance if is_buy else entry - distance


def breakeven_stop(entry: float, is_buy: bool) -> float:
    """Phase-2 breakeven stop: 0.1% the profitable side of entry."""
    return entry + entry * BREAKEVEN_OFFSET if is_buy else entry - entry * BREAKEVEN_OFFSET


def candle_trail_stop(prev_low: float, prev_high: float, is_buy: bool) -> float:
    """Phase-3 trailing stop: 0.1% beyond the previous candle's low (buy) / high (short)."""
    return prev_low - prev_low * TRAIL_OFFSET if is_buy else prev_high + prev_high * TRAIL_OFFSET


def detect_reversal(df, is_buy: bool) -> tuple[bool, str]:
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
