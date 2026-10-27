import pandas as pd
import pandas_ta as ta
import numpy as np
from strategies.base import BaseStrategy

class RSIDivergenceStrategy(BaseStrategy):
    """Strategy 9: RSI Divergence (Bullish)"""
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

        closes = df['Close'].values
        opens = df['Open'].values
        lows = df['Low'].values
        rsi14s = df['rsi14'].values
        ema50s = df['ema50'].values
        atr14s = df['atr14'].values
        low_200s = df['Low_200'].values

        signals = np.zeros(len(df))
        stop_losses = np.zeros(len(df))
        targets = np.zeros(len(df))

        for i in range(lookback + 1, len(df)):
            curr_rsi = rsi14s[i]
            curr_ema50 = ema50s[i]
            curr_atr = atr14s[i]
            curr_low_200 = low_200s[i]
            curr_low = lows[i]
            curr_close = closes[i]
            curr_open = opens[i]

            if np.isnan(curr_rsi) or np.isnan(curr_ema50) or np.isnan(curr_atr) or np.isnan(curr_low_200):
                continue

            window_lows = lows[i - lookback:i]
            window_rsis = rsi14s[i - lookback:i]

            if len(window_lows) < 2:
                continue
            
            sorted_indices = np.argsort(window_lows)
            idx1 = min(sorted_indices[0], sorted_indices[1])
            idx2 = max(sorted_indices[0], sorted_indices[1])

            price_low1 = window_lows[idx1]
            price_low2 = window_lows[idx2]
            rsi_low1 = window_rsis[idx1]
            rsi_low2 = window_rsis[idx2]

            if np.isnan(rsi_low1) or np.isnan(rsi_low2):
                continue

            # Bullish divergence: price lower low + RSI higher low
            price_lower_low = price_low2 < price_low1
            rsi_higher_low = rsi_low2 > rsi_low1
            
            # Major Support: Price is within 5% of the 200-day low
            at_major_support = curr_low <= curr_low_200 * 1.05

            if price_lower_low and rsi_higher_low and at_major_support:
                # Entry: first green candle after divergence
                if curr_close > curr_open:
                    sl = curr_close - 2 * curr_atr
                    rr = curr_close - sl
                    target = curr_close + 2 * rr
                    signals[i] = 1
                    stop_losses[i] = sl
                    targets[i] = target

        df['signal'] = signals
        df['stop_loss'] = stop_losses
        df['target'] = targets

        return df
