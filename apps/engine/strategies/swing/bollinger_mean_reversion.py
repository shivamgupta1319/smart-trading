"""Strategy 12: Bollinger Bands Mean Reversion"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy


class BollingerMeanReversionStrategy(BaseStrategy):
    name = "Bollinger_Mean_Reversion"
    timeframe = "1D"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Bollinger Bands (20, 2)
        bbands = ta.bbands(df['Close'], length=20, std=2)
        if bbands is not None:
            df['bb_lower'] = bbands['BBL_20_2.0_2.0']
            df['bb_middle'] = bbands['BBM_20_2.0_2.0']
            df['bb_upper'] = bbands['BBU_20_2.0_2.0']
        else:
            df['bb_lower'] = pd.NA
            df['bb_middle'] = pd.NA
            df['bb_upper'] = pd.NA
            
        df['rsi14'] = ta.rsi(df['Close'], length=14)
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            curr = df.iloc[i]

            if any(pd.isna([curr['bb_lower'], curr['bb_upper'], curr['rsi14'], curr['atr']])):
                continue

            # Bullish Mean Reversion: Price drops below lower band, RSI is oversold
            if curr['Close'] < curr['bb_lower'] and curr['rsi14'] < 30:
                sl = curr['Close'] - 1.5 * curr['atr']
                target = curr['bb_middle'] # Target the mean
                
                # Only take trades with positive risk reward
                if (target - curr['Close']) > (curr['Close'] - sl):
                    df.iloc[i, df.columns.get_loc('signal')] = 1
                    df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                    df.iloc[i, df.columns.get_loc('target')] = target
            
            # Bearish Mean Reversion: Price jumps above upper band, RSI is overbought
            elif curr['Close'] > curr['bb_upper'] and curr['rsi14'] > 70:
                sl = curr['Close'] + 1.5 * curr['atr']
                target = curr['bb_middle']
                
                if (curr['Close'] - target) > (sl - curr['Close']):
                    df.iloc[i, df.columns.get_loc('signal')] = -1
                    df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                    df.iloc[i, df.columns.get_loc('target')] = target

        return df
