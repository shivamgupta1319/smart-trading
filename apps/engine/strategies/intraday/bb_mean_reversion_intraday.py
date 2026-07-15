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
        df = df.copy()
        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0
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

        # Long Setup: pierces lower band but closes back inside (bullish). The
        # close must still sit BELOW the mid band, otherwise the target (BBM)
        # would be below entry and the trade gets skipped for invalid geometry.
        bullish_cond = (
            (df['Low'] < df['BBL']) & (df['Close'] > df['BBL'])
            & (df['Close'] > df['Open']) & (df['Close'] < df['BBM'])
        )

        # Short Setup: pierces upper band but closes back inside (bearish), with
        # the close still ABOVE the mid band so the target (BBM) sits below entry.
        bearish_cond = (
            (df['High'] > df['BBU']) & (df['Close'] < df['BBU'])
            & (df['Close'] < df['Open']) & (df['Close'] > df['BBM'])
        )

        # Edge-trigger: fire only on the bar the setup first appears.
        bullish_cond = bullish_cond & ~bullish_cond.shift(1, fill_value=False)
        bearish_cond = bearish_cond & ~bearish_cond.shift(1, fill_value=False)

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = df['Low'][bullish_cond] - (df['Close'][bullish_cond] * 0.002)
        df.loc[bullish_cond, 'target'] = df['BBM'][bullish_cond]

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = df['High'][bearish_cond] + (df['Close'][bearish_cond] * 0.002)
        df.loc[bearish_cond, 'target'] = df['BBM'][bearish_cond]

        return df
