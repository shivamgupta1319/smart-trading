"""Where each strategy works: broadly, on particular stocks, or nowhere.

Run from apps/engine:  python -m pytest test/test_strategy_map.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strategy_map  # noqa: E402

GOOD = {"totalTrades": 14, "avgRMultiple": 1.2, "rFirstHalf": 0.9, "rSecondHalf": 1.4, "profitFactor": 3.0,
        "netProfit": 3700.0, "maxDrawdown": 600.0, "roiPercentage": 37.0}
WEAK = {"totalTrades": 12, "avgRMultiple": 0.05, "rFirstHalf": 0.2, "rSecondHalf": -0.1, "profitFactor": 1.05,
        "netProfit": 60.0, "maxDrawdown": 700.0, "roiPercentage": 0.6}
LOSER = {**WEAK, "avgRMultiple": -0.3, "netProfit": -900.0, "roiPercentage": -9.0}


def cell(symbol, strategy, base):
    return {"symbol": symbol, "strategy": strategy, **base}


def by_name(rows, lucky):
    return {s["strategy"]: s for s in strategy_map.build(rows, lucky)}


def test_a_strategy_good_on_most_stocks_works_broadly():
    rows = [cell(f"S{i}", "Golden_Cross", GOOD) for i in range(7)] + [cell(f"L{i}", "Golden_Cross", LOSER) for i in range(3)]
    s = by_name(rows, {"Golden_Cross"})["Golden_Cross"]
    assert (s["tested"], s["profitable"], len(s["meets"])) == (10, 7, 7)
    assert s["verdict"] == "Works broadly"


def test_good_on_a_few_stocks_only_is_not_broad():
    rows = [cell("A", "VCP", GOOD), cell("B", "VCP", GOOD)] + [cell(f"L{i}", "VCP", LOSER) for i in range(8)]
    s = by_name(rows, {"VCP"})["VCP"]
    assert s["verdict"] == "Works on some stocks"
    assert [m["symbol"] for m in s["meets"]] == ["A", "B"]


def test_a_swing_strategy_that_fails_the_luck_check_has_no_stock_that_meets_the_rule():
    rows = [cell(f"S{i}", "VCP", GOOD) for i in range(9)]
    assert by_name(rows, lucky=set())["VCP"]["verdict"] == "No stock meets the rule"
    # With no luck check stored that test is left out, not failed.
    assert by_name(rows, lucky=None)["VCP"]["verdict"] == "Works broadly"


def test_weak_everywhere_meets_nowhere_and_untraded_cells_are_not_counted():
    rows = [cell("A", "DMA20_Pullback", WEAK), cell("B", "DMA20_Pullback", {**WEAK, "totalTrades": 0})]
    s = by_name(rows, None)["DMA20_Pullback"]
    assert (s["tested"], s["profitable"], s["meets"], s["verdict"]) == (1, 1, [], "No stock meets the rule")


def test_every_registered_strategy_has_a_row_and_broad_ones_come_first():
    rows = [cell(f"S{i}", "Golden_Cross", GOOD) for i in range(5)]
    out = strategy_map.build(rows, None)
    from strategies import STRATEGY_REGISTRY
    assert {s["strategy"] for s in out} == set(STRATEGY_REGISTRY)
    assert out[0]["strategy"] == "Golden_Cross"
