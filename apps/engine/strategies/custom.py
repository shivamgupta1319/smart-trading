"""User-defined rule strategy executor.

Turns a JSON rule spec (built in the Strategy Builder UI) into entry signals +
SL/TP, runnable through the same realistic backtest engine as the built-ins.

Spec shape:
{
  "name": "My Strat", "timeframe": "1D", "side": "BUY",
  "entry": [ {"left": {"ind":"EMA","len":50}, "op": ">", "right": {"ind":"EMA","len":200}},
             {"left": {"ind":"RSI","len":14}, "op": "<", "right": {"value": 40}} ],
  "stop":   {"type": "atr", "mult": 2.0, "len": 14},   # or {"type":"pct","value":2}
  "target": {"type": "rr",  "value": 2.0}              # or {"type":"pct","value":4} / {"type":"atr","mult":3,"len":14}
}
"""
from __future__ import annotations
import pandas as pd
import pandas_ta as ta

from .base import BaseStrategy

OPERATORS = {">", "<", ">=", "<=", "crosses_above", "crosses_below"}
INDICATORS = {"EMA", "SMA", "RSI", "CLOSE", "ATR", "VALUE"}


def _series(operand: dict, df: pd.DataFrame) -> pd.Series:
    if "value" in operand:
        return pd.Series(float(operand["value"]), index=df.index)
    ind = (operand.get("ind") or "CLOSE").upper()
    length = int(operand.get("len", 14))
    close = df["Close"]
    if ind == "CLOSE":
        return close
    if ind == "EMA":
        return ta.ema(close, length=length)
    if ind == "SMA":
        return ta.sma(close, length=length)
    if ind == "RSI":
        return ta.rsi(close, length=length)
    if ind == "ATR":
        return ta.atr(df["High"], df["Low"], close, length=length)
    raise ValueError(f"Unknown indicator '{ind}'")


def _condition(cond: dict, df: pd.DataFrame) -> pd.Series:
    left = _series(cond["left"], df)
    right = _series(cond["right"], df)
    op = cond["op"]
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == "crosses_above":
        return (left.shift(1) <= right.shift(1)) & (left > right)
    if op == "crosses_below":
        return (left.shift(1) >= right.shift(1)) & (left < right)
    raise ValueError(f"Unknown operator '{op}'")


def validate_spec(spec: dict) -> None:
    if not isinstance(spec, dict):
        raise ValueError("Spec must be an object")
    if spec.get("side", "BUY") not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    entry = spec.get("entry")
    if not isinstance(entry, list) or not entry:
        raise ValueError("entry must be a non-empty list of conditions")
    for c in entry:
        if c.get("op") not in OPERATORS:
            raise ValueError(f"Bad operator: {c.get('op')}")


class CustomRuleStrategy(BaseStrategy):
    def __init__(self, spec: dict):
        validate_spec(spec)
        self.spec = spec
        self.name = spec.get("name", "Custom")
        self.timeframe = spec.get("timeframe", "1D")
        self.side = spec.get("side", "BUY")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["Close"]
        atr = ta.atr(df["High"], df["Low"], close, length=int(self.spec.get("stop", {}).get("len", 14)))

        # AND all entry conditions, then fire only on the transition to true.
        cond = None
        for c in self.spec["entry"]:
            s = _condition(c, df).fillna(False)
            cond = s if cond is None else (cond & s)
        fired = cond & ~cond.shift(1, fill_value=False)

        is_buy = self.side == "BUY"
        df["signal"] = fired.astype(int) * (1 if is_buy else -1)

        # Stop loss
        stop = self.spec.get("stop", {"type": "pct", "value": 2})
        if stop.get("type") == "atr":
            dist = atr * float(stop.get("mult", 2.0))
            sl = close - dist if is_buy else close + dist
        else:
            pct = float(stop.get("value", 2)) / 100.0
            sl = close * (1 - pct) if is_buy else close * (1 + pct)

        # Target
        tgt = self.spec.get("target", {"type": "rr", "value": 2.0})
        risk = (close - sl).abs()
        if tgt.get("type") == "rr":
            move = risk * float(tgt.get("value", 2.0))
        elif tgt.get("type") == "atr":
            move = atr * float(tgt.get("mult", 3.0))
        else:
            move = close * (float(tgt.get("value", 4)) / 100.0)
        tp = close + move if is_buy else close - move

        df["stop_loss"] = sl
        df["target"] = tp
        return df
