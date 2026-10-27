"""Strategy 3: 9/15 EMA Crossover + RSI Filter"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class EMARSIStrategy(BaseStrategy):
    name = "EMA_RSI"
    timeframe = "5m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df['ema9'] = ta.ema(df['Close'], length=9)
        df['ema15'] = ta.ema(df['Close'], length=15)
        df['rsi14'] = ta.rsi(df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_ema9 = df['ema9'].shift(1)
        prev_ema15 = df['ema15'].shift(1)
        
        # Bullish crossover: 9 EMA crosses above 15 EMA AND RSI > 50
        ema_cross_up = (prev_ema9 <= prev_ema15) & (df['ema9'] > df['ema15'])
        bullish_cond = ema_cross_up & (df['rsi14'] > 50)
        
        # Bearish crossover: 9 EMA crosses below 15 EMA AND RSI < 50
        ema_cross_down = (prev_ema9 >= prev_ema15) & (df['ema9'] < df['ema15'])
        bearish_cond = ema_cross_down & (df['rsi14'] < 50)
        
        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bearish_cond, 'signal'] = -1
        
        swing_low = df['Low'].rolling(window=5).min().shift(1)
        swing_high = df['High'].rolling(window=5).max().shift(1)
        
        df.loc[bullish_cond, 'stop_loss'] = swing_low[bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + 2 * (df['Close'][bullish_cond] - swing_low[bullish_cond])
        
        df.loc[bearish_cond, 'stop_loss'] = swing_high[bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - 2 * (swing_high[bearish_cond] - df['Close'][bearish_cond])

        return df
