"""Candle data checks, the price-jump review list and the demerger adjustment.

Run from apps/engine:  python -m pytest test/test_data_checks.py -q
"""
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_checks  # noqa: E402
from data_checks import (  # noqa: E402
    adjustment_shift, back_adjust, clean_candles, load_known_actions, price_jumps, unexplained_jumps,
)


def _bars(idx, rows):
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000.0}, index=pd.DatetimeIndex(idx))


GOOD = (100.0, 101.0, 99.0, 100.5)


# ── clean_candles ─────────────────────────────────────────────────────────────

def test_good_candles_pass_untouched():
    df = _bars(pd.date_range("2026-11-16", periods=4, freq="D"), [GOOD] * 4)
    out, problems = clean_candles(df, "1D")
    assert problems == [] and out.equals(df)


def test_rows_that_cannot_be_real_are_left_out_and_counted():
    idx = pd.date_range("2026-11-16", periods=6, freq="D")
    df = _bars(idx, [
        GOOD,
        (100.0, 101.0, 99.0, np.nan),      # missing close
        (0.0, 1.0, 0.0, 0.5),              # zero price
        (100.0, 99.5, 99.0, 100.2),        # high below the open and close
        (100.0, 101.0, 100.4, 100.2),      # low above the open and close
        GOOD,
    ])
    df.loc[idx[5], "Volume"] = -5
    out, problems = clean_candles(df, "1D")
    found = {p.check: p.rows for p in problems}
    assert found == {"missing_value": 1, "non_positive_price": 1, "high_low_inconsistent": 2, "negative_volume": 1}
    assert list(out.index) == [idx[0]]      # nothing fake left in; only the clean row is stored


def test_intraday_bars_outside_market_hours_and_repeats_go():
    idx = pd.to_datetime(["2026-11-19 09:10", "2026-11-19 09:15", "2026-11-19 15:25", "2026-11-19 15:30",
                          "2026-11-19 18:15", "2026-11-19 09:15"])
    out, problems = clean_candles(_bars(idx, [GOOD] * 6), "5m")
    found = {p.check: p.rows for p in problems}
    assert found["outside_market_hours"] == 3            # 09:10, 15:30, 18:15 (Muhurat-style)
    assert found["duplicate_timestamp"] == 1
    assert [t.strftime("%H:%M") for t in out.index] == ["09:15", "15:25"]


def test_a_saturday_session_is_kept():
    # NSE trades on some Saturdays (Budget day, 1 Feb 2025). A weekend is not an error.
    df = _bars(pd.to_datetime(["2025-01-31", "2025-02-01", "2025-02-03"]), [GOOD] * 3)
    out, problems = clean_candles(df, "1D")
    assert problems == [] and len(out) == 3


# ── price jumps and the review list ───────────────────────────────────────────

def _close(values, start="2026-04-27"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


def test_a_move_above_20_percent_is_a_jump():
    jumps = price_jumps(_close([770, 772, 773.6, 271.5, 270]))
    assert len(jumps) == 1 and jumps[0].day == date(2026, 4, 30) and jumps[0].pct == pytest.approx(-64.9, abs=0.05)
    assert price_jumps(_close([100, 110, 99, 108])) == []       # ordinary swings are not flagged


def test_reviewed_dates_are_explained_and_others_are_not():
    close = _close([770, 772, 773.6, 271.5, 270])
    known = {"VEDL": [{"date": date(2026, 4, 30), "kind": "demerger", "note": ""}]}
    assert unexplained_jumps("VEDL", close, known) == []
    assert [str(j) for j in unexplained_jumps("OTHER", close, known)] == ["2026-04-30 -64.9%"]


def test_the_shipped_review_list_loads_and_is_well_formed():
    load_known_actions.cache_clear()
    known = load_known_actions()
    assert known["VEDL"][0] == {"date": date(2026, 4, 30), "kind": "demerger",
                                "note": known["VEDL"][0]["note"]}
    assert {e["kind"] for entries in known.values() for e in entries} <= {"real_move", "demerger", "bonus"}
    assert not any(k.startswith("_") for k in known)


def test_a_typo_in_the_review_list_stops_the_run(tmp_path, monkeypatch):
    bad = tmp_path / "known.json"
    bad.write_text('{"ABC": [{"date": "2026-01-02", "kind": "demergr"}]}')
    monkeypatch.setenv("KNOWN_PRICE_ACTIONS_PATH", str(bad))
    load_known_actions.cache_clear()
    with pytest.raises(ValueError):
        load_known_actions()
    monkeypatch.delenv("KNOWN_PRICE_ACTIONS_PATH")
    load_known_actions.cache_clear()


# ── demerger adjustment ───────────────────────────────────────────────────────

KNOWN = {"VEDL": [{"date": date(2026, 4, 30), "kind": "demerger", "note": ""}],
         "ADANIENT": [{"date": date(2023, 1, 27), "kind": "real_move", "note": ""}]}


def test_prices_before_a_demerger_are_scaled_so_the_series_is_continuous():
    idx = pd.to_datetime(["2026-04-28", "2026-04-29", "2026-04-30", "2026-05-04"])
    df = _bars(idx, [(760, 775, 755, 770), (770, 780, 765, 773.6), (272, 275, 268, 271.5), (271, 276, 270, 274)])
    out = back_adjust(df, "VEDL", KNOWN)
    factor = 271.5 / 773.6
    assert out["Close"].iloc[1] == pytest.approx(271.5)                 # day before now meets the day of
    assert out["High"].iloc[0] == pytest.approx(775 * factor)
    assert out.iloc[2:].astype(float).equals(df.iloc[2:].astype(float))  # the day itself and after: untouched
    assert price_jumps(out["Close"]) == []                              # the fake -65% is gone
    assert df["Close"].iloc[1] == 773.6                                 # the caller's frame is not changed
    assert out["Volume"].equals(df["Volume"])


def test_real_moves_and_unlisted_stocks_are_never_scaled():
    idx = pd.to_datetime(["2023-01-25", "2023-01-27"])
    df = _bars(idx, [(3380, 3400, 3350, 3382.8), (3300, 3320, 2700, 2756.4)])
    assert back_adjust(df, "ADANIENT", KNOWN) is df      # a crash stays a crash
    assert back_adjust(df, "RELIANCE", KNOWN) is df


def test_a_bonus_step_the_source_did_not_carry_back_is_scaled_like_a_demerger():
    # TRENT: 1-for-2 bonus, prices adjusted by the source only back to 2026-01-01.
    known = {"TRENT": [{"date": date(2026, 1, 1), "kind": "bonus", "note": ""}]}
    idx = pd.to_datetime(["2025-12-30", "2025-12-31", "2026-01-01", "2026-01-02"])
    df = _bars(idx, [(4250, 4290, 4240, 4265), (4265, 4300, 4250, 4272.7), (2850, 2880, 2840, 2860.7), (2860, 2890, 2850, 2875)])
    out = back_adjust(df, "TRENT", known)
    assert out["Close"].iloc[1] == pytest.approx(2860.7)
    assert price_jumps(out["Close"]) == []
    assert unexplained_jumps("TRENT", df["Close"], known) == []


def test_the_shipped_list_explains_every_move_that_was_flagged_in_november_2026():
    load_known_actions.cache_clear()
    known = load_known_actions()
    assert {e["date"] for e in known["KAYNES"]} >= {date(2024, 6, 4), date(2026, 5, 14)}
    assert known["TRENT"][0]["kind"] == "bonus" and known["TMPV"][0]["kind"] == "demerger"


def test_a_frame_that_does_not_span_the_date_is_unchanged():
    after_only = _bars(pd.to_datetime(["2026-05-04", "2026-05-05"]), [GOOD, GOOD])
    assert back_adjust(after_only, "VEDL", KNOWN) is after_only


def test_intraday_uses_the_first_open_of_the_day_as_the_new_level():
    idx = pd.to_datetime(["2026-04-29 15:15", "2026-04-30 09:15", "2026-04-30 09:30"])
    df = _bars(idx, [(772, 775, 771, 773.6), (270, 274, 268, 273), (273, 276, 272, 275)])
    out = back_adjust(df, "VEDL", KNOWN)
    assert out["Close"].iloc[0] == pytest.approx(270.0)                 # prior close now equals the open


# ── re-scaled history ─────────────────────────────────────────────────────────

def test_a_split_rescaling_is_detected_and_ordinary_noise_is_not():
    idx = pd.date_range("2026-05-25", periods=5, freq="D")
    stored = pd.Series([4290.0, 4300.0, 4310.0, 4272.7, 4280.0], index=idx)
    assert adjustment_shift(stored, stored / 1.5) == pytest.approx(1 / 1.5)      # 1.5-for-1 split
    assert adjustment_shift(stored, stored * 1.0005) is None                     # rounding noise
    # Only the newest bar differs (it was still forming when stored): not a re-scaling.
    fetched = stored.copy()
    fetched.iloc[-1] = 4400.0
    assert adjustment_shift(stored, fetched) is None
    assert adjustment_shift(stored.iloc[:1], stored.iloc[:1]) is None            # too little overlap


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
