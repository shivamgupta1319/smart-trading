"""Strategy 13: MACD and Stochastic Confluence"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class MacdStochConfluenceStrategy(BaseStrategy):
    name = "MACD_Stoch_Confluence"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # MACD (12, 26, 9)
        macd = ta.macd(df['Close'])
        if macd is not None:
            df['macd'] = macd['MACD_12_26_9']
            df['macds'] = macd['MACDs_12_26_9']
            df['macdh'] = macd['MACDh_12_26_9']
        else:
            df['macd'] = pd.NA
            df['macds'] = pd.NA
            df['macdh'] = pd.NA
            
        # Stochastic (14, 3, 3)
        stoch = ta.stoch(df['High'], df['Low'], df['Close'])
        if stoch is not None:
            df['stoch_k'] = stoch['STOCHk_14_3_3']
            df['stoch_d'] = stoch['STOCHd_14_3_3']
        else:
            df['stoch_k'] = pd.NA
            df['stoch_d'] = pd.NA

        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]

            if any(pd.isna([curr['macd'], curr['stoch_k'], curr['atr']])):
                continue

            # Bullish: MACD is positive (above zero line), Stochastic K crosses above D from oversold (<20)
            stoch_cross_up = prev['stoch_k'] <= prev['stoch_d'] and curr['stoch_k'] > curr['stoch_d']
            if curr['macd'] > 0 and stoch_cross_up and curr['stoch_k'] < 40:
                sl = curr['Close'] - 1.5 * curr['atr']
                target = curr['Close'] + 3 * curr['atr'] # 1:2 Risk Reward
                
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = target
            
            # Bearish: MACD is negative, Stochastic K crosses below D from overbought (>80)
            stoch_cross_down = prev['stoch_k'] >= prev['stoch_d'] and curr['stoch_k'] < curr['stoch_d']
            if curr['macd'] < 0 and stoch_cross_down and curr['stoch_k'] > 60:
                sl = curr['Close'] + 1.5 * curr['atr']
                target = curr['Close'] - 3 * curr['atr']
                
                df.iloc[i, df.columns.get_loc('signal')] = -1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = target

        return df
