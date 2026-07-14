import pandas as pd
import numpy as np
from strategies.base import BaseStrategy

class BreakAndRetestStrategy(BaseStrategy):
    """
    Break and Retest Strategy
    Timeframe: 1D
    Logic:
    - Breaks a 60-day resistance level.
    - Pulls back to test the former resistance (now support).
    - Enters on the bounce (bullish candle).
    """
    name = "Break_And_Retest"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 60:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0
        
        df['High_60'] = df['High'].rolling(window=60).max().shift(1)
        
        active_breakout_level = 0
        days_since_breakout = 0
        
        # Optimize with numpy arrays
        closes = df['Close'].values
        opens = df['Open'].values
        lows = df['Low'].values
        high_60s = df['High_60'].values
        
        signals = np.zeros(len(df))
        stop_losses = np.zeros(len(df))
        targets = np.zeros(len(df))

        for i in range(60, len(df)):
            close = closes[i]
            open_p = opens[i]
            low = lows[i]
            high_60 = high_60s[i]
            
            # 1. Detect Breakout
            if close > high_60 and active_breakout_level == 0:
                active_breakout_level = high_60
                days_since_breakout = 0
                continue
                
            # If we have an active breakout
            if active_breakout_level > 0:
                days_since_breakout += 1
                
                # Invalidate if it drops significantly below the breakout level (e.g., false breakout)
                if close < active_breakout_level * 0.95:
                    active_breakout_level = 0
                    continue
                    
                # 2. Wait for Pullback to within 2% of the breakout level
                if low <= active_breakout_level * 1.02 and low >= active_breakout_level * 0.98:
                    # 3. Enter on bounce (bullish close)
                    if close > open_p:
                        signals[i] = 1
                        sl = active_breakout_level * 0.96
                        stop_losses[i] = sl
                        targets[i] = close + (close - sl) * 2
                        
                        # Reset
                        active_breakout_level = 0
                        
                # Invalidate if it takes too long to retest (e.g., > 20 days)
                elif days_since_breakout > 20:
                    active_breakout_level = 0

        df['signal'] = signals
        df['stop_loss'] = stop_losses
        df['target'] = targets
        return df
