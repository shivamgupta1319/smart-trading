import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class SuperTrendEMAStrategy(BaseStrategy):
    """Strategy 11: SuperTrend + EMA Crossover"""
    name = "SuperTrend_EMA"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        df['ema5'] = ta.ema(df['Close'], length=5)
        df['ema20'] = ta.ema(df['Close'], length=20)
        
        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=7, multiplier=3)
        if st is not None and not st.empty:
            df['supertrend'] = st['SUPERT_7_3']
            df['supertrend_dir'] = st['SUPERTd_7_3']
        else:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df
            
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_ema5 = df['ema5'].shift(1)
        prev_ema20 = df['ema20'].shift(1)

        ema_cross_up = (prev_ema5 <= prev_ema20) & (df['ema5'] > df['ema20'])
        ema_cross_down = (prev_ema5 >= prev_ema20) & (df['ema5'] < df['ema20'])

        st_green = df['supertrend_dir'] == 1
        st_red = df['supertrend_dir'] == -1

        bullish_cond = ema_cross_up & st_green
        bearish_cond = ema_cross_down & st_red

        sl_bull = df['supertrend'] - df['atr']
        sl_bear = df['supertrend'] + df['atr']

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = sl_bull[bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + 2.5 * (df['Close'][bullish_cond] - sl_bull[bullish_cond])

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = sl_bear[bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - 2.5 * (sl_bear[bearish_cond] - df['Close'][bearish_cond])

        return df
