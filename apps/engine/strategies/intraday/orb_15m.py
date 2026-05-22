"""Strategy 1: 15-Minute Opening Range Breakout (ORB)"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class ORB15mStrategy(BaseStrategy):
    name = "15m_ORB"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        # Group by date to find each day's opening range (first 15m candle)
        df.index = pd.to_datetime(df.index)
        df['date'] = df.index.date

        for date, day_df in df.groupby('date'):
            if len(day_df) < 2:
                continue

            # First candle = ORB
            orb_high = day_df.iloc[0]['High']
            orb_low = day_df.iloc[0]['Low']
            orb_mid = (orb_high + orb_low) / 2

            # Only check subsequent candles (after first 15m)
            for idx in day_df.index[1:]:
                candle = df.loc[idx]
                # Entry conditions: close above/below ORB range
                if candle['Close'] > orb_high and df.loc[idx, 'signal'] == 0:
                    sl = orb_mid
                    rr = candle['Close'] - sl
                    df.loc[idx, 'signal'] = 1
                    df.loc[idx, 'stop_loss'] = sl
                    df.loc[idx, 'target'] = candle['Close'] + 2 * rr
                    break  # One trade per day
                elif candle['Close'] < orb_low and df.loc[idx, 'signal'] == 0:
                    sl = orb_mid
                    rr = sl - candle['Close']
                    df.loc[idx, 'signal'] = -1
                    df.loc[idx, 'stop_loss'] = sl
                    df.loc[idx, 'target'] = candle['Close'] - 2 * rr
                    break

        return df
