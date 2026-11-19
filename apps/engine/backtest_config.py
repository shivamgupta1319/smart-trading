"""Backtest realism configuration: position sizing + Indian transaction costs.

All numbers are tunable via env so the backtest can be made conservative or
optimistic without touching strategy code. Defaults approximate a discount
broker (e.g. Zerodha-style) on NSE equity.

Two cost profiles:
  * INTRADAY  — used for 5m / 15m strategies (MIS-style; STT on sell side only)
  * DELIVERY  — used for 1D strategies (CNC-style; STT on both sides, higher stamp)

`CostModel.round_trip` returns the *total* rupee cost of entering AND exiting a
position of a given notional, so the backtest can subtract it from gross P&L to
get a realistic net.
"""
from __future__ import annotations
import os
from dataclasses import dataclass

from shared_config import shared, risk_per_trade_fraction


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return default


# Version tag stamped on every BacktestReport (see reports.save_report). BUMP this
# whenever the fill/exit model changes so stored reports produced by an older engine
# are identifiable — they won't reproduce. Current model: C3 (live intraday exits) + F3
# (swing time-stop).
ENGINE_VERSION = os.getenv("BT_ENGINE_VERSION", "2026.11.19-parity2")


# Buying-power multiple by hold bucket. Intraday (MIS) deploys ~5× the cell fund as
# notional; swing/delivery (CNC) uses the fund 1×. Shared with the API: config/trading.json.
LEVERAGE_INTRADAY = shared("LEVERAGE_INTRADAY")
LEVERAGE_DELIVERY = shared("LEVERAGE_DELIVERY")

# Per-trade risk cap (FEAT-005). Sizing is notional (fund × leverage / entry), which lets a
# wide-stop trade risk multiples of a tight-stop one on the same fund — the payoff-ratio leak
# (avg ₹-loss > avg ₹-win) documented in agent-reports/2026-07-14-avg-loss-gt-avg-win-audit.md.
# We add a second bound: each trade risks at most `fund × RISK_PER_TRADE_PCT` rupees, i.e.
# qty = min(notionalQty, floor(fund × pct / |entry−stop|)); 0 → the trade is skipped.
# Shared with the API (config/trading.json); a fraction, 0.02 = 2% (₹200 on a ₹10k seed).
RISK_PER_TRADE_PCT = risk_per_trade_fraction()

# Cost-to-risk gate: skip a trade whose round-trip cost (charges + slippage both ways)
# exceeds this share of the rupees it risks. 0 = off. Shared with the API, which
# rejects the same signals (config/trading.json).
#
# Why: on a Rs 10k cell the round trip costs about 0.2% of the position. With a 0.3%
# stop that is two thirds of the risk gone before the trade starts. Measured on all
# 60 stocks (2026-11): average intraday result -0.35R with no gate, -0.14R at 0.25,
# and no strategy got worse.
MAX_COST_TO_RISK = shared("MAX_COST_TO_RISK")

# Smallest price step on NSE cash equities, in rupees (shared with the API).
TICK_SIZE = shared("TICK_SIZE")


def slippage_per_share(price: float) -> float:
    """Rupees of slippage per share on one side of a trade: the larger of one price tick
    and the configured basis points of the price.

    A flat 5 basis points understates a cheap stock (one Rs 0.05 tick on a Rs 60 share is
    8 basis points: you cannot be filled closer than a tick) and is about right for an
    expensive one. MUST match `slippagePerShare` in apps/api/src/common/costs.ts.
    """
    return max(TICK_SIZE, price * RISK.slippage_bps / 10_000.0)


def cost_to_risk(qty: int, entry: float, risk_per_share: float, timeframe: str) -> float:
    """Round-trip cost of a position (charges + slippage on both sides) divided by
    the rupees it risks. MUST match `costToRisk` in apps/api/src/common/costs.ts."""
    value = qty * entry
    friction = CostModel(timeframe).round_trip(value, value) + 2 * qty * slippage_per_share(entry)
    return friction / (qty * risk_per_share)


@dataclass(frozen=True)
class RiskConfig:
    initial_capital: float = _f("BT_INITIAL_CAPITAL", 100_000.0)
    # The portfolio runs up to N equal-weight slots concurrently (live model).
    # A single-cell backtest simulates ONE such slot traded repeatedly, so its
    # ROI is directly comparable to a live slot. MUST match the API's
    # MAX_CONCURRENT_POSITIONS (apps/api/src/common/risk.ts).
    max_concurrent_positions: int = _i("BT_MAX_CONCURRENT_POSITIONS", 10)
    # Risk a fixed % of *slot* capital per trade.
    risk_per_trade_pct: float = _f("BT_RISK_PER_TRADE_PCT", 2.0)
    # Slippage applied to BOTH entry and exit, in basis points (1bp = 0.01%).
    slippage_bps: float = shared("BT_SLIPPAGE_BPS")  # shared with the API (cost-to-risk gate)
    # When a single bar's range straddles both SL and TP, assume the worse
    # outcome (SL) filled first. Removes the classic optimistic bias.
    pessimistic_intrabar: bool = os.getenv("BT_PESSIMISTIC_INTRABAR", "true").lower() != "false"
    # Enter on the NEXT bar's open (realistic) rather than the signal bar close.
    next_bar_entry: bool = os.getenv("BT_NEXT_BAR_ENTRY", "true").lower() != "false"
    # When a bar OPENS beyond the stop (overnight gap, circuit), fill the stop at
    # that open, not at the stop price. A stop is a market order once triggered:
    # the stop price never traded, so booking it there invents money on exactly
    # the bars where swing stops get hit. "false" restores the old stop-price fill.
    gap_through_stop_at_open: bool = os.getenv("BT_GAP_THROUGH_STOP_AT_OPEN", "true").lower() != "false"
    # Cap each position's notional at `max_position_value` (fund × intraday leverage)
    # instead of letting it compound with the cell's running equity. Without this,
    # `qty = current_capital × leverage / entry` compounds geometrically over a long
    # backtest, inflating ROI absurdly (a ₹10k slot → +₹187k / +639%) and poisoning
    # every ROI-based auto-select gate/rank. Capping keeps the equity curve additive
    # and the reported ROI honest & comparable across cells. Env: BT_CAP_POSITION_VALUE.
    cap_position_value: bool = os.getenv("BT_CAP_POSITION_VALUE", "true").lower() != "false"

    @property
    def slot_capital(self) -> float:
        """Per-cell fund seed (₹1L / 10 = ₹10,000). Each (stock × strategy) cell
        compounds its own ₹10k, matching the live per-cell model."""
        slots = self.max_concurrent_positions if self.max_concurrent_positions > 0 else 1
        return self.initial_capital / slots

    @property
    def max_position_value(self) -> float:
        """Rupees deployable per position = fund × intraday leverage (kept for
        reference; sizing in base.py applies the per-bucket leverage directly)."""
        return self.slot_capital * LEVERAGE_INTRADAY


@dataclass(frozen=True)
class CostProfile:
    brokerage_pct: float       # % of turnover per side
    brokerage_flat_cap: float  # rupee cap per side
    stt_buy_pct: float         # % on buy turnover
    stt_sell_pct: float        # % on sell turnover
    exchange_txn_pct: float    # % of turnover (both sides)
    sebi_pct: float            # % of turnover (both sides)
    stamp_buy_pct: float       # % on buy side only
    gst_pct: float             # % on (brokerage + exchange txn)
    dp_charge_per_sell: float  # flat rupee fee per delivery (CNC) sell, incl. GST


# Approximate NSE discount-broker schedules (as of ~2025-26). Values are shared with
# the API's costs.ts through config/trading.json; env vars of the same name override.
INTRADAY_PROFILE = CostProfile(
    brokerage_pct=shared("BT_INTRADAY_BROKERAGE_PCT"),
    brokerage_flat_cap=shared("BT_BROKERAGE_FLAT_CAP"),
    stt_buy_pct=shared("BT_INTRADAY_STT_BUY_PCT"),
    stt_sell_pct=shared("BT_INTRADAY_STT_SELL_PCT"),
    exchange_txn_pct=shared("BT_EXCHANGE_TXN_PCT"),
    sebi_pct=shared("BT_SEBI_PCT"),
    stamp_buy_pct=shared("BT_INTRADAY_STAMP_BUY_PCT"),
    gst_pct=shared("BT_GST_PCT"),
    dp_charge_per_sell=0.0,  # no delivery leg for intraday (MIS) — no DP charge
)

DELIVERY_PROFILE = CostProfile(
    brokerage_pct=shared("BT_DELIVERY_BROKERAGE_PCT"),  # many brokers: free CNC
    brokerage_flat_cap=shared("BT_BROKERAGE_FLAT_CAP"),
    stt_buy_pct=shared("BT_DELIVERY_STT_BUY_PCT"),
    stt_sell_pct=shared("BT_DELIVERY_STT_SELL_PCT"),
    exchange_txn_pct=shared("BT_EXCHANGE_TXN_PCT"),
    sebi_pct=shared("BT_SEBI_PCT"),
    stamp_buy_pct=shared("BT_DELIVERY_STAMP_BUY_PCT"),
    gst_pct=shared("BT_GST_PCT"),
    # Dhan: ₹12.50 + 18% GST ≈ ₹14.75 per ISIN per day on every CNC sell (flat, not turnover-based).
    dp_charge_per_sell=shared("BT_DP_CHARGE_PER_DELIVERY_SELL"),
)


class CostModel:
    """Computes realistic round-trip transaction costs for one position."""

    def __init__(self, timeframe: str):
        self.profile = DELIVERY_PROFILE if str(timeframe).upper() in ("1D", "1W") else INTRADAY_PROFILE

    def _brokerage(self, turnover: float) -> float:
        p = self.profile
        return min(turnover * p.brokerage_pct / 100.0, p.brokerage_flat_cap)

    def round_trip(self, buy_value: float, sell_value: float) -> float:
        """Total rupee cost to buy `buy_value` and sell `sell_value` of stock."""
        p = self.profile
        brokerage = self._brokerage(buy_value) + self._brokerage(sell_value)
        stt = buy_value * p.stt_buy_pct / 100.0 + sell_value * p.stt_sell_pct / 100.0
        exch = (buy_value + sell_value) * p.exchange_txn_pct / 100.0
        sebi = (buy_value + sell_value) * p.sebi_pct / 100.0
        stamp = buy_value * p.stamp_buy_pct / 100.0
        gst = (brokerage + exch) * p.gst_pct / 100.0
        # Flat DP charge, once per delivery sell (already GST-inclusive; 0 for intraday).
        dp = p.dp_charge_per_sell
        return brokerage + stt + exch + sebi + stamp + gst + dp


RISK = RiskConfig()


# --- Reward:risk by hold-duration bucket (validated R:R-by-horizon model) -------
# Longer holds justify a higher reward multiple (lower win rate, bigger winners).
# The STOP stays whatever each strategy set (that defines risk); only the target
# distance is standardised per bucket. None = keep the strategy's native target
# (INTRADAY keeps its own ~2R — wider isn't realistically capturable same-day).
# All env-tunable, e.g. TARGET_R_SHORT_SWING=3.5.
def _target_r(name: str, default: float):
    v = _f(name, default)
    return v if v and v > 0 else None


TARGET_R_BY_BUCKET = {
    "INTRADAY": _target_r("TARGET_R_INTRADAY", 0.0),          # 0 -> keep native
    "SHORT_SWING": _target_r("TARGET_R_SHORT_SWING", 3.0),
    "MID_SWING": _target_r("TARGET_R_MID_SWING", 4.0),
    "LONG_POSITIONAL": _target_r("TARGET_R_LONG_POSITIONAL", 5.0),
}


def target_r_for_bucket(bucket: str | None):
    """Reward:risk multiple to apply for a hold-duration bucket, or None to keep
    the strategy's own target."""
    return TARGET_R_BY_BUCKET.get(bucket) if bucket else None


# --- Swing exit style: ATR chandelier trailing stop + fixed R target -----------
# Swing/mid/long trades trail the stop at (peak-since-entry ∓ mult×ATR) and exit
# at the fixed R target OR the trailing stop, whichever hits first — no partial
# booking, no reversal exit (those stay INTRADAY-only). Intraday keeps a plain
# fixed SL/TP in the backtest. Modelled the same way in backtest and live.
TRAILING_BUCKETS = {"SHORT_SWING", "MID_SWING", "LONG_POSITIONAL"}
SWING_TRAIL_ATR_PERIOD = _i("SWING_TRAIL_ATR_PERIOD", 14)
# ATR multiple for the chandelier trail, BY bucket. Wider targets need wider
# trails (a tight trail just clips the winner before it reaches a far target);
# tuned on the user's data — looser for longer holds. Env-overridable.
TRAIL_ATR_MULT_BY_BUCKET = {
    "SHORT_SWING": _f("SWING_TRAIL_ATR_MULT_SHORT", 6.0),
    "MID_SWING": _f("SWING_TRAIL_ATR_MULT_MID", 5.0),
    "LONG_POSITIONAL": _f("SWING_TRAIL_ATR_MULT_LONG", 8.0),
}


def uses_trailing_exit(bucket: str | None) -> bool:
    return bucket in TRAILING_BUCKETS


def trail_mult_for_bucket(bucket: str | None) -> float:
    return TRAIL_ATR_MULT_BY_BUCKET.get(bucket, 5.0)


# --- Swing time-stop by hold bucket (audit F3) --------------------------------
# A swing that neither stops out nor reaches target just hogs its cell's fund
# (INFY·Channel_Oscillation sat open 3 weeks). Exit flat after N bars held.
# Every swing/mid/long strategy is 1D (see strategies.STRATEGY_TIMEFRAMES), so
# "N bars" == "N trading days" — which is what lets live count completed daily
# candles and stay in parity with the backtest's bar walk.
# INTRADAY is deliberately absent: the 15:15 square-off already bounds it.
# 0 / negative disables the stop for that bucket.
# MUST stay mirrored in scanner/live_scanner.auto_close_signals or backtest≠live.
#
# OFF by default (0). It was measured to hurt 15 of 16 swing strategies (it cuts a
# trade that is aiming for 3R to 5R after 10 to 40 days) and the live stack has run with
# it off since July 2026. The code default used to be 10/20/40 while the live containers
# were set to 0, so a backtest run outside those containers used a rule live does not
# have: the swing figures published on 2026-11-19 were wrong for that reason. The default
# now matches live. To try a time-stop, set e.g. TIME_STOP_BARS_SHORT_SWING=10 on the
# engine AND the scanner.
TIME_STOP_BARS_BY_BUCKET = {
    "SHORT_SWING": _i("TIME_STOP_BARS_SHORT_SWING", 0),
    "MID_SWING": _i("TIME_STOP_BARS_MID_SWING", 0),
    "LONG_POSITIONAL": _i("TIME_STOP_BARS_LONG_POSITIONAL", 0),
}


def time_stop_bars_for_bucket(bucket: str | None) -> int | None:
    """Bars to hold a swing before exiting flat, or None if this bucket is unbounded.

    Exit convention (backtest AND live): the condition "N bars held, neither stop
    nor target hit" is only knowable once bar N has CLOSED, so the exit lands on
    bar N+1 — same reasoning as RiskConfig.next_bar_entry. Backtest exits at
    o[entry_idx + N + 1]; live exits at the first poll once N completed daily
    candles exist after the entry date, which is that same session.
    """
    n = TIME_STOP_BARS_BY_BUCKET.get(bucket) if bucket else None
    return n if n and n > 0 else None
