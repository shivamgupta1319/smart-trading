"""Regression tests for the v2 authenticity fixes:

  * 200-MA swing strategies no longer raise on short (walk-forward) slices.
  * BB mean-reversion intraday emits only valid-geometry trades.
  * The backtest sizes each trade to ONE portfolio slot (slot_capital), and
    reports ROI against that slot.

Run from apps/engine:  python -m pytest test/test_roadmap_fixes.py -q
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_config import RISK  # noqa: E402
from strategies.base import BaseStrategy  # noqa: E402
from strategies.swing.golden_cross import GoldenCrossStrategy  # noqa: E402
from strategies.swing.ema200_macd import EMA200MACDStrategy  # noqa: E402
from strategies.swing.sma44_pullback import SMA44PullbackStrategy  # noqa: E402
from strategies.intraday.bb_mean_reversion_intraday import (  # noqa: E402
    BBMeanReversionIntradayStrategy,
)


def _random_ohlc(n, seed=0, freq="D"):
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.standard_normal(n) * 0.5)
    df = pd.DataFrame({
        "Open": base,
        "High": base + np.abs(rng.standard_normal(n)),
        "Low": base - np.abs(rng.standard_normal(n)),
        "Close": base + rng.standard_normal(n) * 0.2,
        "Volume": rng.integers(1000, 9000, n),
    })
    df.index = pd.date_range("2024-01-01", periods=n, freq=freq)
    return df


@pytest.mark.parametrize("Strat", [GoldenCrossStrategy, EMA200MACDStrategy, SMA44PullbackStrategy])
@pytest.mark.parametrize("n", [20, 50, 80, 199])
def test_200ma_strategies_safe_on_short_slices(Strat, n):
    """Walk-forward folds can be <200 bars; pandas_ta returns None there. The
    guard must produce a clean zero-signal frame instead of raising."""
    df = _random_ohlc(n, seed=n)
    out = Strat().generate_signals(df.copy())
    for col in ("signal", "stop_loss", "target"):
        assert col in out.columns
    assert (out["signal"] == 0).all()
    # run_backtest must not raise either (this is what 500'd /run-walk-forward).
    m = Strat().run_backtest(df.copy())
    assert m["totalTrades"] == 0


def test_bb_mean_reversion_geometry_is_valid():
    """Every emitted long must have target above entry-ish (room to the mid
    band); shorts the reverse. Invalid geometry would be silently skipped."""
    df = _random_ohlc(400, seed=7, freq="15min")
    out = BBMeanReversionIntradayStrategy().generate_signals(df.copy())
    longs = out[out["signal"] == 1]
    shorts = out[out["signal"] == -1]
    # For longs the target (mid band) must sit above the signal close.
    assert (longs["target"] > longs["Close"]).all()
    assert (longs["stop_loss"] < longs["Close"]).all()
    # For shorts the target must sit below the signal close.
    assert (shorts["target"] < shorts["Close"]).all()
    assert (shorts["stop_loss"] > shorts["Close"]).all()


def test_backtest_sizes_to_one_slot():
    """A single-cell backtest must cap notional at one slot (slot_capital) and
    report ROI against the slot, not the whole ₹1L account."""
    from backtest_config import LEVERAGE_INTRADAY
    assert RISK.slot_capital == RISK.initial_capital / RISK.max_concurrent_positions
    # Notional is capped at one slot × intraday leverage (the reworked cap), not the
    # bare slot — so a compounding cell can still deploy its leveraged notional.
    assert RISK.max_position_value == RISK.slot_capital * LEVERAGE_INTRADAY

    class _OneBuy(BaseStrategy):
        name, timeframe = "ONE_BUY", "1D"

        def generate_signals(self, df):
            df = df.copy()
            df["signal"] = 0
            df.iloc[0, df.columns.get_loc("signal")] = 1
            df["stop_loss"] = 95.0
            df["target"] = 110.0
            return df

    # entry ~100, target 110 hit on bar 2's high.
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    df = pd.DataFrame({
        "Open": [100, 100, 101], "High": [101, 102, 111],
        "Low": [99, 99, 100], "Close": [100, 101, 105],
    }, index=idx)
    sim = _OneBuy().simulate(df)
    # Sizing = min(notional, per-trade risk cap). 1D → delivery leverage 1×, notional =
    # slot_capital = 10k → notionalQty = floor(10k/entry~100) ≈ 99. Risk cap (FEAT-005):
    # riskBudget = 10k×0.02 = 200, risk/share = |entry−95| ≈ 5 → riskQty = 40, so the cap
    # binds and qty = 40. ROI denominator is still the slot, independent of qty.
    m = _OneBuy().run_backtest(df)
    assert m["totalTrades"] == 1
    # ROI denominator is the slot, so netProfit / slot_capital * 100 == roiPercentage.
    assert m["roiPercentage"] == pytest.approx(m["netProfit"] / RISK.slot_capital * 100, abs=0.01)


def test_per_trade_risk_cap_bounds_wide_stops():
    """FEAT-005: sizing bounds rupee-risk at fund × RISK_PER_TRADE_PCT, so a wide-stop
    trade can't out-risk a tight-stop one on the same fund. Mirrors the live formula in
    apps/api/src/common/risk.ts (parity)."""
    from backtest_config import RISK_PER_TRADE_PCT, LEVERAGE_INTRADAY, LEVERAGE_DELIVERY

    def qty(cell, lev, entry, stop, pct=RISK_PER_TRADE_PCT, cap=None):
        notional = cell * lev
        if cap is not None:
            notional = min(notional, cap)
        notional_qty = int(notional / entry)
        rps = abs(entry - stop)
        risk_qty = int((cell * pct) / rps) if rps > 0 else notional_qty
        return max(1, min(notional_qty, risk_qty))

    assert RISK_PER_TRADE_PCT == 0.02  # keep in lockstep with risk.ts default
    # Wide-stop swing (live open #241 IFCI·Fibonacci): notional 128 sh, cap trims to 38.
    assert qty(10000, LEVERAGE_DELIVERY, 78.00, 72.86) == 38
    # entry == stop → cap inert (no div-by-zero), falls back to notional qty.
    assert qty(10000, LEVERAGE_DELIVERY, 78.00, 78.00) == int(10000 / 78.00)
    # Cap disabled (pct huge) → qty equals the pre-feature notional qty (purely additive).
    assert qty(10000, LEVERAGE_DELIVERY, 78.00, 72.86, pct=1.0) == int(10000 / 78.00)
    # A fund too small for one risk-unit still trades ≥1 share.
    assert qty(500, LEVERAGE_DELIVERY, 78.00, 40.00) >= 1


# ── FEAT-005 Phase 4 / audit F3 — swing time-stop ─────────────────────────────

def _flat_swing_frame():
    """15 daily bars that never touch SL (90) or target (200), so only a time-stop
    can end the trade. Bar 12 opens at a distinctive 105 (the expected time-stop
    exit); the last bar closes at 90.5 (where a time-stop-less walk would mark out).
    The 98–102 range keeps ATR ≈ 4, so the chandelier trail sits at peak − 6×4 ≈ 78,
    far under the 90 stop — the trail provably never binds and can't confound this.
    """
    n = 15
    o = [100.0] * n
    o[12] = 105.0
    h = [102.0] * n
    h[12] = 106.0
    low = [98.0] * n
    low[14] = 90.4  # still above the 90 stop
    c = [100.0] * n
    c[14] = 90.5
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"Open": o, "High": h, "Low": low, "Close": c, "Volume": [5000] * n}, index=idx
    )


class _SwingHold(BaseStrategy):
    # Name must be a real SHORT_SWING key — _hold_bucket() resolves the bucket (and
    # hence the 10-bar time-stop) through STRATEGY_HOLD_DURATIONS.
    name, timeframe = "SMA44_Pullback", "1D"

    def generate_signals(self, df):
        df = df.copy()
        df["signal"] = 0
        df.iloc[0, df.columns.get_loc("signal")] = 1
        df["stop_loss"] = 90.0
        df["target"] = 200.0
        return df


def test_time_stop_bars_for_bucket_semantics():
    """INTRADAY is unbounded (15:15 square-off already ends it); 0 disables a bucket."""
    import backtest_config as bc

    assert bc.time_stop_bars_for_bucket("SHORT_SWING") == 10
    assert bc.time_stop_bars_for_bucket("MID_SWING") == 20
    assert bc.time_stop_bars_for_bucket("LONG_POSITIONAL") == 40
    assert bc.time_stop_bars_for_bucket("INTRADAY") is None
    assert bc.time_stop_bars_for_bucket(None) is None


def test_swing_time_stop_exits_on_the_bar_after_n(monkeypatch):
    """F3: a swing that hits neither stop nor target exits at the open of bar N+1.

    Entry is bar 1 (next_bar_entry), the SHORT_SWING stop is 10 bars, so the walk
    exits at bar 12's open (105) — NOT at the series end (90.5). This is the exact
    bar `live_scanner.auto_close_signals` fires on: the first session once 10
    completed daily candles exist after the entry date.
    """
    import backtest_config as bc

    df = _flat_swing_frame()
    slip = RISK.slippage_bps / 10_000.0
    entry = 100.0 * (1 + slip)  # bar 1 open + adverse slippage

    # qty = min(notional, risk cap) — the FEAT-005 cap binds here (wide 10-pt stop).
    notional_qty = int(RISK.slot_capital * 1.0 / entry)  # 1D → delivery leverage 1×
    risk_qty = int((RISK.slot_capital * bc.RISK_PER_TRADE_PCT) / abs(entry - 90.0))
    qty = max(1, min(notional_qty, risk_qty))

    sim = _SwingHold().simulate(df)
    assert len(sim["gross_trades"]) == 1
    expected = (105.0 * (1 - slip) - entry) * qty  # exit at bar 12's OPEN
    assert sim["gross_trades"][0] == pytest.approx(expected, abs=0.01)

    # Same frame with the stop disabled → the walk runs to the series end and marks
    # to the last close (90.5), a loss. Proves the exit above is the time-stop's doing
    # and that the feature is purely additive when switched off.
    monkeypatch.setattr(bc, "TIME_STOP_BARS_BY_BUCKET", {})
    off = _SwingHold().simulate(df)
    assert len(off["gross_trades"]) == 1
    assert off["gross_trades"][0] == pytest.approx((90.5 * (1 - slip) - entry) * qty, abs=0.01)
    assert off["gross_trades"][0] < 0 < sim["gross_trades"][0]


def test_intraday_is_untouched_by_the_time_stop():
    """The time-stop is swing-only: INTRADAY still exits via the 3-phase/square-off
    path, so no bucket without a configured stop changes behaviour."""
    import backtest_config as bc

    assert "INTRADAY" not in bc.TIME_STOP_BARS_BY_BUCKET


# ── Audit 2026-07-15 F3 — persist the honest edge metrics ─────────────────────

def test_run_backtest_reports_measured_span_years():
    """spanYears must be MEASURED from the bars, not assumed per timeframe: raw ROI is
    cumulative over whatever history is stored (1D ≈ 5.1y vs 15m/5m ≈ 4.7mo), so the UI
    can only annualise honestly if the engine reports the actual span."""
    class _Noop(BaseStrategy):
        name, timeframe = "SPAN_PROBE", "1D"

        def generate_signals(self, df):
            df = df.copy()
            df["signal"] = 0
            df["stop_loss"] = 0.0
            df["target"] = 0.0
            return df

    idx = pd.date_range("2021-01-01", "2026-01-01", freq="D")
    df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
                       "Volume": 1000}, index=idx)
    assert _Noop().run_backtest(df)["spanYears"] == pytest.approx(5.0, abs=0.02)

    # Unknown rather than a wrong guess: no usable index → 0.0, and never raises
    # (a backtest must not die because the span can't be derived).
    assert _Noop().run_backtest(df.reset_index(drop=True))["spanYears"] == 0.0
    assert _Noop().run_backtest(df.iloc[:1])["spanYears"] == 0.0


def test_metrics_expose_the_edge_fields_reports_persists():
    """The four edge metrics + spanYears must be present on EVERY run_backtest result —
    reports.save_report writes exactly these, and they were silently dropped before
    (F3), leaving roiPercentage as the only rankable column."""
    df = _flat_swing_frame()
    m = _SwingHold().run_backtest(df)
    for k in ("avgRMultiple", "profitFactor", "maxDrawdownPct", "expectancy",
              "spanYears", "roiPercentage", "totalTrades"):
        assert k in m, f"{k} missing from run_backtest metrics"
    assert m["totalTrades"] == 1
    # avgR is net ÷ rupees risked — sign must agree with the trade's P&L, and it is
    # NOT the ROI (different denominators: risk vs the ₹10k fund).
    assert m["avgRMultiple"] > 0
    assert m["avgRMultiple"] != m["roiPercentage"]


def test_zero_trade_cell_still_reports_every_field():
    """A 0-trade cell must not omit keys — save_report would KeyError on the UPSERT."""
    class _NoSignal(BaseStrategy):
        name, timeframe = "NO_SIGNAL", "1D"

        def generate_signals(self, df):
            df = df.copy()
            df["signal"] = 0
            df["stop_loss"] = 0.0
            df["target"] = 0.0
            return df

    m = _NoSignal().run_backtest(_flat_swing_frame())
    assert m["totalTrades"] == 0
    for k in ("avgRMultiple", "profitFactor", "maxDrawdownPct", "expectancy", "spanYears"):
        assert k in m
