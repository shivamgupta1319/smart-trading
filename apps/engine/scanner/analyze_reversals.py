import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from sqlalchemy import text
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from db.client import engine

def fetch_intraday_candles(symbol: str, trade_date: datetime) -> pd.DataFrame:
    yf_symbol = symbol if symbol.endswith(".NS") else symbol + ".NS"
    start = trade_date.strftime('%Y-%m-%d')
    end = (trade_date + timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        df = yf.download(yf_symbol, start=start, end=end, interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            df = yf.download(yf_symbol, start=start, end=end, interval="15m", progress=False, auto_adjust=True)
        if not df.empty:
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        return df
    except Exception as e:
        return pd.DataFrame()

def main():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, symbol, "strategyName", "signalType", "entryPrice", "stopLoss", target, 
                   "exitPrice", pnl, outcome, "entryTime"
            FROM "Trade" 
            WHERE status = 'CLOSED' AND outcome IS NOT NULL
            ORDER BY id ASC
        """)).fetchall()

    columns = ['id', 'symbol', 'strategyName', 'signalType', 'entryPrice', 'stopLoss', 'target', 'exitPrice', 'pnl', 'outcome', 'entryTime']
    trades = [dict(zip(columns, row)) for row in rows]

    reversal_trades = []

    for trade in trades:
        symbol = trade['symbol']
        entry_time = trade['entryTime']
        trade_date = entry_time if isinstance(entry_time, datetime) else datetime.fromisoformat(str(entry_time))
        
        candles = fetch_intraday_candles(symbol, trade_date)
        if candles.empty:
            continue

        entry = trade['entryPrice']
        tp = trade['target']
        is_buy = trade['signalType'] == 'BUY'
        
        # Calculate max progress
        if is_buy:
            peak_price = candles['High'].max()
            total_dist = tp - entry
            progress = (peak_price - entry) / total_dist if total_dist > 0 else 0
        else:
            peak_price = candles['Low'].min()
            total_dist = entry - tp
            progress = (entry - peak_price) / total_dist if total_dist > 0 else 0

        # We care about trades that went > 50% but then reversed to < 50% or loss
        actual_progress = 0
        if is_buy:
            actual_progress = (trade['exitPrice'] - entry) / total_dist if total_dist > 0 else 0
        else:
            actual_progress = (entry - trade['exitPrice']) / total_dist if total_dist > 0 else 0

        if progress >= 0.5 and actual_progress < 0.4:
            # Find the peak candle
            peak_idx = None
            if is_buy:
                peak_idx = candles['High'].idxmax()
            else:
                peak_idx = candles['Low'].idxmin()

            # Get 3 candles before peak and peak candle
            try:
                peak_pos = candles.index.get_loc(peak_idx)
                lookback = candles.iloc[max(0, peak_pos - 3): peak_pos + 1]
                
                # Volume analysis
                avg_vol = candles['Volume'].mean()
                peak_vol = lookback.iloc[-1]['Volume']
                prev_vol = lookback.iloc[-2]['Volume'] if len(lookback) > 1 else 0
                
                vol_spike = (peak_vol > 1.5 * avg_vol) or (prev_vol > 1.5 * avg_vol)
                
                # Target proximity to round numbers (like 100, 500, 1000)
                is_near_round = False
                for r in [50, 100, 500, 1000]:
                    if abs(tp % r) < (tp * 0.002): # within 0.2% of a round number
                        is_near_round = True
                        break

                reversal_trades.append({
                    'id': trade['id'],
                    'symbol': symbol,
                    'type': trade['signalType'],
                    'peak_progress': progress,
                    'actual_progress': actual_progress,
                    'vol_spike': vol_spike,
                    'peak_vol_ratio': peak_vol / avg_vol if avg_vol > 0 else 0,
                    'prev_vol_ratio': prev_vol / avg_vol if avg_vol > 0 else 0,
                    'near_round_target': is_near_round,
                    'target': tp
                })
            except Exception as e:
                pass

    print(f"Found {len(reversal_trades)} trades that peaked >50% but reversed significantly.")
    for rt in reversal_trades:
        print(f"#{rt['id']} {rt['type']} {rt['symbol']} | Peak: {rt['peak_progress']*100:.0f}% | Actual: {rt['actual_progress']*100:.0f}% | Target: {rt['target']}")
        print(f"   -> Vol Spike (Peak or Prev): {rt['vol_spike']} (Peak Vol: {rt['peak_vol_ratio']:.1f}x avg, Prev: {rt['prev_vol_ratio']:.1f}x avg)")
        print(f"   -> Near Round Number Target: {rt['near_round_target']}")
        print("-" * 50)

if __name__ == "__main__":
    main()
