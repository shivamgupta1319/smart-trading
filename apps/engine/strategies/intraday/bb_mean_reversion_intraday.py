import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class BBMeanReversionIntradayStrategy(BaseStrategy):
    """
    Bollinger Band Mean Reversion Strategy (Intraday)
    Timeframe: 15m
    Logic:
    - Target mid-day chop.
    - Long if price pierces lower BB and closes inside. Target: Middle Band (20 SMA).
    - Short if price pierces upper BB and closes inside. Target: Middle Band (20 SMA).
    """
    name = "BB_Mean_Reversion_Intraday"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 25:
            return df

        # Calculate Bollinger Bands (Length 20, StdDev 2)
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is None:
            return df
            
        bb_lower_col = [c for c in bb.columns if c.startswith('BBL_')][0]
        bb_mid_col = [c for c in bb.columns if c.startswith('BBM_')][0]
        bb_upper_col = [c for c in bb.columns if c.startswith('BBU_')][0]

        df['BBL'] = bb[bb_lower_col]
        df['BBM'] = bb[bb_mid_col]
        df['BBU'] = bb[bb_upper_col]

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            close = df['Close'].iloc[i]
            open_p = df['Open'].iloc[i]
            low = df['Low'].iloc[i]
            high = df['High'].iloc[i]
            
            bbl = df['BBL'].iloc[i]
            bbm = df['BBM'].iloc[i]
            bbu = df['BBU'].iloc[i]

            if pd.isna(bbl):
                continue

            # Long Setup: Pierces lower band but closes above it (and bullish)
            if low < bbl and close > bbl and close > open_p:
                df.at[df.index[i], 'signal'] = 1
                df.at[df.index[i], 'stop_loss'] = low - (close * 0.002)
                df.at[df.index[i], 'target'] = bbm # Target the midline

            # Short Setup: Pierces upper band but closes below it (and bearish)
            elif high > bbu and close < bbu and close < open_p:
                df.at[df.index[i], 'signal'] = -1
                df.at[df.index[i], 'stop_loss'] = high + (close * 0.002)
                df.at[df.index[i], 'target'] = bbm # Target the midline

        return df
