import pandas as pd
import numpy as np
from strategies.base import BaseStrategy

class SMCFVGStrategy(BaseStrategy):
    """
    Smart Money Concepts - Fair Value Gap (FVG) Strategy
    Timeframe: 15m
    Logic:
    - Identifies Bullish FVG (Candle 1 High < Candle 3 Low) and Bearish FVG (Candle 1 Low > Candle 3 High).
    - Stores the most recent FVG.
    - Enters long when price retraces into the Bullish FVG and bounces (closes above the FVG low).
    - Enters short when price retraces into the Bearish FVG and rejects (closes below the FVG high).
    """
    name = "SMC_FVG"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 5:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        closes = df['Close'].values
        highs = df['High'].values
        lows = df['Low'].values

        signals = np.zeros(len(df))
        stop_losses = np.zeros(len(df))
        targets = np.zeros(len(df))

        active_bull_fvg_top = 0
        active_bull_fvg_bottom = 0

        active_bear_fvg_top = 0
        active_bear_fvg_bottom = 0

        for i in range(2, len(df)):
            c1_high = highs[i-2]
            c1_low = lows[i-2]
            c3_high = highs[i]
            c3_low = lows[i]
            c2_close = closes[i-1]
            c2_open = df['Open'].iloc[i-1]

            # FVG formation is confirmed on candle 3 close
            is_bull_fvg = (c1_high < c3_low) and (c2_close > c2_open) # Big green candle in middle
            is_bear_fvg = (c1_low > c3_high) and (c2_close < c2_open) # Big red candle in middle

            if is_bull_fvg:
                active_bull_fvg_top = c3_low
                active_bull_fvg_bottom = c1_high
                active_bear_fvg_top = 0 # Invalidate opposite

            if is_bear_fvg:
                active_bear_fvg_top = c1_low
                active_bear_fvg_bottom = c3_high
                active_bull_fvg_top = 0

            # Signal Generation (Retracement into FVG)
            curr_close = closes[i]
            curr_low = lows[i]
            curr_high = highs[i]

            if active_bull_fvg_top > 0:
                # If price drops into FVG and closes above the bottom
                if curr_low <= active_bull_fvg_top and curr_close > active_bull_fvg_bottom:
                    signals[i] = 1
                    sl = active_bull_fvg_bottom * 0.998 # Slightly below FVG
                    stop_losses[i] = sl
                    targets[i] = curr_close + (curr_close - sl) * 2
                    active_bull_fvg_top = 0 # Mark as mitigated

                # Invalidate if closes below FVG
                elif curr_close < active_bull_fvg_bottom:
                    active_bull_fvg_top = 0

            if active_bear_fvg_top > 0:
                # If price rises into FVG and closes below top
                if curr_high >= active_bear_fvg_bottom and curr_close < active_bear_fvg_top:
                    signals[i] = -1
                    sl = active_bear_fvg_top * 1.002
                    stop_losses[i] = sl
                    targets[i] = curr_close - (sl - curr_close) * 2
                    active_bear_fvg_top = 0 # Mark as mitigated
                    
                # Invalidate if closes above FVG
                elif curr_close > active_bear_fvg_top:
                    active_bear_fvg_top = 0

        df['signal'] = signals
        df['stop_loss'] = stop_losses
        df['target'] = targets

        return df
