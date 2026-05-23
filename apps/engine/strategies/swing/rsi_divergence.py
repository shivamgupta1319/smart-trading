"""Strategy 9: RSI Divergence (Bullish)"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class RSIDivergenceStrategy(BaseStrategy):
    name = "RSI_Divergence"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['rsi14'] = ta.rsi(df['Close'], length=14)
        df['ema50'] = ta.ema(df['Close'], length=50)
        df['atr14'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        df['Low_200'] = df['Low'].rolling(window=200).min().shift(1)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        lookback = 20  # bars to look for divergence

        for i in range(lookback + 1, len(df)):
            curr = df.iloc[i]
            window = df.iloc[i - lookback:i]

            if pd.isna(curr['rsi14']) or pd.isna(curr['ema50']) or pd.isna(curr['atr14']) or pd.isna(curr['Low_200']):
                continue

            # Find two lows in the window
            price_lows = window['Low'].nsmallest(2).index
            if len(price_lows) < 2:
                continue

            idx1 = min(price_lows)
            idx2 = max(price_lows)

            price_low1 = df.loc[idx1, 'Low']
            price_low2 = df.loc[idx2, 'Low']
            rsi_low1 = df.loc[idx1, 'rsi14']
            rsi_low2 = df.loc[idx2, 'rsi14']

            if any(pd.isna([rsi_low1, rsi_low2])):
                continue

            # Bullish divergence: price lower low + RSI higher low
            price_lower_low = price_low2 < price_low1
            rsi_higher_low = rsi_low2 > rsi_low1
            
            # Major Support: Price is within 5% of the 200-day low
            at_major_support = curr['Low'] <= curr['Low_200'] * 1.05

            if price_lower_low and rsi_higher_low and at_major_support:
                # Entry: first green candle after divergence
                if curr['Close'] > curr['Open']:
                    sl = curr['Close'] - 2 * curr['atr14']
                    rr = curr['Close'] - sl
                    target = curr['Close'] + 2 * rr
                    df.iloc[i, df.columns.get_loc('signal')] = 1
                    df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                    df.iloc[i, df.columns.get_loc('target')] = target

        return df
