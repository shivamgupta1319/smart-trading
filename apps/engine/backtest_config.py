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
    slippage_bps: float = _f("BT_SLIPPAGE_BPS", 5.0)
    # When a single bar's range straddles both SL and TP, assume the worse
    # outcome (SL) filled first. Removes the classic optimistic bias.
    pessimistic_intrabar: bool = os.getenv("BT_PESSIMISTIC_INTRABAR", "true").lower() != "false"
    # Enter on the NEXT bar's open (realistic) rather than the signal bar close.
    next_bar_entry: bool = os.getenv("BT_NEXT_BAR_ENTRY", "true").lower() != "false"

    @property
    def slot_capital(self) -> float:
        """Rupees allocated to one position slot (₹1L / 10 = ₹10,000)."""
        slots = self.max_concurrent_positions if self.max_concurrent_positions > 0 else 1
        return self.initial_capital / slots

    @property
    def max_position_value(self) -> float:
        """Hard cap on rupees deployed per position = one slot (no leverage)."""
        return self.slot_capital


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


# Approximate NSE discount-broker schedules (as of ~2025-26). Tunable via env.
INTRADAY_PROFILE = CostProfile(
    brokerage_pct=_f("BT_INTRADAY_BROKERAGE_PCT", 0.03),
    brokerage_flat_cap=_f("BT_BROKERAGE_FLAT_CAP", 20.0),
    stt_buy_pct=_f("BT_INTRADAY_STT_BUY_PCT", 0.0),
    stt_sell_pct=_f("BT_INTRADAY_STT_SELL_PCT", 0.025),
    exchange_txn_pct=_f("BT_EXCHANGE_TXN_PCT", 0.00297),
    sebi_pct=_f("BT_SEBI_PCT", 0.0001),
    stamp_buy_pct=_f("BT_INTRADAY_STAMP_BUY_PCT", 0.003),
    gst_pct=_f("BT_GST_PCT", 18.0),
)

DELIVERY_PROFILE = CostProfile(
    brokerage_pct=_f("BT_DELIVERY_BROKERAGE_PCT", 0.0),  # many brokers: free CNC
    brokerage_flat_cap=_f("BT_BROKERAGE_FLAT_CAP", 20.0),
    stt_buy_pct=_f("BT_DELIVERY_STT_BUY_PCT", 0.1),
    stt_sell_pct=_f("BT_DELIVERY_STT_SELL_PCT", 0.1),
    exchange_txn_pct=_f("BT_EXCHANGE_TXN_PCT", 0.00297),
    sebi_pct=_f("BT_SEBI_PCT", 0.0001),
    stamp_buy_pct=_f("BT_DELIVERY_STAMP_BUY_PCT", 0.015),
    gst_pct=_f("BT_GST_PCT", 18.0),
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
        return brokerage + stt + exch + sebi + stamp + gst


RISK = RiskConfig()
