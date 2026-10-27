import pandas as pd
import numpy as np
from strategies.base import BaseStrategy

class VolumeProfilePOCStrategy(BaseStrategy):
    """
    Volume Profile / POC Rejection Strategy
    Timeframe: 15m
    Logic:
    - Calculates a rolling N-period Point of Control (POC), which is the price level with the most volume.
    - Trades bounces off the POC.
    - Long when price retraces to POC from above and prints a bullish reversal candle.
    - Short when price retraces to POC from below and prints a bearish reversal candle.
    """
    name = "Volume_Profile_POC"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 50:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        # Calculating exact Volume Profile in pandas without loop is tricky.
        # We will approximate POC using the typical price weighted by volume rolling.
        # Wait, a true POC approximation: 
        # Price * Volume smoothed, or just use the price of the candle with the maximum volume in the last N periods.
        # The price level of the max volume candle is a strong S/R level.
        df['Max_Vol_50'] = df['Volume'].rolling(window=50).max()
        
        # We want the typical price of the candle that had Max_Vol_50
        # Create a condition where Vol == Max_Vol
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        
        # Where volume == max volume, save the typical price, else NaN
        df['POC_Candidate'] = np.where(df['Volume'] == df['Max_Vol_50'], df['Typical_Price'], np.nan)
        
        # Forward fill the POC Candidate
        df['POC'] = df['POC_Candidate'].ffill().shift(1)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        if 'POC' not in df.columns:
            return df

        # Bullish: Price is above POC, pulls back to it (Low <= POC * 1.002), and closes above Open
        above_poc = df['Close'].shift(1) > df['POC']
        touch_poc_bull = (df['Low'] <= df['POC'] * 1.002) & (df['Low'] >= df['POC'] * 0.998)
        bullish_candle = df['Close'] > df['Open']
        
        bullish_cond = above_poc & touch_poc_bull & bullish_candle

        # Bearish: Price is below POC, pulls back to it (High >= POC * 0.998), and closes below Open
        below_poc = df['Close'].shift(1) < df['POC']
        touch_poc_bear = (df['High'] >= df['POC'] * 0.998) & (df['High'] <= df['POC'] * 1.002)
        bearish_candle = df['Close'] < df['Open']

        bearish_cond = below_poc & touch_poc_bear & bearish_candle

        # Edge trigger
        prev_bullish = bullish_cond.shift(1, fill_value=False)
        valid_bull = bullish_cond & ~prev_bullish
        
        prev_bearish = bearish_cond.shift(1, fill_value=False)
        valid_bear = bearish_cond & ~prev_bearish

        sl_bull = df['POC'] * 0.995
        sl_bear = df['POC'] * 1.005

        df.loc[valid_bull, 'signal'] = 1
        df.loc[valid_bull, 'stop_loss'] = sl_bull[valid_bull]
        df.loc[valid_bull, 'target'] = df['Close'][valid_bull] + (df['Close'][valid_bull] - sl_bull[valid_bull]) * 2

        df.loc[valid_bear, 'signal'] = -1
        df.loc[valid_bear, 'stop_loss'] = sl_bear[valid_bear]
        df.loc[valid_bear, 'target'] = df['Close'][valid_bear] - (sl_bear[valid_bear] - df['Close'][valid_bear]) * 2

        df.drop(columns=['Max_Vol_50', 'Typical_Price', 'POC_Candidate', 'POC'], inplace=True, errors='ignore')

        return df
