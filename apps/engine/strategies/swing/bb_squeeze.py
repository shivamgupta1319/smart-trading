"""Strategy 8: Bollinger Band Squeeze (Swing)"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class BBSqueezeStrategy(BaseStrategy):
    name = "BB_Squeeze"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        bb = ta.bbands(df['Close'], length=20, std=2)
        df['bb_upper'] = bb['BBU_20_2.0_2.0']
        df['bb_lower'] = bb['BBL_20_2.0_2.0']
        df['bb_mid'] = bb['BBM_20_2.0_2.0']
        df['bb_bandwidth'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']

        # 6-month low of bandwidth (120 trading days)
        df['bw_rolling_min'] = df['bb_bandwidth'].rolling(120, min_periods=60).min()

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            curr = df.iloc[i]

            if any(pd.isna([curr['bb_upper'], curr['bb_lower'], curr['bw_rolling_min']])):
                continue

            is_squeeze = curr['bb_bandwidth'] <= curr['bw_rolling_min'] * 1.05  # within 5% of 6m low

            if is_squeeze and curr['Close'] > curr['bb_upper']:
                sl = curr['bb_mid']
                rr = curr['Close'] - sl
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] + 2 * rr

            elif is_squeeze and curr['Close'] < curr['bb_lower']:
                sl = curr['bb_mid']
                rr = sl - curr['Close']
                df.iloc[i, df.columns.get_loc('signal')] = -1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = curr['Close'] - 2 * rr

        return df
