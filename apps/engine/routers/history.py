"""POST /api/engine/fetch-history — Downloads OHLCV from yfinance and stores in PostgreSQL"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy import text
from db.client import engine
from cache import cached, cache_get, cache_set
from data_checks import adjustment_shift, clean_candles, unexplained_jumps

router = APIRouter()

LIVE_PRICE_TTL = float(os.getenv("LIVE_PRICE_TTL_S", "20"))
CHART_TTL = float(os.getenv("CHART_TTL_S", "60"))

IST = "Asia/Kolkata"

TIMEFRAME_CONFIG = {
    "1D": {"period": "5y", "interval": "1d"},
    "15m": {"period": "60d", "interval": "15m"},
    "5m": {"period": "60d", "interval": "5m"},
}


def normalize_to_ist_naive(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance returns tz-aware timestamps (exchange tz / UTC depending on
    interval & version). Storing them naively (as the old code did) silently
    shifted intraday bars by hours, corrupting any session-aware strategy
    (ORB/VWAP/CPR). Normalize every index to IST wall-clock, then drop tz so
    time-of-day comparisons against NSE hours (09:15–15:30) are correct."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return df
    df = df.copy()
    if df.index.tz is not None:
        df.index = df.index.tz_convert(IST).tz_localize(None)
    return df


class FetchHistoryRequest(BaseModel):
    symbol: str
    timeframes: List[str] = ["1D", "15m", "5m"]


def get_stock_id(symbol: str) -> int:
    with engine.connect() as conn:
        result = conn.execute(
            text('SELECT id FROM "Stock" WHERE symbol = :sym'),
            {"sym": symbol.upper()}
        ).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found in DB. Add it first.")
        return result[0]


def _resolve_stock_id(symbol: str):
    """Non-raising stock-id lookup (returns None if absent) for non-HTTP callers."""
    with engine.connect() as conn:
        result = conn.execute(
            text('SELECT id FROM "Stock" WHERE symbol = :sym'),
            {"sym": symbol.upper()}
        ).fetchone()
        return result[0] if result else None


def _last_timestamp(stock_id: int, timeframe: str):
    """Newest stored bar for (stock, timeframe), or None if we have no data yet.
    Stored timestamps are IST-naive (see normalize_to_ist_naive)."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT MAX("timestamp") FROM "HistoricalData"
            WHERE "stockId" = :sid AND timeframe = :tf
        """), {"sid": stock_id, "tf": timeframe}).fetchone()
    return row[0] if row and row[0] else None


def fetch_and_store(symbol: str, timeframes=None, incremental: bool = True) -> dict:
    """Download OHLCV from yfinance and upsert into HistoricalData.

    Shared core for the HTTP endpoint and the background fetch scheduler. Because
    upsert never deletes, repeated runs accumulate history beyond yfinance's
    per-request intraday window (15m/5m are capped to ~60 days per call), which is
    how the backtest dataset grows over time. Returns per-timeframe row counts.

    With ``incremental`` (default), we only pull what's missing: a stock with NO
    stored data for a timeframe gets the full window (yfinance ``period``), while a
    stock that already has data is topped up from its last stored bar forward
    (yfinance ``start``) — so old + only-the-new candles merge via upsert instead
    of re-downloading years every run. Pass ``incremental=False`` to force a full
    re-pull (e.g. to backfill/repair a corrupted series).
    """
    timeframes = timeframes or ["1D", "15m", "5m"]
    original_symbol = symbol.upper()
    stock_id = _resolve_stock_id(original_symbol)
    if stock_id is None:
        return {"symbol": original_symbol, "error": "not found in Stock table"}

    yf_symbol = original_symbol if original_symbol.endswith(".NS") else original_symbol + ".NS"
    results = {}
    ticker = yf.Ticker(yf_symbol)

    for tf in timeframes:
        if tf not in TIMEFRAME_CONFIG:
            continue
        cfg = TIMEFRAME_CONFIG[tf]
        last_ts = _last_timestamp(stock_id, tf) if incremental else None
        mode = "full" if last_ts is None else "incremental"
        try:
            if last_ts is None:
                # No data yet → pull the full window.
                df = ticker.history(period=cfg["period"], interval=cfg["interval"])
            else:
                # Have data → fetch only from the last stored bar forward. A small
                # buffer re-fetches the most recent bars so a partial/adjusted last
                # candle gets corrected; the upsert merges old + new cleanly.
                buffer_days = 5 if cfg["interval"] == "1d" else 1
                start = (last_ts - timedelta(days=buffer_days)).date()
                # yfinance caps intraday history to ~60 days per request — never ask
                # for an intraday start older than that or the call errors out.
                if cfg["interval"] != "1d":
                    earliest = (datetime.now() - timedelta(days=59)).date()
                    if start < earliest:
                        start = earliest
                df = ticker.history(start=start.isoformat(), interval=cfg["interval"])
            if df.empty:
                results[tf] = {"rows": 0, "status": "empty", "mode": mode}
                continue
            df = normalize_to_ist_naive(df[['Open', 'High', 'Low', 'Close', 'Volume']])

            # Has the source re-scaled its history (split / dividend adjustment) since
            # we stored ours? Then the stored bars are on the old scale and topping up
            # would stitch two scales together. Replace the whole series instead.
            if mode == "incremental":
                shift = adjustment_shift(_stored_closes(stock_id, tf, df.index.min()), df["Close"])
                if shift is not None:
                    print(f"[history] {original_symbol} {tf}: source re-scaled its prices "
                          f"(x{shift:.4f}); replacing the stored series")
                    full = ticker.history(period=cfg["period"], interval=cfg["interval"])
                    if not full.empty:
                        df = normalize_to_ist_naive(full[['Open', 'High', 'Low', 'Close', 'Volume']])
                        _delete_series(stock_id, tf)
                        mode = "replaced (re-scaled)"

            # Leave out rows that cannot be real, and say how many (never silently).
            df, problems = clean_candles(df, tf)
            rows = upsert_ohlcv(stock_id, df, tf)
            results[tf] = {"rows": rows, "status": "ok", "mode": mode}
            if problems:
                results[tf]["left_out"] = [str(p) for p in problems]
                print(f"[history] {original_symbol} {tf}: " + "; ".join(str(p) for p in problems))
            if tf == "1D":
                results[tf]["needs_review"] = update_data_flag(stock_id, original_symbol)
        except Exception as e:
            results[tf] = {"rows": 0, "status": f"error: {str(e)}", "mode": mode}
        time.sleep(1)  # Rate limit friendly

    return {"symbol": original_symbol, "results": results}


def _stored_closes(stock_id: int, timeframe: str, since) -> pd.Series:
    """Stored closes from `since` on, indexed by timestamp (for the re-scaling check)."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT "timestamp", close FROM "HistoricalData"
            WHERE "stockId" = :sid AND timeframe = :tf AND "timestamp" >= :since
            ORDER BY "timestamp"
        """), {"sid": stock_id, "tf": timeframe, "since": pd.Timestamp(since).to_pydatetime()}).fetchall()
    return pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in rows}, dtype=float)


def _delete_series(stock_id: int, timeframe: str) -> None:
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM "HistoricalData" WHERE "stockId" = :sid AND timeframe = :tf'),
                     {"sid": stock_id, "tf": timeframe})


def update_data_flag(stock_id: int, symbol: str) -> list[str]:
    """Mark the stock when its stored daily history has a large move nobody has reviewed
    (config/known_price_actions.json), or clear the mark when it has none. Returns the
    unreviewed moves as text. A failure here never fails the fetch."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT "timestamp", close FROM "HistoricalData"
                WHERE "stockId" = :sid AND timeframe = '1D' ORDER BY "timestamp"
            """), {"sid": stock_id}).fetchall()
        close = pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in rows}, dtype=float)
        jumps = [str(j) for j in unexplained_jumps(symbol, close)]
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE "Stock" SET "dataFlag" = :flag, "dataFlagDetail" = :detail WHERE id = :sid
            """), {"sid": stock_id, "flag": "PRICE_JUMP" if jumps else None,
                   "detail": "; ".join(jumps) if jumps else None})
        return jumps
    except Exception as exc:
        print(f"[history] {symbol}: data flag not updated: {type(exc).__name__}: {exc}")
        return []


def upsert_ohlcv(stock_id: int, df: pd.DataFrame, timeframe: str):
    if df.empty:
        return 0

    df = normalize_to_ist_naive(df)

    # Build one parameter list and issue a single batched executemany instead of
    # thousands of individual round-trips (the old behaviour).
    params = [
        {
            "sid": stock_id,
            "ts": pd.Timestamp(ts).to_pydatetime(),
            "o": float(row["Open"]), "h": float(row["High"]),
            "l": float(row["Low"]), "c": float(row["Close"]),
            "v": float(row.get("Volume", 0)), "tf": timeframe,
        }
        for ts, row in df.iterrows()
    ]
    if not params:
        return 0

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO "HistoricalData" ("stockId", "timestamp", "open", "high", "low", "close", "volume", "timeframe")
            VALUES (:sid, :ts, :o, :h, :l, :c, :v, :tf)
            ON CONFLICT ("stockId", "timestamp", "timeframe") DO UPDATE
            SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                close=EXCLUDED.close, volume=EXCLUDED.volume
        """), params)
    return len(params)


@router.post("/fetch-history")
def fetch_history(req: FetchHistoryRequest):
    get_stock_id(req.symbol)  # validate the symbol exists → 404 if not
    return fetch_and_store(req.symbol, req.timeframes)

class LivePriceRequest(BaseModel):
    symbols: List[str]

# How many quotes to fetch at once. The dashboard asks for every active stock; one at a
# time that was 60 slow calls in a row (prices sat on "loading" for half a minute and the
# next poll piled on top), and a burst of that size is what gets the data source to
# answer "currently down".
LIVE_PRICE_WORKERS = 6
# A quote that failed to refresh is still shown if it is at most this old (seconds).
LIVE_PRICE_STALE_OK = 300


def _fetch_quote(sym: str):
    from brokers import get_live_price as _broker_live_price

    try:
        return _broker_live_price(sym)  # Dhan/Upstox when configured, else yfinance
    except Exception as exc:  # one bad symbol must not fail the whole request
        print(f"[live-prices] {sym}: {type(exc).__name__}: {exc}")
        return None


@router.post("/live-prices")
def get_live_prices(req: LivePriceRequest):
    results = {}
    missing = []
    for sym in dict.fromkeys(req.symbols):  # de-duplicate, keep order
        cached_val = cache_get(f"live:{sym}", LIVE_PRICE_TTL)
        if cached_val is not None:
            results[sym] = cached_val
        else:
            missing.append(sym)

    if missing:
        with ThreadPoolExecutor(max_workers=LIVE_PRICE_WORKERS) as pool:
            fetched = dict(zip(missing, pool.map(_fetch_quote, missing)))
        for sym, payload in fetched.items():
            if payload is not None:
                cache_set(f"live:{sym}", payload)
                results[sym] = payload
            else:
                # Refresh failed: an older quote is more useful than a blank.
                results[sym] = cache_get(f"live:{sym}", LIVE_PRICE_STALE_OK)
    return {sym: results.get(sym) for sym in req.symbols}


BENCHMARK_SYMBOL = "^NSEI"
BENCHMARK_TTL = 600  # seconds


def benchmark_return(closes: pd.Series, since) -> dict | None:
    """Return of simply holding the index from the first close on or after `since` to the
    latest close. None when there is no bar on or after that date."""
    closes = closes.dropna()
    window = closes[closes.index >= pd.Timestamp(since)]
    if window.empty:
        return None
    start, last = float(window.iloc[0]), float(closes.iloc[-1])
    return {
        "name": "NIFTY 50",
        "since": window.index[0].strftime("%Y-%m-%d"),
        "to": closes.index[-1].strftime("%Y-%m-%d"),
        "start_close": round(start, 2),
        "last_close": round(last, 2),
        "return_pct": round((last / start - 1) * 100, 2),
    }


@router.get("/benchmark")
def get_benchmark(since: str):
    """What holding NIFTY 50 did since `since` (YYYY-MM-DD). The honest yardstick: a
    strategy that makes less than this was not worth the effort."""
    try:
        start = pd.Timestamp(since[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="since must be a date like 2026-11-19")

    def _load():
        hist = yf.Ticker(BENCHMARK_SYMBOL).history(start=(start - timedelta(days=7)).date().isoformat())
        return normalize_to_ist_naive(hist)["Close"] if not hist.empty else pd.Series(dtype=float)

    try:
        closes = cached(f"benchmark:{start.date()}", BENCHMARK_TTL, _load)
    except Exception as exc:
        print(f"[benchmark] {type(exc).__name__}: {exc}")
        return {"status": "unavailable", "message": "The index data could not be loaded just now."}
    result = benchmark_return(closes, start) if len(closes) else None
    if result is None:
        return {"status": "unavailable", "message": "No index data for that period yet."}
    return {"status": "ok", **result}


@router.get("/chart-data/{symbol}")
def get_chart_data(symbol: str, timeframe: str = "1d"):
    """Return OHLCV + indicators for the candlestick chart component."""
    import pandas_ta as ta

    cache_key = f"chart:{symbol.upper()}:{timeframe}"
    cached_chart = cache_get(cache_key, CHART_TTL)
    if cached_chart is not None:
        return cached_chart

    yf_symbol = symbol if symbol.endswith(".NS") else symbol + ".NS"

    period_map = {"5m": "60d", "15m": "60d", "1h": "1mo", "1d": "1y", "1wk": "5y"}
    interval_map = {"5m": "5m", "15m": "15m", "1h": "60m", "1d": "1d", "1wk": "1wk"}

    period = period_map.get(timeframe, "1y")
    interval = interval_map.get(timeframe, "1d")

    ticker = yf.Ticker(yf_symbol)
    hist = ticker.history(period=period, interval=interval)

    if hist.empty:
        raise HTTPException(status_code=404, detail="No data found for this symbol/timeframe")

    hist = hist[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()

    # Compute indicators
    ema50 = ta.ema(hist['Close'], length=50)
    ema200 = ta.ema(hist['Close'], length=200)
    bb = ta.bbands(hist['Close'], length=20, std=2)

    # Build OHLCV array for lightweight-charts (expects unix timestamp in seconds)
    candles = []
    volumes = []
    for ts, row in hist.iterrows():
        t = int(pd.Timestamp(ts).timestamp())
        candles.append({
            "time": t,
            "open": round(float(row['Open']), 2),
            "high": round(float(row['High']), 2),
            "low": round(float(row['Low']), 2),
            "close": round(float(row['Close']), 2),
        })
        volumes.append({
            "time": t,
            "value": int(row['Volume']),
            "color": "rgba(34,211,238,0.3)" if row['Close'] >= row['Open'] else "rgba(248,113,113,0.3)",
        })

    # Build indicator series
    indicators = {}

    if ema50 is not None:
        ema50_data = []
        for ts, val in ema50.dropna().items():
            ema50_data.append({"time": int(pd.Timestamp(ts).timestamp()), "value": round(float(val), 2)})
        indicators["ema50"] = ema50_data

    if ema200 is not None:
        ema200_data = []
        for ts, val in ema200.dropna().items():
            ema200_data.append({"time": int(pd.Timestamp(ts).timestamp()), "value": round(float(val), 2)})
        indicators["ema200"] = ema200_data

    if bb is not None and not bb.empty:
        bb_upper = []
        bb_lower = []
        bb_mid = []
        upper_col = [c for c in bb.columns if 'BBU' in c]
        lower_col = [c for c in bb.columns if 'BBL' in c]
        mid_col = [c for c in bb.columns if 'BBM' in c]

        if upper_col and lower_col and mid_col:
            for ts in bb.index:
                t = int(pd.Timestamp(ts).timestamp())
                u = bb.at[ts, upper_col[0]]
                l = bb.at[ts, lower_col[0]]
                m = bb.at[ts, mid_col[0]]
                if pd.notna(u) and pd.notna(l) and pd.notna(m):
                    bb_upper.append({"time": t, "value": round(float(u), 2)})
                    bb_lower.append({"time": t, "value": round(float(l), 2)})
                    bb_mid.append({"time": t, "value": round(float(m), 2)})
            indicators["bbUpper"] = bb_upper
            indicators["bbLower"] = bb_lower
            indicators["bbMid"] = bb_mid

    result = {
        "candles": candles,
        "volumes": volumes,
        "indicators": indicators,
    }
    cache_set(cache_key, result)
    return result

