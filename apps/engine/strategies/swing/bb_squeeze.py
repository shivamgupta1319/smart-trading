import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class BBSqueezeStrategy(BaseStrategy):
    """Strategy 8: Bollinger Band Squeeze (Swing)"""
    name = "BB_Squeeze"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is None or bb.empty:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['bb_upper'] = bb['BBU_20_2.0_2.0']
        df['bb_lower'] = bb['BBL_20_2.0_2.0']
        df['bb_mid'] = bb['BBM_20_2.0_2.0']
        df['bb_bandwidth'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']

        # 6-month low of bandwidth (120 trading days)
        df['bw_rolling_min'] = df['bb_bandwidth'].rolling(120, min_periods=60).min()

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        is_squeeze = df['bb_bandwidth'] <= df['bw_rolling_min'] * 1.05  # within 5% of 6m low
        
        bullish_breakout = (df['Close'] > df['bb_upper'])
        prev_bullish_breakout = (df['Close'].shift(1) > df['bb_upper'].shift(1))
        
        bearish_breakout = (df['Close'] < df['bb_lower'])
        prev_bearish_breakout = (df['Close'].shift(1) < df['bb_lower'].shift(1))

        bullish_cond = is_squeeze & bullish_breakout & ~prev_bullish_breakout
        bearish_cond = is_squeeze & bearish_breakout & ~prev_bearish_breakout

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = df['bb_mid'][bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + 2 * (df['Close'][bullish_cond] - df['bb_mid'][bullish_cond])

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = df['bb_mid'][bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - 2 * (df['bb_mid'][bearish_cond] - df['Close'][bearish_cond])

        return df
