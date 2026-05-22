"""Strategy 11: SuperTrend + EMA Crossover"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class SuperTrendEMAStrategy(BaseStrategy):
    name = "SuperTrend_EMA"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # 5 and 20 EMA for crossover
        df['ema5'] = ta.ema(df['Close'], length=5)
        df['ema20'] = ta.ema(df['Close'], length=20)
        
        # SuperTrend (7, 3)
        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=7, multiplier=3)
        df['supertrend'] = st['SUPERT_7_3']
        df['supertrend_dir'] = st['SUPERTd_7_3'] # 1 for uptrend, -1 for downtrend
        
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]

            if any(pd.isna([curr['ema5'], curr['ema20'], curr['supertrend_dir'], curr['atr']])):
                continue

            # Bullish: EMA5 crosses above EMA20 AND SuperTrend is green (1)
            ema_cross_up = prev['ema5'] <= prev['ema20'] and curr['ema5'] > curr['ema20']
            st_green = curr['supertrend_dir'] == 1
            
            if ema_cross_up and st_green:
                sl = curr['supertrend'] - curr['atr'] # Trailing stop slightly below SuperTrend
                rr = curr['Close'] - sl
                target = curr['Close'] + 2.5 * rr # 1:2.5 risk reward
                
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = target
            
            # Bearish: EMA5 crosses below EMA20 AND SuperTrend is red (-1)
            ema_cross_down = prev['ema5'] >= prev['ema20'] and curr['ema5'] < curr['ema20']
            st_red = curr['supertrend_dir'] == -1
            
            if ema_cross_down and st_red:
                sl = curr['supertrend'] + curr['atr']
                rr = sl - curr['Close']
                target = curr['Close'] - 2.5 * rr
                
                df.iloc[i, df.columns.get_loc('signal')] = -1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = target

        return df
