import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class MacdStochConfluenceStrategy(BaseStrategy):
    """Strategy 13: MACD and Stochastic Confluence"""
    name = "MACD_Stoch_Confluence"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # MACD (12, 26, 9)
        macd = ta.macd(df['Close'])
        if macd is not None and not macd.empty:
            df['macd'] = macd['MACD_12_26_9']
        else:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df
            
        # Stochastic (14, 3, 3)
        stoch = ta.stoch(df['High'], df['Low'], df['Close'])
        if stoch is not None and not stoch.empty:
            df['stoch_k'] = stoch['STOCHk_14_3_3']
            df['stoch_d'] = stoch['STOCHd_14_3_3']
        else:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_stoch_k = df['stoch_k'].shift(1)
        prev_stoch_d = df['stoch_d'].shift(1)

        # Bullish: MACD is positive, Stochastic K crosses above D from oversold (<40)
        stoch_cross_up = (prev_stoch_k <= prev_stoch_d) & (df['stoch_k'] > df['stoch_d'])
        bullish_cond = (df['macd'] > 0) & stoch_cross_up & (df['stoch_k'] < 40)

        # Bearish: MACD is negative, Stochastic K crosses below D from overbought (>60)
        stoch_cross_down = (prev_stoch_k >= prev_stoch_d) & (df['stoch_k'] < df['stoch_d'])
        bearish_cond = (df['macd'] < 0) & stoch_cross_down & (df['stoch_k'] > 60)

        sl_bull = df['Close'] - 1.5 * df['atr']
        sl_bear = df['Close'] + 1.5 * df['atr']

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = sl_bull[bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + 3 * df['atr'][bullish_cond]

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = sl_bear[bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - 3 * df['atr'][bearish_cond]

        return df
