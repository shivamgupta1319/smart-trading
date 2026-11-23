"""The one rule that decides whether a cell's backtest is good enough to go live (paper).

A cell is one stock with one strategy. Three places used to decide "live" three different
ways: the roster, auto-select and the Set Live button (which checked nothing). They now
all ask this module. The thresholds are in config/trading.json under "selection".

A cell passes when ALL of these hold, on its backtest after costs:
  1. average per trade above +0.10R;
  2. positive in both halves of its history (not one lucky stretch);
  3. enough trades: 30 intraday, 10 swing, 4 for the long-hold strategies. Those signal
     about twice per stock in five years (Golden_Cross), so with a minimum of 10 the
     strategy with the best average could never put a single stock live. Four trades
     on one stock prove little; it is the strategy's result across all stocks, checked
     by the luck test, that carries the weight there;
  4. profit factor at least 1.5 (total won / total lost);
  5. net profit at least twice the worst drawdown;
  6. total return at least 10% of the fund;
  7. swing only: its strategy passes the first luck test (see luck_check.py).

Checks 4 to 6 were added on 2026-11-23: without them a cell with a 31% win rate, a small
profit and a drawdown twice that profit went live because its average R looked fine.

A passing backtest only earns a place on the roster. The cell's own paper trades decide
whether it stays (the cell lifecycle).
"""
from __future__ import annotations

from dataclasses import dataclass

from shared_config import shared


@dataclass(frozen=True)
class SelectionRules:
    min_avg_r: float
    min_trades_intraday: int
    min_trades_swing: int
    min_trades_long: int
    min_profit_factor: float
    min_profit_to_drawdown: float
    min_roi_pct: float


def selection_rules() -> SelectionRules:
    return SelectionRules(
        min_avg_r=shared("SELECT_MIN_AVG_R"),
        min_trades_intraday=int(shared("SELECT_MIN_TRADES_INTRADAY")),
        min_trades_swing=int(shared("SELECT_MIN_TRADES_SWING")),
        min_trades_long=int(shared("SELECT_MIN_TRADES_LONG")),
        min_profit_factor=shared("SELECT_MIN_PROFIT_FACTOR"),
        min_profit_to_drawdown=shared("SELECT_MIN_PROFIT_TO_DRAWDOWN"),
        min_roi_pct=shared("SELECT_MIN_ROI_PCT"),
    )


def misses(metrics: dict, bucket: str | None, strategy_passes_luck: bool | None = None,
           rules: SelectionRules | None = None) -> list[str]:
    """What a backtest fails, in plain words. An empty list means it passes.

    metrics: the dict `BaseStrategy.run_backtest` returns.
    bucket: the strategy's hold bucket; "INTRADAY" or one of the swing buckets.
    strategy_passes_luck: True/False from the latest luck check, or None when there is
        no luck check to ask (the check is then left out, not failed).
    """
    r = rules or selection_rules()
    intraday = bucket == "INTRADAY"
    out: list[str] = []

    trades = int(metrics.get("totalTrades") or 0)
    need = r.min_trades_intraday if intraday else r.min_trades_long if bucket == "LONG_POSITIONAL" else r.min_trades_swing
    if trades < need:
        out.append(f"only {trades} trades (needs {need})")

    avg_r = float(metrics.get("avgRMultiple") or 0.0)
    if avg_r <= r.min_avg_r:
        out.append(f"average per trade {avg_r:+.2f}R (needs above {r.min_avg_r:+.2f}R)")

    first, second = metrics.get("rFirstHalf"), metrics.get("rSecondHalf")
    if first is None or second is None:
        out.append("too few trades to compare the two halves")
    elif first <= 0 or second <= 0:
        which = "first" if first <= 0 else "second"
        out.append(f"the {which} half of its history lost ({first:+.2f}R, then {second:+.2f}R)")

    pf = float(metrics.get("profitFactor") or 0.0)
    if pf < r.min_profit_factor:
        out.append(f"profit factor {pf:.2f} (needs {r.min_profit_factor:g})")

    net = float(metrics.get("netProfit") or 0.0)
    drawdown = float(metrics.get("maxDrawdown") or 0.0)
    if net <= 0:
        out.append("it lost money")
    elif drawdown > 0 and net < r.min_profit_to_drawdown * drawdown:
        out.append(f"profit is {net / drawdown:.1f} times its worst drawdown (needs {r.min_profit_to_drawdown:g})")

    roi = float(metrics.get("roiPercentage") or 0.0)
    if roi < r.min_roi_pct:
        out.append(f"total return {roi:.1f}% (needs {r.min_roi_pct:g}%)")

    if not intraday and strategy_passes_luck is False:
        out.append("its strategy does not pass the luck test")
    return out


def verdict(metrics: dict, bucket: str | None, strategy_passes_luck: bool | None = None) -> dict:
    """{"passes": bool, "misses": [...]} for the API and the page."""
    found = misses(metrics, bucket, strategy_passes_luck)
    return {"passes": not found, "misses": found}


def strategies_passing_luck() -> set[str] | None:
    """Strategies with a positive average whose corrected chance of luck is at or below
    the luck check's limit, from the latest stored run. None when no run is stored."""
    import luck_check  # local: needs the database

    run = luck_check.latest()
    if not run:
        return None
    return {
        row["strategy"] for row in run["rows"]
        if (row.get("avg_r") or 0) > 0 and row.get("q_value") is not None and row["q_value"] <= run["fdrQ"]
    }
