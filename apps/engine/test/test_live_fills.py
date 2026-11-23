"""Live paper-fill rules (scanner entries and stop/target exits).

Run from apps/engine:  python -m pytest test/test_live_fills.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live_fills import entry_geometry_ok, stop_exit_price, target_exit_price  # noqa: E402


def test_long_entry_needs_stop_below_and_target_above():
    assert entry_geometry_ok(True, 100, 98, 104) == (True, "")
    # Price ran through the target before the poll saw the signal: nothing left to take.
    assert entry_geometry_ok(True, 105, 98, 104)[0] is False
    # Price already at/below the stop.
    assert entry_geometry_ok(True, 98, 98, 104)[0] is False


def test_short_entry_is_the_mirror():
    assert entry_geometry_ok(False, 100, 102, 96) == (True, "")
    assert entry_geometry_ok(False, 95, 102, 96)[0] is False
    assert entry_geometry_ok(False, 102.5, 102, 96)[0] is False


@pytest.mark.parametrize("entry,stop,target", [
    (0, 98, 104), (-5, 98, 104), (float("nan"), 98, 104), (100, float("nan"), 104), (100, 98, None),
])
def test_missing_or_bad_prices_are_rejected(entry, stop, target):
    ok, why = entry_geometry_ok(True, entry, stop, target)
    assert ok is False and why == "missing price"


def test_stop_out_books_the_worse_of_stop_and_live():
    # Long: the poll sees 97.4 with the stop at 98 → the fill is 97.4, not 98.
    assert stop_exit_price(True, 98, 97.4) == 97.4
    assert stop_exit_price(True, 98, 98) == 98
    # Short: the poll sees 102.6 with the stop at 102 → 102.6.
    assert stop_exit_price(False, 102, 102.6) == 102.6
    assert stop_exit_price(False, 102, 102) == 102


def test_target_books_the_level_not_the_better_live_price():
    assert target_exit_price(104) == 104


def test_scanner_uses_these_rules():
    """Guard against the scanner drifting back to booking the candle close / stop price."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "scanner", "live_scanner.py")).read()
    assert "entry_geometry_ok(" in src and "stop_exit_price(" in src and "target_exit_price(" in src
    assert '"entryPrice": round(float(latest[\'Close\']), 2)' not in src


# ── Scanner: candles completed between polls ─────────────────────────────────

def _bars(signals):
    import pandas as pd
    idx = pd.date_range("2026-11-19 09:15", periods=len(signals), freq="5min")
    return pd.DataFrame({"Close": 100.0, "signal": signals}, index=idx)


def test_first_evaluation_only_looks_at_the_newest_candle():
    from scanner.live_scanner import pick_signal_row
    df = _bars([1, 0, 0])                       # an old signal must not replay on start-up
    assert pick_signal_row(df, None) is None
    assert pick_signal_row(_bars([0, 0, -1]), None)["signal"] == -1


def test_a_signal_on_a_candle_completed_mid_cycle_is_not_lost():
    from scanner.live_scanner import pick_signal_row
    df = _bars([0, 0, 1, 0])                    # signal on the 09:25 candle; newest is 09:30
    seen = df.index[1]                          # last cycle evaluated up to 09:20
    row = pick_signal_row(df, seen)
    assert row is not None and row.name == df.index[2]
    # Already evaluated through the newest candle: nothing new to act on.
    assert pick_signal_row(df, df.index[-1]) is None


def test_catch_up_is_bounded_and_takes_the_most_recent_signal():
    from scanner.live_scanner import pick_signal_row
    df = _bars([1, 0, 0, 0, 0, 0])              # signal 5 candles back
    assert pick_signal_row(df, df.index[0] - (df.index[1] - df.index[0])) is None   # outside the 3-candle window
    df2 = _bars([0, 1, 0, -1, 0])
    assert pick_signal_row(df2, df2.index[0])["signal"] == -1                        # newest of the two


# ── Engine: live-prices endpoint ─────────────────────────────────────────────

def test_live_prices_fetches_missing_quotes_together_and_survives_a_bad_symbol(monkeypatch):
    import threading
    import time as _time
    import brokers
    import routers.history as history

    history.cache_set("live:CACHED", {"price": 1.0})
    seen, lock = [], threading.Lock()

    def fake_quote(sym):
        with lock:
            seen.append(sym)
        _time.sleep(0.2)
        if sym == "BROKEN":
            raise RuntimeError("provider down")
        if sym == "NOQUOTE":
            return None
        return {"price": 100.0, "symbol": sym}

    monkeypatch.setattr(brokers, "get_live_price", fake_quote)
    symbols = ["CACHED", "AAA", "BBB", "CCC", "BROKEN", "NOQUOTE", "AAA"]
    started = _time.monotonic()
    out = history.get_live_prices(history.LivePriceRequest(symbols=symbols))
    took = _time.monotonic() - started

    assert out["CACHED"] == {"price": 1.0} and "CACHED" not in seen       # cache respected
    assert out["AAA"]["price"] == 100.0 and out["BBB"]["price"] == 100.0
    assert out["BROKEN"] is None and out["NOQUOTE"] is None                # no crash, no fake price
    assert sorted(seen) == ["AAA", "BBB", "BROKEN", "CCC", "NOQUOTE"]      # each asked once
    assert took < 0.8                                                      # 5 x 0.2s in a row would be 1.0s


def test_live_prices_keeps_a_recent_quote_when_the_refresh_fails(monkeypatch):
    import brokers
    import routers.history as history

    history.cache_set("live:STALE", {"price": 55.0})
    monkeypatch.setattr(history, "LIVE_PRICE_TTL", 0)       # force a refresh
    monkeypatch.setattr(brokers, "get_live_price", lambda sym: None)
    out = history.get_live_prices(history.LivePriceRequest(symbols=["STALE"]))
    assert out["STALE"] == {"price": 55.0}


# ── Engine: NIFTY comparison ─────────────────────────────────────────────────

def test_benchmark_return_is_first_close_on_or_after_the_date_to_the_latest():
    import pandas as pd
    import pytest as _pytest
    from routers.history import benchmark_return

    closes = pd.Series([25000.0, 25100.0, 24900.0, 25400.0],
                       index=pd.to_datetime(["2026-11-17", "2026-11-18", "2026-11-20", "2026-11-23"]))
    r = benchmark_return(closes, "2026-11-19")            # 19th was not a trading day in this series
    assert r["since"] == "2026-11-20" and r["to"] == "2026-11-23"
    assert r["return_pct"] == _pytest.approx((25400 / 24900 - 1) * 100, abs=0.01)
    assert benchmark_return(closes, "2026-11-17")["return_pct"] == _pytest.approx(1.6, abs=0.01)
    assert benchmark_return(closes, "2026-12-01") is None  # nothing on or after that date


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# --- daily candles are fetched once and reused between passes -----------------------

def test_daily_candles_are_reused_between_passes_and_intraday_never(monkeypatch):
    import pandas as pd
    import scanner.live_scanner as ls

    calls = []
    frame = pd.DataFrame({"Close": [1.0]})

    def fake_fetch(symbol, timeframe):
        calls.append((symbol, timeframe))
        return frame

    monkeypatch.setattr(ls, "fetch_live_candles", fake_fetch)
    monkeypatch.setattr(ls.time, "sleep", lambda *_: None)
    monkeypatch.setattr(ls, "_daily_candles", {})

    # Pass 1: one download per stock and timeframe, however many strategies ask.
    one = {}
    ls.candles_for_scan("RELIANCE", "1D", one)
    ls.candles_for_scan("RELIANCE", "1D", one)
    ls.candles_for_scan("IFCI", "15m", one)
    assert calls == [("RELIANCE", "1D"), ("IFCI", "15m")]

    # Pass 2 (a new per-pass cache): daily comes from the store, intraday is fetched again.
    two = {}
    ls.candles_for_scan("RELIANCE", "1D", two)
    ls.candles_for_scan("IFCI", "15m", two)
    assert calls == [("RELIANCE", "1D"), ("IFCI", "15m"), ("IFCI", "15m")]

    # Once the stored copy is too old it is fetched again.
    monkeypatch.setattr(ls, "DAILY_CANDLES_MAX_AGE_SECONDS", 0)
    ls.candles_for_scan("RELIANCE", "1D", {})
    assert calls[-1] == ("RELIANCE", "1D") and len(calls) == 4


def test_a_failed_daily_download_is_not_kept(monkeypatch):
    import pandas as pd
    import scanner.live_scanner as ls

    calls = []
    monkeypatch.setattr(ls, "fetch_live_candles", lambda s, t: calls.append(s) or pd.DataFrame())
    monkeypatch.setattr(ls.time, "sleep", lambda *_: None)
    monkeypatch.setattr(ls, "_daily_candles", {})
    ls.candles_for_scan("TCS", "1D", {})
    ls.candles_for_scan("TCS", "1D", {})
    assert calls == ["TCS", "TCS"]   # tried again on the next pass
