"""XS Momentum 12-1 tests: the ranking verified by hand on a few synthetic stocks.

The signal logic is what these pin -- correct 12-1 ranking, the skipped month actually skipped,
missing names dropped -- because a momentum *number* on the real universe means nothing until R3
(the point-in-time universe) is settled. The load-bearing test is `test_skips_the_last_month`:
a stock that spiked only in the skipped month must NOT be selected, which is the whole difference
between momentum and short-term reversal.

Parameters are shrunk (2-month lookback, 1-month skip) so the windows are small enough to reason
about bar-by-bar; the 12-1 default is exercised through the registered spec and the gate.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from trading.core.slippage import SlippageConfig
from trading.data.universe import MembershipChange, Universe
from trading.engine import rebalance_engine
from trading.engine.ledger import Ledger, from_rebalance_result
from trading.engine.rebalance_engine import Panel
from trading.engine.stop_engine import EngineConfig
from trading.research.friction import Verdict, evaluate
from trading.strategies.xs_momentum import XSMomentum, XSMomentum121

NO_SLIP = SlippageConfig(k=0.0, floor_bps=0.0)
CFG = EngineConfig(tick=1e-9, spread=0.0)

# 2-month lookback, 1-month skip => lookback_days=42, skip_days=21.
SMALL = dict(lookback_months=2, skip_months=1)


def ramp_panel(rates: dict[str, float], n: int = 90) -> Panel:
    """One geometric ramp per symbol: close[t] = 100 * (1+rate)^t. Then the 12-1 ratio
    close[i-21]/close[i-42] = (1+rate)^21 is monotone in `rate`, so the momentum ranking is
    exactly the ranking of `rates` -- known by construction."""
    dates = pd.bdate_range("2022-01-03", periods=n)
    frames = {}
    for sym, rate in rates.items():
        close = pd.Series([100.0 * (1.0 + rate) ** t for t in range(n)], index=dates)
        frames[sym] = pd.DataFrame(
            {"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1000}
        )
    return Panel(frames)


class TestRanking:
    def test_top_k_are_the_fastest_growers(self):
        # Six stocks, distinct growth rates. Top-3 must be the three fastest (F, E, D).
        panel = ramp_panel({"A": 0.000, "B": 0.001, "C": 0.002, "D": 0.003, "E": 0.004, "F": 0.005})
        tgt = XSMomentum(**SMALL, top_k=3).generate_targets(panel)
        first = tgt.loc[tgt.index.get_level_values(0)[0]]
        assert set(first.index) == {"F", "E", "D"}
        assert all(w == pytest.approx(1 / 3) for w in first["weight"])

    def test_weights_sum_to_one_per_rebalance(self):
        panel = ramp_panel({s: i * 0.001 for i, s in enumerate("ABCDEF")})
        tgt = XSMomentum(**SMALL, top_k=4).generate_targets(panel)
        for _t, group in tgt.groupby(level=0):
            assert group["weight"].sum() == pytest.approx(1.0)
            assert len(group) == 4

    def test_skips_the_last_month(self):
        """The 12-1 invariant, and it must be load-bearing. The single rebalance fires at bar 42,
        so its momentum window is bars [0, 21] and the SKIPPED month is bars [21, 42]. TREND rises
        over [0, 21] then goes flat; SPIKER is flat over [0, 21] then leaps through [21, 42]. With
        the skip, TREND's window return beats SPIKER's zero, so TREND is held. Drop the skip and
        SPIKER's leap (counted at bar 42) wins instead -- which is exactly the reversal trap the
        12-1 window exists to avoid. (Mutation-checked: removing the skip flips the selection.)"""
        n = 50  # short enough that exactly one quarterly rebalance fires, at bar 42
        dates = pd.bdate_range("2022-01-03", periods=n)

        def series(vals):
            c = pd.Series(vals, index=dates)
            return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1000})

        # TREND: +1/bar over the momentum window [0,21], then flat (nothing in the skipped month).
        trend = [100.0 + min(t, 21) for t in range(n)]
        # SPIKER: flat over [0,21] (zero window return), then leaps through the skipped month.
        spiker = [100.0 if t <= 21 else 100.0 + 5.0 * (t - 21) for t in range(n)]
        panel = Panel(
            {
                "TREND": series(trend),
                "SPIKER": series(spiker),
                "DOWN1": series([100.0 - 0.1 * t for t in range(n)]),
                "DOWN2": series([100.0 - 0.2 * t for t in range(n)]),
            }
        )
        tgt = XSMomentum(**SMALL, top_k=1).generate_targets(panel)
        assert len(tgt.index.get_level_values(0).unique()) == 1  # one rebalance, at bar 42
        held = set(tgt.index.get_level_values(1))
        assert held == {"TREND"}  # the window-grower, NOT the recent spiker

    def test_names_missing_an_endpoint_are_dropped(self):
        # A name that only starts trading mid-window has NaN at the lookback endpoint -> unrankable.
        panel = ramp_panel({"A": 0.003, "B": 0.002, "C": 0.001})
        newcomer = panel.close["A"].copy()
        newcomer.iloc[:50] = float("nan")  # A did not exist for the first 50 bars
        frames = {
            "A": pd.DataFrame(
                {"Open": newcomer, "High": newcomer, "Low": newcomer, "Close": newcomer}
            ),
            "B": panel.open[["B"]]
            .rename(columns={"B": "Open"})
            .assign(High=panel.open["B"], Low=panel.open["B"], Close=panel.close["B"]),
            "C": panel.open[["C"]]
            .rename(columns={"C": "Open"})
            .assign(High=panel.open["C"], Low=panel.open["C"], Close=panel.close["C"]),
        }
        tgt = XSMomentum(**SMALL, top_k=3).generate_targets(Panel(frames))
        first = tgt.loc[tgt.index.get_level_values(0)[0]]
        assert "A" not in first.index  # dropped at the first rebalance, not ranked as zero


class TestPointInTimeUniverse:
    """The R3 wiring: with a universe, each rebalance ranks only that date's index members."""

    def test_a_non_member_is_excluded_even_with_the_best_momentum(self):
        # A has the strongest ramp, so it wins outright WITHOUT a universe. But A is not a member,
        # so WITH the universe the best MEMBER (B) is held instead -- survivorship guard working.
        panel = ramp_panel({"A": 0.005, "B": 0.003, "C": 0.001}, n=90)
        assert set(
            XSMomentum(**SMALL, top_k=1).generate_targets(panel).index.get_level_values(1)
        ) == {"A"}

        u = Universe("2023-01-01", {"B", "C"}, [])  # A was never a member
        held = XSMomentum(**SMALL, top_k=1, universe=u).generate_targets(panel)
        assert set(held.index.get_level_values(1)) == {"B"}

    def test_a_name_that_left_later_is_still_eligible_in_its_period(self):
        # D has the best momentum and is NOT in today's anchor {B,C}. But it was a member until a
        # Dec-2022 removal, so at a spring-2022 rebalance the reconstruction restores it and it
        # wins -- proving the ranking uses point-in-time membership, not today's list.
        panel = ramp_panel({"B": 0.003, "C": 0.001, "D": 0.005}, n=90)  # panel ends ~May 2022
        u = Universe(
            "2023-01-01",
            {"B", "C"},  # D is gone from today's list
            [
                MembershipChange(
                    effective_date=date(2022, 12, 1),
                    added=frozenset(),
                    removed=frozenset({"D"}),
                    source="test",
                )
            ],
        )
        held = XSMomentum(**SMALL, top_k=1, universe=u).generate_targets(panel)
        assert set(held.index.get_level_values(1)) == {"D"}  # eligible while it belonged


class TestRebalanceSchedule:
    def test_rebalances_are_quarterly_and_gated_by_warmup(self):
        # ~1.5 years of daily bars -> the first rebalance only after the 42-bar lookback.
        panel = ramp_panel({"A": 0.002, "B": 0.001}, n=380)
        tgt = XSMomentum(**SMALL, top_k=1).generate_targets(panel)
        rebalance_dates = sorted(tgt.index.get_level_values(0).unique())
        assert len(rebalance_dates) >= 4  # multiple quarters covered
        # Every rebalance sits at or beyond the lookback warmup.
        first_pos = panel.dates.get_loc(rebalance_dates[0])
        assert first_pos >= 42
        # Consecutive rebalances are in different quarters.
        quarters = [(d.year, d.quarter) for d in rebalance_dates]
        assert len(quarters) == len(set(quarters))


class TestEndToEnd:
    def test_targets_run_through_the_engine_within_the_slot_budget(self):
        panel = ramp_panel({s: i * 0.001 for i, s in enumerate("ABCDEF")}, n=200)
        top_k = 3
        tgt = XSMomentum(**SMALL, top_k=top_k).generate_targets(panel)
        result = rebalance_engine.run(panel, tgt, n_slots=top_k, cfg=CFG, slip_cfg=NO_SLIP)
        assert result.n_positions > 0
        trades = from_rebalance_result(result, slot_id="NIFTY200:MOM")
        # A top-K book must never hold more than K names at once.
        assert Ledger(top_k).check(trades) <= top_k


class TestRegistrationAndGate:
    def test_registered_spec_is_the_top6_delivery_config(self):
        spec = XSMomentum121.spec
        assert spec.name == "xs_momentum_12_1"
        assert spec.slots == 6  # top-6 => a Rs 60,000 commitment (D8)
        assert spec.bucket.cost_bucket == "delivery"
        assert spec.proposal.stop_pct is None  # cross-sectional: no stop (D9)

    def test_the_gate_passes(self):
        # Momentum is the one candidate whose quarterly friction its own prior can clear.
        assert evaluate(XSMomentum121.spec.proposal).verdict == Verdict.PASSED

    def test_default_is_twelve_one(self):
        s = XSMomentum121()
        assert s.lookback_months == 12 and s.skip_months == 1 and s.top_k == 6
        assert s.lookback_days == 252 and s.skip_days == 21


class TestGuards:
    def test_lookback_must_exceed_skip(self):
        with pytest.raises(ValueError, match="must exceed skip"):
            XSMomentum(lookback_months=1, skip_months=1)

    def test_top_k_must_be_positive(self):
        with pytest.raises(ValueError, match="top_k must be"):
            XSMomentum(top_k=0)
