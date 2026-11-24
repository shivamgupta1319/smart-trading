"""Switching by market condition: the rule table built from the backtest.

Run from apps/engine:  python -m pytest test/test_switch_rules.py -q
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import switch_rules as sw  # noqa: E402


def index_candles(days=700, seed=5):
    """An index that trends up, falls hard, then drifts: every regime appears."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=days)
    drift = np.concatenate([np.full(250, 0.0012), np.full(120, -0.0025), np.full(days - 370, 0.0001)])
    noise = np.concatenate([rng.normal(0, 0.006, 250), rng.normal(0, 0.016, 120), rng.normal(0, 0.005, days - 370)])
    close = 18000 * np.cumprod(1 + drift + noise)
    spread = np.abs(noise) + 0.004
    return pd.DataFrame({"Open": close * (1 - noise / 2), "High": close * (1 + spread), "Low": close * (1 - spread),
                         "Close": close, "Volume": 1.0}, index=idx)


def test_every_day_gets_one_of_the_four_labels_and_they_vary():
    labels = sw.regime_series(index_candles())
    assert set(labels.unique()) <= set(sw.REGIMES)
    assert len(set(labels.unique())) >= 3
    assert len(labels) > 500


def test_the_last_label_is_what_the_live_classifier_says():
    # The history must use the same rules as routers/regime._classify, or a rule learnt
    # on "RANGING" days would be applied to days the live label calls something else.
    from routers.regime import _classify

    df = index_candles()
    labels = sw.regime_series(df)
    for end in (400, 520, 640, len(df)):
        window = df.iloc[:end]
        assert labels.loc[window.index[-1]] == _classify(window.tail(253))["regime"], end


def test_a_trade_is_judged_by_the_regime_known_before_its_entry_day():
    labels = pd.Series(["RANGING", "TRENDING_UP", "VOLATILE"],
                       index=pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-04"]))
    assert sw.regime_on_entry(labels, pd.Timestamp("2026-03-04 09:45")) == "TRENDING_UP"   # not that day's own label
    assert sw.regime_on_entry(labels, pd.Timestamp("2026-03-05")) == "VOLATILE"
    assert sw.regime_on_entry(labels, pd.Timestamp("2026-03-09 10:00")) == "VOLATILE"      # after a weekend
    assert sw.regime_on_entry(labels, pd.Timestamp("2026-03-02 09:30")) is None            # nothing known yet


def test_a_strategy_is_switched_off_only_with_enough_losing_trades_in_that_regime():
    labels = pd.Series(["TRENDING_UP", "RANGING"], index=pd.to_datetime(["2026-03-02", "2026-03-03"]))
    up_day, range_day = pd.Timestamp("2026-03-03 10:00"), pd.Timestamp("2026-03-04 10:00")
    trades = {
        "Trend": [(up_day, 0.4)] * 60 + [(range_day, -0.2)] * 60,
        "Thin": [(range_day, -1.0)] * (sw.MIN_TRADES - 1),
    }
    rules = {(r["strategy"], r["regime"]): r for r in sw.build_rules(trades, labels)}
    assert rules[("Trend", "TRENDING_UP")]["approved"] is True
    assert rules[("Trend", "RANGING")] == {"strategy": "Trend", "regime": "RANGING", "trades": 60, "avgR": -0.2, "approved": False}
    # Too few trades: no evidence, so it is not switched off.
    assert rules[("Thin", "RANGING")]["approved"] is None
    # A regime with no trades at all has a row, with nothing in it.
    assert rules[("Trend", "VOLATILE")] == {"strategy": "Trend", "regime": "VOLATILE", "trades": 0, "avgR": None, "approved": None}
    assert len(rules) == 2 * len(sw.REGIMES)
