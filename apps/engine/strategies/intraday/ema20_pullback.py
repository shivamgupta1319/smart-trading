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
        df = df.copy()
        if df.empty or len(df) < 50:
            return df

        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        # Uptrend: 20 EMA > 50 EMA and previous closes were above 20 EMA
        # Pullback: Low touches or drops below 20 EMA, but Close is above Open (Bullish candle)
        bullish_cond = (df['EMA_20'] > df['EMA_50']) & (df['Low'] <= df['EMA_20']) & (df['Close'] > df['Open']) & (df['Volume'] < df['Vol_SMA'] * 1.5)

        # Downtrend: 20 EMA < 50 EMA
        bearish_cond = (df['EMA_20'] < df['EMA_50']) & (df['High'] >= df['EMA_20']) & (df['Close'] < df['Open']) & (df['Volume'] < df['Vol_SMA'] * 1.5)

        df.loc[bullish_cond, 'signal'] = 1
        sl_bull = df['Low'] - (df['Close'] * 0.002)
        df.loc[bullish_cond, 'stop_loss'] = sl_bull[bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + (df['Close'][bullish_cond] - sl_bull[bullish_cond]) * 2

        df.loc[bearish_cond, 'signal'] = -1
        sl_bear = df['High'] + (df['Close'] * 0.002)
        df.loc[bearish_cond, 'stop_loss'] = sl_bear[bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - (sl_bear[bearish_cond] - df['Close'][bearish_cond]) * 2

        return df
