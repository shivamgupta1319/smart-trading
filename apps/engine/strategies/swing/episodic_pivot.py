import pandas as pd
import numpy as np
from strategies.base import BaseStrategy

class EpisodicPivotStrategy(BaseStrategy):
    """
    Episodic Pivots (Earnings/Catalyst Gaps) Strategy
    Timeframe: 1D
    Logic:
    - Massive gap up (>5%).
    - Consolidation for 3-5 days (price doesn't fill the gap).
    - Breakout above the consolidation high.
    """
    name = "Episodic_Pivot"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 10:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0
        
        df['Prev_Close'] = df['Close'].shift(1)
        df['Gap_Pct'] = (df['Open'] - df['Prev_Close']) / df['Prev_Close']
        
        gap_threshold = 0.05
        
        closes = df['Close'].values
        opens = df['Open'].values
        highs = df['High'].values
        lows = df['Low'].values
        gap_pcts = df['Gap_Pct'].values
        prev_closes = df['Prev_Close'].values

        signals = np.zeros(len(df))
        stop_losses = np.zeros(len(df))
        targets = np.zeros(len(df))

        active_gap_idx = -1
        consolidation_high = 0
        consolidation_low = 0
        
        for i in range(1, len(df)):
            gap_pct = gap_pcts[i]
            high = highs[i]
            low = lows[i]
            close = closes[i]
            
            # 1. Detect new gap
            if gap_pct > gap_threshold:
                active_gap_idx = i
                consolidation_high = high
                consolidation_low = low
                continue
                
            # If we have an active gap, check consolidation
            if active_gap_idx != -1:
                days_since_gap = i - active_gap_idx
                
                # Update consolidation high
                if high > consolidation_high:
                    consolidation_high = high
                    
                # If gap is filled (price drops below the gap day's low), invalidate
                if close < consolidation_low:
                    active_gap_idx = -1
                    continue
                    
                # 2. Wait 3-5 days for consolidation, then look for breakout
                if 3 <= days_since_gap <= 8:
                    # Breakout above consolidation high
                    if close > consolidation_high and closes[i-1] <= consolidation_high:
                        signals[i] = 1
                        # Stop loss at the bottom of the gap day or a 5% stop
                        sl = max(consolidation_low, close * 0.95)
                        stop_losses[i] = sl
                        targets[i] = close + (close - sl) * 3
                        # Reset
                        active_gap_idx = -1
                
                # If too many days pass, invalidate
                elif days_since_gap > 8:
                    active_gap_idx = -1

        df['signal'] = signals
        df['stop_loss'] = stop_losses
        df['target'] = targets
        return df
