import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class EMA20PullbackStrategy(BaseStrategy):
    """
    Pullback to the 20 EMA Strategy
    Timeframe: 5m
    Logic:
    - Long: Strong uptrend (Price > 50 EMA), price pulls back to touch 20 EMA, 
      volume is lower than average, prints a bullish reversal candle.
    """
    name = "EMA20_Pullback"
    timeframe = "5m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 50:
            return df

        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            close = df['Close'].iloc[i]
            open_p = df['Open'].iloc[i]
            low = df['Low'].iloc[i]
            high = df['High'].iloc[i]
            vol = df['Volume'].iloc[i]
            
            ema20 = df['EMA_20'].iloc[i]
            ema50 = df['EMA_50'].iloc[i]
            vol_sma = df['Vol_SMA'].iloc[i]

            if pd.isna(ema50):
                continue

            # Uptrend: 20 EMA > 50 EMA and previous closes were above 20 EMA
            # Pullback: Low touches or drops below 20 EMA, but Close is above Open (Bullish candle)
            if ema20 > ema50 and low <= ema20 and close > open_p:
                # Lower than average volume on the pullback candle is ideal, or just normal
                if vol < vol_sma * 1.5: # Not massive volume spike on the red/pullback candles
                    df.at[df.index[i], 'signal'] = 1
                    df.at[df.index[i], 'stop_loss'] = low - (close * 0.002) # Small 0.2% stop below wick
                    df.at[df.index[i], 'target'] = close + (close - df.at[df.index[i], 'stop_loss']) * 2

            # Downtrend: 20 EMA < 50 EMA
            elif ema20 < ema50 and high >= ema20 and close < open_p:
                if vol < vol_sma * 1.5:
                    df.at[df.index[i], 'signal'] = -1
                    df.at[df.index[i], 'stop_loss'] = high + (close * 0.002)
                    df.at[df.index[i], 'target'] = close - (df.at[df.index[i], 'stop_loss'] - close) * 2

        return df
