"""Ledger tests: the slot budget, and the cross-engine invariant that proves the two engines
are one underlying model.

The concurrency check has one subtle rule -- exits before entries at a shared timestamp -- so a
rotating slot reads as one position, not two. That rule is tested directly, and then exercised
through both engines' adapters. The invariant (ARCHITECTURE §3) closes P8: a degenerate 1-name
cross-sectional strategy must book the same trade as the StopEngine on the same price path.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading.core.slippage import SlippageConfig
from trading.engine import rebalance_engine, stop_engine
from trading.engine.ledger import (
    Ledger,
    SlotBreach,
    Trade,
    from_rebalance_result,
    from_stop_result,
)
from trading.engine.rebalance_engine import Panel
from trading.engine.stop_engine import LONG, EngineConfig

NO_SLIP = SlippageConfig(k=0.0, floor_bps=0.0)
CFG = EngineConfig(tick=1e-9, spread=0.0)


def trade(sym: str, entry_ts, exit_ts, slot_id: str = "cell") -> Trade:
    """A shared trade with only the fields the concurrency check reads set meaningfully."""
    return Trade(
        slot_id=slot_id,
        symbol=sym,
        side=LONG,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        entry=100.0,
        exit=110.0,
        qty=1,
        gross=10.0,
        cost=1.0,
    )


class TestConcurrency:
    def test_empty_is_zero(self):
        assert Ledger(1).check(()) == 0

    def test_sequential_trades_never_overlap(self):
        # Two trades on one slot, the second starting after the first exits.
        trades = (trade("A", 0, 2), trade("A", 3, 5))
        assert Ledger(1).check(trades) == 1

    def test_two_overlapping_positions_breach_a_single_slot(self):
        trades = (trade("A", 0, 5), trade("B", 2, 7))  # both open over [2, 5]
        with pytest.raises(SlotBreach, match="2 concurrent"):
            Ledger(1).check(trades)

    def test_rotation_at_a_shared_timestamp_is_not_an_overlap(self):
        # A exits at the exact bar B enters -- the slot rotates. Exits sort before entries, so
        # this reads as 1 concurrent, not 2. Without the tie-break every rotating book breaches.
        t1 = pd.Timestamp("2024-01-10")
        trades = (
            trade("A", pd.Timestamp("2024-01-01"), t1),
            trade("B", t1, pd.Timestamp("2024-01-20")),
        )
        assert Ledger(1).check(trades) == 1

    def test_top_k_holds_exactly_k_and_passes_at_k_slots(self):
        trades = (trade("A", 0, 10), trade("B", 0, 10), trade("C", 0, 10))
        assert Ledger(3).check(trades) == 3

    def test_one_extra_name_breaches_the_declared_budget(self):
        # A top-3 cell that quietly holds a 4th name during the same window fails loudly.
        trades = (
            trade("A", 0, 10),
            trade("B", 0, 10),
            trade("C", 0, 10),
            trade("D", 5, 15),  # the 4th, overlapping the other three
        )
        assert Ledger(4).check(trades) == 4  # honest when funded for 4
        with pytest.raises(SlotBreach, match="4 concurrent"):
            Ledger(3).check(trades)  # a lie when only 3 were funded


class TestStopEngineAdapter:
    def _two_sequential(self):
        idx = pd.RangeIndex(6)
        bars = [
            (100, 100, 100, 100),  # 0 signal A
            (100, 100, 100, 100),  # 1 enter A
            (100, 130, 100, 125),  # 2 A hits target 120
            (100, 100, 100, 100),  # 3 signal B
            (100, 100, 100, 100),  # 4 enter B
            (100, 130, 100, 125),  # 5 B hits target 120
        ]
        df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close"], index=idx, dtype=float)
        df["signal"] = 0.0
        df["stop_loss"] = float("nan")
        df["target"] = float("nan")
        df.loc[0, ["signal", "stop_loss", "target"]] = [1, 90, 120]
        df.loc[3, ["signal", "stop_loss", "target"]] = [1, 90, 120]
        return df

    def test_time_series_cell_is_one_slot_and_never_overlaps(self):
        result = stop_engine.run(self._two_sequential(), "delivery", CFG, slip_cfg=NO_SLIP)
        trades = from_stop_result(result, symbol="RELIANCE", slot_id="RELIANCE:ORB")
        assert len(trades) == 2
        assert all(t.symbol == "RELIANCE" for t in trades)
        assert Ledger(1).check(trades) == 1  # 1 slot, as a time-series cell must be


class TestRebalanceAdapter:
    def _panel(self, n=6):
        dates = pd.bdate_range("2024-01-01", periods=n)
        frames = {}
        for s in ("A", "B", "C"):
            opens = [100 + i for i in range(n)]
            frames[s] = pd.DataFrame(
                {"Open": opens, "High": opens, "Low": opens, "Close": opens, "Volume": 1000},
                index=dates,
            )
        return Panel(frames), dates

    def test_top_one_rotation_reads_as_one_slot(self):
        panel, dates = self._panel()
        # Rebalance twice: hold A, then rotate to B. The rotation shares a fill timestamp.
        tgt = pd.DataFrame(
            {"weight": [1.0, 1.0]},
            index=pd.MultiIndex.from_tuples(
                [(dates[0], "A"), (dates[2], "B")], names=["rebalance_ts", "symbol"]
            ),
        )
        result = rebalance_engine.run(panel, tgt, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)
        trades = from_rebalance_result(result, slot_id="NIFTY200:MOM")
        assert len(trades) == 2
        assert Ledger(1).check(trades) == 1  # rotation, not double-booking

    def test_top_two_needs_two_slots(self):
        panel, dates = self._panel()
        tgt = pd.DataFrame(
            {"weight": [0.5, 0.5]},
            index=pd.MultiIndex.from_tuples(
                [(dates[0], "A"), (dates[0], "B")], names=["rebalance_ts", "symbol"]
            ),
        )
        result = rebalance_engine.run(panel, tgt, n_slots=2, cfg=CFG, slip_cfg=NO_SLIP)
        trades = from_rebalance_result(result, slot_id="NIFTY200:MOM")
        assert Ledger(2).check(trades) == 2
        with pytest.raises(SlotBreach, match="2 concurrent"):
            Ledger(1).check(trades)  # declaring 1 slot for a top-2 is the breach we catch


class TestCrossEngineInvariant:
    """ARCHITECTURE §3: a cross-sectional strategy that always holds exactly one name must book
    the same trade the StopEngine books on the same price path. Same entry, same exit, same
    size, therefore same money -- that is what proves the two engines are one model, not two."""

    def test_degenerate_one_name_matches_stop_engine(self):
        # A rising path: entry at the next open (105), held to the last close (120). The stop
        # (104) and target (999) are never touched, so the StopEngine holds to series end --
        # exactly what the RebalanceEngine does with a single rebalance and one name.
        bars = [
            (100, 100, 100, 100),  # 0 signal / rebalance date
            (105, 111, 105, 110),  # 1 entry at open 105 (low 105 > stop 104, not hit)
            (110, 116, 110, 115),  # 2
            (115, 121, 115, 120),  # 3 last close 120
        ]
        opens = [b[0] for b in bars]
        closes = [b[3] for b in bars]

        # StopEngine on the single symbol.
        idx = pd.RangeIndex(len(bars))
        df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close"], index=idx, dtype=float)
        df["signal"] = 0.0
        df["stop_loss"] = float("nan")
        df["target"] = float("nan")
        df.loc[0, ["signal", "stop_loss", "target"]] = [1, 104, 999]
        stop_res = stop_engine.run(df, "delivery", CFG, slip_cfg=NO_SLIP)
        assert stop_res.n_trades == 1
        st = stop_res.trades[0]

        # RebalanceEngine on a 1-name panel, one rebalance, weight 1.0, 1 slot.
        dates = pd.bdate_range("2024-01-01", periods=len(bars))
        frame = pd.DataFrame(
            {
                "Open": opens,
                "High": [max(o, c) for o, c in zip(opens, closes, strict=True)],
                "Low": [min(o, c) for o, c in zip(opens, closes, strict=True)],
                "Close": closes,
                "Volume": 1000,
            },
            index=dates,
        )
        panel = Panel({"A": frame})
        tgt = pd.DataFrame(
            {"weight": [1.0]},
            index=pd.MultiIndex.from_tuples([(dates[0], "A")], names=["rebalance_ts", "symbol"]),
        )
        reb_res = rebalance_engine.run(panel, tgt, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)
        assert reb_res.n_positions == 1
        rp = reb_res.positions[0]

        # Same size, same fills, therefore same money -- the invariant.
        assert st.qty == rp.qty
        assert st.entry == pytest.approx(rp.entry)
        assert st.exit == pytest.approx(rp.exit)
        assert st.gross == pytest.approx(rp.gross)
        assert st.cost == pytest.approx(rp.cost)
        assert st.net == pytest.approx(rp.net)

    def test_invariant_holds_through_the_shared_trade_type(self):
        # And the shared Trade both map to agrees end to end -- one comparable record.
        bars = [
            (100, 100, 100, 100),
            (105, 111, 105, 110),
            (110, 116, 110, 115),
            (115, 121, 115, 120),
        ]
        idx = pd.RangeIndex(len(bars))
        df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close"], index=idx, dtype=float)
        df["signal"] = 0.0
        df["stop_loss"] = float("nan")
        df["target"] = float("nan")
        df.loc[0, ["signal", "stop_loss", "target"]] = [1, 104, 999]
        stop_res = stop_engine.run(df, "delivery", CFG, slip_cfg=NO_SLIP)

        dates = pd.bdate_range("2024-01-01", periods=len(bars))
        opens = [b[0] for b in bars]
        closes = [b[3] for b in bars]
        frame = pd.DataFrame(
            {
                "Open": opens,
                "High": [max(o, c) for o, c in zip(opens, closes, strict=True)],
                "Low": [min(o, c) for o, c in zip(opens, closes, strict=True)],
                "Close": closes,
                "Volume": 1000,
            },
            index=dates,
        )
        panel = Panel({"A": frame})
        tgt = pd.DataFrame(
            {"weight": [1.0]},
            index=pd.MultiIndex.from_tuples([(dates[0], "A")], names=["rebalance_ts", "symbol"]),
        )
        reb_res = rebalance_engine.run(panel, tgt, n_slots=1, cfg=CFG, slip_cfg=NO_SLIP)

        st = from_stop_result(stop_res, symbol="A", slot_id="A:degenerate")[0]
        rt = from_rebalance_result(reb_res, slot_id="A:degenerate")[0]
        assert st.qty == rt.qty
        assert st.net == pytest.approx(rt.net)
        assert st.side == rt.side == LONG
