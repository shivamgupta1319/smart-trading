"""Trials-ledger tests: N is what is durably on disk, and understating it means deleting lines.

The point of the ledger is auditability, so these pin that a recorded trial round-trips exactly,
that N counts every recorded evaluation (a re-run legitimately raises it), and that `sharpes()`
hands the DSR the full trial set.
"""

from __future__ import annotations

import pytest

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_trials import Trial, TrialsLedger


def a_trial(strategy="XSMomentum", variant="lookback=12,skip=1", sharpe=0.12) -> Trial:
    return Trial(
        strategy=strategy,
        variant=variant,
        instrument_set="NIFTY200",
        sharpe=sharpe,
        n_obs=750,
        timestamp="2026-07-16T12:00:00",
    )


class TestLedger:
    def test_record_then_read_round_trips(self, tmp_path):
        led = TrialsLedger(tmp_path / "trials.jsonl")
        t = a_trial()
        led.record(t)
        assert led.read() == [t]

    def test_missing_file_reads_empty_not_error(self, tmp_path):
        led = TrialsLedger(tmp_path / "does_not_exist.jsonl")
        assert led.read() == []
        assert led.n_trials() == 0

    def test_append_only_grows_n(self, tmp_path):
        led = TrialsLedger(tmp_path / "trials.jsonl")
        led.record(a_trial(variant="lookback=6"))
        led.record(a_trial(variant="lookback=12"))
        led.record(a_trial(variant="lookback=12"))  # a re-run is a real, N-raising trial
        assert led.n_trials() == 3

    def test_sharpes_feed_the_dsr(self, tmp_path):
        led = TrialsLedger(tmp_path / "trials.jsonl")
        led.record(a_trial(sharpe=0.05))
        led.record(a_trial(sharpe=0.20))
        assert led.sharpes() == [0.05, 0.20]

    def test_two_ledgers_on_the_same_path_see_each_others_writes(self, tmp_path):
        # The runner writes; a separate reader (the report) sees the durable N -- no shared state.
        path = tmp_path / "trials.jsonl"
        TrialsLedger(path).record(a_trial())
        assert TrialsLedger(path).n_trials() == 1

    def test_key_identifies_the_hypothesis(self):
        assert a_trial().key == ("XSMomentum", "lookback=12,skip=1", "NIFTY200")

    def test_blank_lines_are_ignored(self, tmp_path):
        path = tmp_path / "trials.jsonl"
        led = TrialsLedger(path)
        led.record(a_trial())
        with open(path, "a") as f:
            f.write("\n")  # a stray newline must not become a phantom trial
        assert led.n_trials() == 1


class TestTrial:
    def test_is_frozen(self):
        with pytest.raises(Exception):  # noqa: B017 -- FrozenInstanceError
            a_trial().sharpe = 0.99  # type: ignore[misc]


# ── the backtest tool's strategy table ────────────────────────────────────────

def test_pure_noise_strategies_do_not_stand_out_and_a_real_edge_does():
    import numpy as np
    from tools.backtest_all import strategy_table

    rng = np.random.default_rng(7)
    noise = {f"NOISE_{i}": list(rng.standard_normal(300)) for i in range(27)}
    table = strategy_table(noise, prior_sharpes=[])
    assert len(table) == 27 and not any(r["stands_out"] for r in table)

    # One strategy with a genuine +0.35R average among the same noise.
    mixed = dict(noise, REAL=list(rng.standard_normal(300) + 0.35))
    table = strategy_table(mixed, prior_sharpes=[])
    assert [r["strategy"] for r in table if r["stands_out"]] == ["REAL"]
    assert table[0]["strategy"] == "REAL"                    # best average first


def test_strategy_table_handles_cells_with_nothing_to_test():
    from tools.backtest_all import strategy_table

    table = strategy_table({"EMPTY": [], "ONE": [0.5], "FLAT": [0.2, 0.2, 0.2]}, prior_sharpes=[])
    assert {r["strategy"] for r in table} == {"EMPTY", "ONE", "FLAT"}
    assert all(r["p_value"] is None and r["stands_out"] is False for r in table)
