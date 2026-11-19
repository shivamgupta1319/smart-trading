"""RebalanceEngine tests on synthetic panels where the fill is known by arithmetic.

The engine that runs cross-sectional momentum -- the one strategy that passes the friction gate.
The properties that matter: fills are at the NEXT open (no lookahead), sleeves rotate at rebalance
dates, sizing follows the slot atom, and there is NO stop (so no R -- the metric is period return).
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading.core.slippage import SlippageConfig
from trading.engine.rebalance_engine import Panel, run
from trading.engine.stop_engine import EngineConfig

NO_SLIP = SlippageConfig(k=0.0, floor_bps=0.0)
CFG = EngineConfig(tick=1e-9, spread=0.0)


def sym_frame(dates, opens, closes=None):
    closes = closes if closes is not None else opens
    return pd.DataFrame(
        {
            "Open": opens,
            "High": [max(o, c) for o, c in zip(opens, closes, strict=True)],
            "Low": [min(o, c) for o, c in zip(opens, closes, strict=True)],
            "Close": closes,
            "Volume": 1000,
        },
        index=pd.DatetimeIndex(dates),
    )


def make_panel(**series) -> Panel:
    """make_panel(A=[opens...], B=[...]) over a shared daily index."""
    n = len(next(iter(series.values())))
    dates = pd.bdate_range("2024-01-01", periods=n)
    return Panel({s: sym_frame(dates, opens) for s, opens in series.items()})


def targets(rows: list[tuple]) -> pd.DataFrame:
    """rows: (rebalance_ts, symbol, weight)."""
    idx = pd.MultiIndex.from_tuples(
        [(pd.Timestamp(t), s) for t, s, _ in rows], names=["rebalance_ts", "symbol"]
    )
    return pd.DataFrame({"weight": [w for _, _, w in rows]}, index=idx)


class TestPanel:
    def test_next_open_skips_to_the_bar_after(self):
        p = make_panel(A=[100, 110, 120, 130])
        dates = p.dates
        ts, px = p.next_open(dates[0], "A")
        assert ts == dates[1]  # strictly after
        assert px == 110.0

    def test_next_open_returns_none_past_the_end(self):
        p = make_panel(A=[100, 110])
        assert p.next_open(p.dates[-1], "A") is None

    def test_nan_opens_are_skipped(self):
        p = make_panel(A=[100, float("nan"), 120])
        ts, px = p.next_open(p.dates[0], "A")
        assert px == 120.0  # the NaN bar is not tradeable


class TestFills:
    def test_a_single_sleeve_enters_next_open_and_exits_at_rotation(self):
        # Rebalance day0 -> hold A. Enter day1 open (110). Rebalance day2 -> exit day3 open.
        p = make_panel(A=[100, 110, 120, 130, 140])
        t = targets([(p.dates[0], "A", 1.0), (p.dates[2], "A", 0.0)])
        r = run(p, t, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)
        assert r.n_positions == 1
        pos = r.positions[0]
        assert pos.entry == pytest.approx(110.0)  # day1 open
        assert pos.exit == pytest.approx(130.0)  # day3 open (first open after the day2 rebalance)
        assert pos.gross > 0

    def test_no_lookahead_target_on_the_rebalance_bar_fills_next_day(self):
        p = make_panel(A=[100, 200, 300])
        t = targets([(p.dates[0], "A", 1.0)])
        pos = run(p, t, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP).positions[0]
        assert pos.entry == pytest.approx(200.0)  # day1, NOT day0's 100

    def test_final_period_marks_to_last_close(self):
        # Only one rebalance; the sleeve is held to the end and marked to the last close.
        p = make_panel(A=[100, 110, 120, 130])
        t = targets([(p.dates[0], "A", 1.0)])
        pos = run(p, t, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP).positions[0]
        assert pos.exit == pytest.approx(130.0)


class TestTopKSelection:
    def test_holds_only_the_targeted_names(self):
        p = make_panel(A=[100] * 4, B=[100] * 4, C=[100] * 4)
        # Top-2 basket: A and C, not B.
        t = targets([(p.dates[0], "A", 0.5), (p.dates[0], "C", 0.5)])
        r = run(p, t, n_slots=2, cfg=CFG, slip_cfg=NO_SLIP)
        assert {pos.symbol for pos in r.positions} == {"A", "C"}

    def test_weight_splits_the_commitment(self):
        # n_slots=2 -> Rs 20,000; weight 0.5 each -> Rs 10,000 per sleeve.
        # At entry ~100 that is ~100 shares; the tiny test slippage nudges entry to
        # 100.000000001, so floor(10000 / that) = 99 -- the same "we do not round" float-noise
        # at the sizing crossover the docs pin (499 vs 500 shares). Not a bug.
        p = make_panel(A=[100] * 3, C=[100] * 3)
        t = targets([(p.dates[0], "A", 0.5), (p.dates[0], "C", 0.5)])
        r = run(p, t, n_slots=2, cfg=CFG, slip_cfg=NO_SLIP)
        for pos in r.positions:
            assert pos.qty == 99


class TestZeroWeight:
    def test_a_zero_weight_row_is_ignored_not_counted_as_unfilled(self):
        """A weight-0 target means "not held" -- it must not create a position AND must not count
        as `unfilled` (which means "wanted to hold but couldn't"). Without the weight>0 filter, a
        zero-weight row falls through to the qty<=0 skip and wrongly inflates unfilled."""
        p = make_panel(A=[100, 110, 120], B=[100, 110, 120])
        t = targets([(p.dates[0], "A", 1.0), (p.dates[0], "B", 0.0)])
        r = run(p, t, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)
        assert {pos.symbol for pos in r.positions} == {"A"}
        assert r.unfilled == 0  # B was weight 0, not an unfillable want


class TestSizingAndSkips:
    def test_a_name_with_no_open_after_rebalance_is_unfilled_not_a_crash(self):
        # B stops trading (NaN) right after the rebalance -> no tradeable open -> unfilled.
        p = make_panel(A=[100, 110, 120], B=[100, float("nan"), float("nan")])
        t = targets([(p.dates[0], "A", 0.5), (p.dates[0], "B", 0.5)])
        r = run(p, t, n_slots=2, cfg=CFG, slip_cfg=NO_SLIP)
        assert r.unfilled == 1
        assert {pos.symbol for pos in r.positions} == {"A"}

    def test_a_sleeve_too_small_for_one_share_is_unfilled(self):
        # An expensive stock: sleeve Rs 10,000 cannot buy one Rs 35,000 share.
        p = make_panel(A=[35000, 35000, 35000])
        t = targets([(p.dates[0], "A", 1.0)])
        r = run(p, t, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)
        assert r.n_positions == 0
        assert r.unfilled == 1


class TestMetrics:
    def test_no_r_multiple_only_period_return(self):
        p = make_panel(A=[100, 100, 120, 120])  # enter 100, exit 120 -> +~20% before costs
        t = targets([(p.dates[0], "A", 1.0)])
        r = run(p, t, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)
        pos = r.positions[0]
        assert 0.18 < pos.net_return < 0.20
        assert r.avg_period_return == pytest.approx(pos.net_return)
        assert r.win_rate == 1.0

    def test_roi_is_over_the_whole_commitment(self):
        p = make_panel(A=[100, 100, 120], C=[100, 100, 120])
        t = targets([(p.dates[0], "A", 0.5), (p.dates[0], "C", 0.5)])
        r = run(p, t, n_slots=2, cfg=CFG, slip_cfg=NO_SLIP)
        assert r.roi == pytest.approx(r.net_pnl / (2 * 10000.0))

    def test_empty_targets_give_clean_zero_metrics(self):
        p = make_panel(A=[100, 110])
        r = run(p, targets([]), n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)
        assert r.n_positions == 0
        assert r.avg_period_return is None
        assert r.roi == 0.0


class TestCostsAndSlippage:
    def test_costs_are_charged(self):
        p = make_panel(A=[100, 100, 120])
        t = targets([(p.dates[0], "A", 1.0)])
        r = run(p, t, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)
        assert r.total_costs > 0
        assert r.positions[0].net == pytest.approx(r.positions[0].gross - r.positions[0].cost)

    def test_slippage_makes_entry_higher_and_exit_lower(self):
        p = make_panel(A=[100, 100, 120])
        t = targets([(p.dates[0], "A", 1.0)])
        slipped = run(p, t, n_slots=1, cfg=EngineConfig(tick=0.05, spread=1.0)).positions[0]
        clean = run(p, t, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP).positions[0]
        assert slipped.entry > clean.entry
        assert slipped.exit < clean.exit


class TestRotation:
    def test_capital_rotates_across_rebalances(self):
        """The whole point of cross-sectional: hold A this period, rotate to B next."""
        p = make_panel(
            A=[100, 100, 100, 100, 100],
            B=[100, 100, 100, 100, 100],
        )
        t = targets([(p.dates[0], "A", 1.0), (p.dates[2], "B", 1.0)])
        r = run(p, t, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)
        assert [pos.symbol for pos in r.positions] == ["A", "B"]
        # A entered day1, exited at B's rebalance (day3 open); B entered day3, held to the end.
        a, b = r.positions
        assert a.symbol == "A" and b.symbol == "B"
        assert b.entry_ts >= a.exit_ts
