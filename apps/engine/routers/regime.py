"""Market regime detection.

Classifies the current market (or a single stock) as TRENDING_UP / TRENDING_DOWN
/ RANGING / VOLATILE using ADX (trend strength), directional movement, and ATR%
(volatility). Used to tell which *kind* of strategy is in/out of favour — e.g.
trend-followers in a trend, mean-reverters in a range.
"""
import numpy as np
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from fastapi import APIRouter, HTTPException

router = APIRouter()

INDEX_SYMBOL = "^NSEI"  # NIFTY 50

# Which strategy families historically suit each regime (guidance, not gospel).
REGIME_PLAYBOOK = {
    "TRENDING_UP": {
        "favoured": ["Trend-following", "Breakout", "Pullback-to-MA", "Supertrend/EMA"],
        "avoid": ["Mean-reversion fades", "Counter-trend shorts"],
    },
    "TRENDING_DOWN": {
        "favoured": ["Trend-following shorts", "Breakdown", "Avoid fresh longs"],
        "avoid": ["Bottom-fishing", "Buy-the-dip without confirmation"],
    },
    "RANGING": {
        "favoured": ["Mean-reversion (BB, RSI, Channel)", "Support/Resistance fades"],
        "avoid": ["Breakout chasing (false breaks)"],
    },
    "VOLATILE": {
        "favoured": ["Reduced size", "ORB with wide stops", "Wait for clarity"],
        "avoid": ["Tight stops", "Over-leverage"],
    },
}


def _classify(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 60:
        raise HTTPException(status_code=400, detail="Not enough data to classify regime")

    close = df["Close"]
    adx_df = ta.adx(df["High"], df["Low"], close, length=14)
    atr = ta.atr(df["High"], df["Low"], close, length=14)
    ema50 = ta.ema(close, length=50)
    ema200 = ta.ema(close, length=200)

    adx = float(adx_df[f"ADX_14"].iloc[-1])
    dmp = float(adx_df["DMP_14"].iloc[-1])
    dmn = float(adx_df["DMN_14"].iloc[-1])
    last = float(close.iloc[-1])
    atr_pct = float(atr.iloc[-1]) / last * 100 if last else 0.0
    e50 = float(ema50.iloc[-1]) if ema50 is not None and not np.isnan(ema50.iloc[-1]) else last
    e200 = float(ema200.iloc[-1]) if ema200 is not None and not np.isnan(ema200.iloc[-1]) else last

    # Volatility takes precedence — a violent tape overrides trend/range labels.
    if atr_pct >= 3.0:
        regime = "VOLATILE"
    elif adx >= 25:
        regime = "TRENDING_UP" if dmp >= dmn and last >= e50 else "TRENDING_DOWN"
    elif adx < 20:
        regime = "RANGING"
    else:
        # 20-25 ADX: lean on price structure
        regime = "TRENDING_UP" if last > e50 > e200 else "RANGING"

    strength = "strong" if adx >= 30 else "moderate" if adx >= 20 else "weak"
    return {
        "regime": regime,
        "adx": round(adx, 1),
        "trendStrength": strength,
        "atrPct": round(atr_pct, 2),
        "priceVsEma50": round((last / e50 - 1) * 100, 2) if e50 else 0.0,
        "priceVsEma200": round((last / e200 - 1) * 100, 2) if e200 else 0.0,
        "playbook": REGIME_PLAYBOOK[regime],
    }


def _load_yf(symbol: str, is_index: bool) -> pd.DataFrame:
    yf_sym = symbol if is_index else (symbol if symbol.endswith(".NS") else symbol + ".NS")
    df = yf.Ticker(yf_sym).history(period="1y", interval="1d")
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


@router.get("/regime")
def market_regime():
    """Overall NIFTY-50 market regime."""
    df = _load_yf(INDEX_SYMBOL, is_index=True)
    return {"scope": "NIFTY 50", **_classify(df)}


@router.get("/regime/{symbol}")
def stock_regime(symbol: str):
    """Regime for a single stock."""
    df = _load_yf(symbol.upper(), is_index=False)
    return {"scope": symbol.upper(), **_classify(df)}
