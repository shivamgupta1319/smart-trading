"""The backtest and the live scanner must take the same trades from the same candles.

`replay.replay_scanner` runs the scanner's own entry and exit functions over a candle
series with the network, the clock and the API replaced. Its trades are compared with
`BaseStrategy.simulate` on the same series.

What must hold:
  * ENTRIES are identical: same candle, same side. A difference here means one side
    has a rule the other lacks (this test found three such rules when it was written).
  * EXITS land on the same candle in most trades. They cannot always: the scanner
    sees a price every poll and advances one exit phase per poll, the backtest sees a
    whole candle. The floors below are well under today's figures (91% same candle,
    95% within one) so only a real drift fails the test.

Run from apps/engine:  python -m pytest test/test_replay_parity.py -q
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from entry_limits import intraday_entry_time_ok  # noqa: E402
from replay import replay_scanner, synthetic_intraday_candles  # noqa: E402
from strategies import STRATEGY_REGISTRY  # noqa: E402

WARMUP = 30
CASES = [("VWAP_MACD_RSI", 1), ("VWAP_MACD_RSI", 2), ("RVOL_ORB", 1), ("RVOL_ORB", 3), ("SMC_FVG", 2)]
_totals = {"trades": 0, "same_candle": 0, "within_one": 0}


@pytest.mark.parametrize("name,seed", CASES)
def test_backtest_and_scanner_take_the_same_entries(name, seed, monkeypatch, capsys):
    strategy = STRATEGY_REGISTRY[name]
    df = synthetic_intraday_candles(seed)

    backtest = {(t["entry_ts"], t["side"]): t for t in strategy.simulate(df, trade_from=WARMUP)["trade_log"]}
    live_trades, _api = replay_scanner(df, name, strategy.timeframe, monkeypatch, trade_from=WARMUP)
    live = {(t["entry_ts"], t["side"]): t for t in live_trades}
    capsys.readouterr()  # drop the scanner's own log lines

    assert backtest, "the candles produced no backtest trade: the case tests nothing"
    only_backtest = sorted(str(k[0]) + " " + k[1] for k in backtest.keys() - live.keys())
    only_live = sorted(str(k[0]) + " " + k[1] for k in live.keys() - backtest.keys())
    assert not only_backtest and not only_live, (
        f"{name}: backtest-only entries {only_backtest}; scanner-only entries {only_live}"
    )

    for key, bt in backtest.items():
        apart = abs(df.index.get_loc(bt["exit_ts"]) - df.index.get_loc(live[key]["exit_ts"]))
        _totals["trades"] += 1
        _totals["same_candle"] += apart == 0
        _totals["within_one"] += apart <= 1


def test_exits_mostly_land_on_the_same_candle():
    # Runs after the cases above (same module, file order) and judges them together.
    n = _totals["trades"]
    assert n >= 30, f"only {n} trades compared: too few to judge exits"
    assert _totals["same_candle"] / n >= 0.80, _totals
    assert _totals["within_one"] / n >= 0.90, _totals


def test_intraday_entry_window_and_stale_signals():
    at = lambda s: pd.Timestamp(s).to_pydatetime()
    # Inside the window, same day.
    assert intraday_entry_time_ok(at("2026-03-04 09:15"), at("2026-03-04 09:30")) == (True, "")
    assert intraday_entry_time_ok(at("2026-03-04 14:30"), at("2026-03-04 14:45"))[0]
    # From 15:00 there is no time left before the square-off.
    assert not intraday_entry_time_ok(at("2026-03-04 14:45"), at("2026-03-04 15:00"))[0]
    assert not intraday_entry_time_ok(at("2026-03-04 15:00"), at("2026-03-04 15:15"))[0]
    # Before 09:30.
    assert not intraday_entry_time_ok(at("2026-03-04 09:15"), at("2026-03-04 09:16"))[0]
    # Yesterday's last candle is never traded this morning.
    ok, why = intraday_entry_time_ok(at("2026-03-03 15:00"), at("2026-03-04 09:31"))
    assert not ok and "earlier day" in why


def test_backtest_opens_no_intraday_trade_outside_the_window():
    strategy = STRATEGY_REGISTRY["SMC_FVG"]
    log = strategy.simulate(synthetic_intraday_candles(2), trade_from=WARMUP)["trade_log"]
    assert log
    for t in log:
        assert pd.Timestamp("09:30").time() <= t["entry_ts"].time() < pd.Timestamp("15:00").time(), t
        assert t["signal_ts"].date() == t["entry_ts"].date(), t
