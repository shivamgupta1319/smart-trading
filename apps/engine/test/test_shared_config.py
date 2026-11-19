"""config/trading.json is the one source for settings the engine and API share.

Run from apps/engine:  python -m pytest test/test_shared_config.py -q
The TypeScript twin is apps/api/src/common/shared-config.spec.ts — it asserts the
SAME golden numbers, which is what proves the two runtimes agree.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shared_config  # noqa: E402
from backtest_config import (  # noqa: E402
    RISK, RISK_PER_TRADE_PCT, LEVERAGE_INTRADAY, LEVERAGE_DELIVERY, CostModel,
    MAX_COST_TO_RISK, cost_to_risk,
)

ENGINE_DIR = Path(__file__).resolve().parents[1]


def _file() -> dict:
    for candidate in shared_config._candidates():
        if candidate.is_file():
            return json.loads(candidate.read_text())
    raise AssertionError("config/trading.json not found")


def test_engine_constants_come_from_the_file():
    capital = _file()["capital"]
    assert LEVERAGE_INTRADAY == capital["LEVERAGE_INTRADAY"]
    assert LEVERAGE_DELIVERY == capital["LEVERAGE_DELIVERY"]
    assert RISK_PER_TRADE_PCT == capital["RISK_PER_TRADE_PCT"]
    # The engine derives its per-cell fund differently (initial capital / slots);
    # it must still equal the fund the API seeds every cell with.
    assert RISK.slot_capital == capital["BASE_CELL_CAPITAL"]


def test_golden_costs_match_the_typescript_twin():
    # Same inputs and expected values as shared-config.spec.ts.
    assert CostModel("15m").round_trip(100000.0, 101000.0) == pytest.approx(82.695246, abs=1e-6)
    assert CostModel("1D").round_trip(10000.0, 10300.0) == pytest.approx(37.2817338, abs=1e-6)


def test_cost_to_risk_matches_the_typescript_twin():
    assert MAX_COST_TO_RISK == _file()["capital"]["MAX_COST_TO_RISK"]
    assert RISK.slippage_bps == _file()["costs"]["BT_SLIPPAGE_BPS"]
    # A Rs 817.50 stock with a Rs 1.20 stop: the costs are 140% of the risk.
    assert cost_to_risk(61, 817.5, 1.2, "15m") == pytest.approx(1.403437675, abs=1e-8)
    assert cost_to_risk(30, 1600.0, 26.0, "15m") == pytest.approx(0.1267748923, abs=1e-8)
    assert cost_to_risk(38, 78.0, 5.14, "1D") == pytest.approx(0.1244126597, abs=1e-8)


def test_backtest_skips_a_trade_whose_costs_are_too_large_a_share_of_the_risk():
    import pandas as pd
    from strategies.base import BaseStrategy

    idx = pd.date_range("2026-11-18 09:15", periods=20, freq="15min")
    df = pd.DataFrame({"Open": 800.0, "High": 801.0, "Low": 799.5, "Close": 800.0, "Volume": 1000}, index=idx)

    class _Stop(BaseStrategy):
        name = "15m_ORB"       # a registered INTRADAY name
        timeframe = "15m"

        def __init__(self, stop):
            self._stop = stop

        def generate_signals(self, d):
            d = d.copy()
            d["signal"] = 0
            d.iloc[0, d.columns.get_loc("signal")] = 1
            d["stop_loss"] = self._stop
            d["target"] = 840.0
            return d

    tight = _Stop(799.0).simulate(df)      # Rs 1 stop on a Rs 800 stock: costs dwarf the risk
    assert tight["net_trades"] == [] and tight["skipped_costly"] == 1
    wide = _Stop(780.0).simulate(df)       # Rs 20 stop: costs are a small share
    assert len(wide["net_trades"]) == 1 and wide["skipped_costly"] == 0


def test_env_overrides_the_file(monkeypatch):
    monkeypatch.setenv("LEVERAGE_INTRADAY", "3")
    assert shared_config.shared("LEVERAGE_INTRADAY") == 3.0


def test_unknown_key_is_an_error_not_a_silent_default():
    with pytest.raises(KeyError):
        shared_config.shared("NOT_A_REAL_SETTING")


@pytest.mark.parametrize("bad", ["2", "0", "-0.02", "0.5"])
def test_percent_style_risk_value_is_refused(monkeypatch, bad):
    # RISK_PER_TRADE_PCT=2 (meant as 2%) once read as 200% and disabled the cap.
    monkeypatch.setenv("RISK_PER_TRADE_PCT", bad)
    with pytest.raises(ValueError):
        shared_config.risk_per_trade_fraction()


def test_shared_values_are_not_typed_into_the_code_any_more():
    cfg = (ENGINE_DIR / "backtest_config.py").read_text()
    for name in ("LEVERAGE_INTRADAY", "LEVERAGE_DELIVERY", "BT_GST_PCT", "BT_DELIVERY_STT_SELL_PCT"):
        assert f'_f("{name}"' not in cfg, f"{name} has an in-code default again"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
