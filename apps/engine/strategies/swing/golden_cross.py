import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class GoldenCrossStrategy(BaseStrategy):
    """Strategy 10: 50/200 Golden Cross (Swing)"""
    name = "Golden_Cross"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # Needs a full 200-period SMA; on shorter slices (e.g. a walk-forward
        # fold) pandas_ta returns None, so guard before touching it.
        if df.empty or len(df) < 200:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['sma50'] = ta.sma(df['Close'], length=50)
        df['sma200'] = ta.sma(df['Close'], length=200)
        df['atr14'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_sma50 = df['sma50'].shift(1)
        prev_sma200 = df['sma200'].shift(1)

        golden = (prev_sma50 <= prev_sma200) & (df['sma50'] > df['sma200'])
        death = (prev_sma50 >= prev_sma200) & (df['sma50'] < df['sma200'])

        sl_bull = df['sma50'] - 1.5 * df['atr14']
        sl_bear = df['sma50'] + 1.5 * df['atr14']

        df.loc[golden, 'signal'] = 1
        df.loc[golden, 'stop_loss'] = sl_bull[golden]
        df.loc[golden, 'target'] = df['Close'][golden] + 2 * (df['Close'][golden] - sl_bull[golden])

        df.loc[death, 'signal'] = -1
        df.loc[death, 'stop_loss'] = sl_bear[death]
        df.loc[death, 'target'] = df['Close'][death] - 2 * (sl_bear[death] - df['Close'][death])

        return df
