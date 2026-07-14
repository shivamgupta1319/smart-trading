import pandas as pd
import pandas_ta as ta
import numpy as np
from strategies.base import BaseStrategy

class VCPStrategy(BaseStrategy):
    """
    Volatility Contraction Pattern (VCP) Strategy
    Timeframe: 1D
    Logic:
    - Approximates VCP by looking for a period of low volatility (narrowing price range)
    - Volume drying up during the consolidation (10-day avg vol < 50-day avg vol)
    - Breakout above 20-day high on heavy volume (volume > 1.5x 50-day avg).
    """
    name = "VCP"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 50:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        # Calculate metrics
        df['Vol_10'] = ta.sma(df['Volume'], length=10)
        df['Vol_50'] = ta.sma(df['Volume'], length=50)
        
        # Volatility contraction: 20-day ATR as a percentage of price should be dropping or low
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=20)
        df['ATR_Pct'] = df['ATR'] / df['Close']
        
        # 20-day Rolling High for Breakout
        df['High_20'] = df['High'].rolling(window=20).max().shift(1)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_vol_10 = df['Vol_10'].shift(1)
        prev_vol_50 = df['Vol_50'].shift(1)
        prev_atr_pct = df['ATR_Pct'].shift(1)

        vol_dry = prev_vol_10 < prev_vol_50
        low_volatility = prev_atr_pct < 0.03
        breakout = df['Close'] > df['High_20']
        heavy_volume = df['Volume'] > (prev_vol_50 * 1.5)

        bullish_cond = vol_dry & low_volatility & breakout & heavy_volume

        # Edge trigger
        prev_bullish = bullish_cond.shift(1, fill_value=False)
        valid_bull = bullish_cond & ~prev_bullish

        sl_1 = df['Low'] - (df['Close'] * 0.01)
        sl_2 = df['Close'] * 0.95
        sl = np.maximum(sl_1, sl_2)

        df.loc[valid_bull, 'signal'] = 1
        df.loc[valid_bull, 'stop_loss'] = sl[valid_bull]
        df.loc[valid_bull, 'target'] = df['Close'][valid_bull] + (df['Close'][valid_bull] - sl[valid_bull]) * 2.5

        return df
