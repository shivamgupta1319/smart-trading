"""Replay harness: run the REAL live scanner over stored candles, with no network.

The backtest (`strategies/base.simulate`) and the live scanner
(`scanner/live_scanner`) are two programs that should take the same trades from the
same candles. This module drives the scanner's own `check_and_fire_signal` and
`auto_close_signals` through a candle series, replacing only what touches the
outside world: the candle download, the live quote, the clock, the Trade-table
read and the HTTP calls to the API.

Each candle is visited four times, as a live poll would see it: at its open, at
its adverse extreme, at its favourable extreme and at its close. The adverse
extreme comes first, the same pessimistic order the backtest uses.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytz

import scanner.live_scanner as ls
from backtest_config import LEVERAGE_INTRADAY, MAX_COST_TO_RISK, RISK, RISK_PER_TRADE_PCT, cost_to_risk
from strategies.base import position_qty

IST = pytz.timezone("Asia/Kolkata")
LIVE_WINDOW_BARS = 260
SYMBOL = "REPLAY"
STOCK_ID = 1


class _Clock(datetime):
    """`datetime` whose now() is set by the replay."""
    current: datetime = None  # IST-naive

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.current
        return tz.localize(cls.current)


class _Response(SimpleNamespace):
    def json(self):
        return self.body


class FakeApi:
    """The few API behaviours the scanner depends on, held in memory."""

    def __init__(self, timeframe: str):
        self.timeframe = timeframe
        self.signals: list[dict] = []
        self.closed: list[dict] = []
        self.rejected: list[str] = []

    # -- what the scanner calls ------------------------------------------------
    def post(self, url, json=None, **_):
        entry, stop = json["entryPrice"], json["stopLoss"]
        key = (json["stockId"], json["strategyName"])
        if any(s["status"] == "ACTIVE" and s["key"] == key for s in self.signals):
            self.rejected.append("already open")
            return _Response(status_code=409, text="already open", body={})
        risk = abs(entry - stop)
        qty = position_qty(
            min(RISK.slot_capital * LEVERAGE_INTRADAY, RISK.max_position_value),
            RISK.slot_capital * RISK_PER_TRADE_PCT, entry, risk,
        )
        if qty < 1:
            self.rejected.append("unsizable")
            return _Response(status_code=400, text="one share does not fit", body={})
        if MAX_COST_TO_RISK > 0 and cost_to_risk(qty, entry, risk, self.timeframe) > MAX_COST_TO_RISK:
            self.rejected.append("costly")
            return _Response(status_code=400, text="costs too large for the risk", body={})
        sid = len(self.signals) + 1
        self.signals.append({
            "id": sid, "key": key, "status": "ACTIVE", "signalType": json["signalType"],
            "target": json["target"], "holdDuration": json["holdDuration"],
            "stock": {"symbol": SYMBOL},
            "trade": {
                "status": "OPEN", "quantity": qty, "remainingQty": qty, "entryPrice": entry,
                "stopLoss": stop, "signalType": json["signalType"], "trailingState": "INITIAL",
                "peakPrice": None, "entryTime": _Clock.current,
            },
        })
        return _Response(status_code=201, text="", body={"id": sid})

    def get(self, url, **_):
        return _Response(status_code=200, body=[s for s in self.signals if s["status"] == "ACTIVE"])

    def patch(self, url, json=None, **_):
        parts = url.rstrip("/").split("/")
        action, sid = parts[-1], int(parts[-2])
        sig = self.signals[sid - 1]
        trade = sig["trade"]
        if action == "update-sl":
            trade["stopLoss"] = json["newStopLoss"]
            trade["trailingState"] = json["trailingState"]
            trade["peakPrice"] = json.get("peakPrice")
        elif action == "partial-close":
            lot = min(int(trade["quantity"] * json["percent"]), trade["remainingQty"])
            if lot >= trade["remainingQty"]:
                self._close(sig, json["exitPrice"])
            else:
                trade["remainingQty"] -= lot
        elif action == "close":
            self._close(sig, json["exitPrice"])
        return _Response(status_code=200, body={})

    def _close(self, sig, price):
        sig["status"] = "CLOSED"
        sig["trade"]["status"] = "CLOSED"
        self.closed.append({
            "entry_time": sig["trade"]["entryTime"], "exit_time": _Clock.current,
            "side": sig["signalType"], "entry": sig["trade"]["entryPrice"], "exit": price,
            "qty": sig["trade"]["quantity"],
        })

    # -- what the Trade-table read returns -------------------------------------
    def activity_today(self, now_naive: datetime):
        today = now_naive.date()
        entered = sum(1 for s in self.signals if s["trade"]["entryTime"].date() == today)
        exits = [c["exit_time"] for c in self.closed]
        return entered, (max(exits) if exits else None)


def replay_scanner(df: pd.DataFrame, strategy_name: str, timeframe: str, monkeypatch, trade_from: int = 0):
    """Run the live scanner over `df` (IST-naive index, completed candles) and return
    the trades it took: [{signal bar's entry candle, exit candle, side, entry, exit}]."""
    api = FakeApi(timeframe)
    bar = df.index[1] - df.index[0]
    state = {"completed": 0, "price": None}

    monkeypatch.setattr(ls, "datetime", _Clock)
    monkeypatch.setattr(ls, "httpx", api)
    monkeypatch.setattr(ls.time, "sleep", lambda *_: None)
    # Live downloads about ten days of intraday candles; give the scanner the same window.
    monkeypatch.setattr(ls, "fetch_live_candles", lambda *_: df.iloc[max(0, state["completed"] - LIVE_WINDOW_BARS):state["completed"]])
    monkeypatch.setattr(ls, "get_recent_candles", lambda *_a, **_k: df.iloc[:state["completed"]].tail(10))
    monkeypatch.setattr(ls, "get_live_price", lambda *_: state["price"])
    monkeypatch.setattr(ls, "cell_activity_today", lambda _s, _n, now: api.activity_today(now.replace(tzinfo=None)))
    monkeypatch.setattr(ls, "last_evaluated", {})
    monkeypatch.setattr(ls, "cannot_evaluate", {})
    last_fired: dict = {}
    config = (1, STOCK_ID, strategy_name, timeframe, SYMBOL)

    for k in range(max(trade_from, 30), len(df)):
        row = df.iloc[k]
        state["completed"] = k                     # candles 0..k-1 are complete while k forms
        up_first = False                           # adverse extreme first for whatever is open
        open_side = next((s["signalType"] for s in api.signals if s["status"] == "ACTIVE"), None)
        if open_side == "SELL":
            up_first = True
        path = [row["Open"]] + ([row["High"], row["Low"]] if up_first else [row["Low"], row["High"]]) + [row["Close"]]
        for step, price in enumerate(path):
            _Clock.current = (df.index[k] + bar * (0.07 + 0.3 * step)).to_pydatetime()
            state["price"] = float(price)
            now_t = _Clock.current.time()
            ls.auto_close_signals({})
            # New setups: same window as main(). A candle completes once, so the later
            # polls inside the same candle have nothing new to evaluate.
            if step == 0 and dtime(9, 30) <= now_t < dtime(15, 15):
                ls.check_and_fire_signal(config, {}, last_fired)

    floor = lambda t: df.index[df.index.searchsorted(pd.Timestamp(t), side="right") - 1]
    return [
        {"entry_ts": floor(c["entry_time"]), "exit_ts": floor(c["exit_time"]), "side": c["side"],
         "entry": c["entry"], "exit": c["exit"], "qty": c["qty"]}
        for c in api.closed
    ], api


def synthetic_intraday_candles(seed: int, days: int = 24, minutes: int = 15, start: float = 400.0) -> pd.DataFrame:
    """Deterministic 09:15-15:15 candles: a small overnight gap, a drift for the day
    and noise. Enough movement for the intraday strategies to trade."""
    rng = np.random.default_rng(seed)
    index = []
    for day in pd.bdate_range("2026-03-02", periods=days):
        t = day + pd.Timedelta(hours=9, minutes=15)
        while t.time() <= dtime(15, 15):
            index.append(t)
            t += pd.Timedelta(minutes=minutes)
    price, drift, rows = start, 0.0, []
    for t in index:
        if t.time() == dtime(9, 15):
            price *= 1 + rng.normal(0, 0.006)
            drift = rng.normal(0, 0.0006)
        o = price
        c = o * (1 + drift + rng.normal(0, 0.0022))
        h = max(o, c) * (1 + abs(rng.normal(0, 0.0009)))
        low = min(o, c) * (1 - abs(rng.normal(0, 0.0009)))
        rows.append((round(o, 2), round(h, 2), round(low, 2), round(c, 2), int(abs(rng.normal(1, 0.5)) * 200000 + 20000)))
        price = c
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex(index))
