import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class BollingerMeanReversionStrategy(BaseStrategy):
    """Strategy 12: Bollinger Bands Mean Reversion"""
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
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df
            
        df['rsi14'] = ta.rsi(df['Close'], length=14)
        df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        cond_long = (df['Close'] < df['bb_lower']) & (df['rsi14'] < 30)
        cond_short = (df['Close'] > df['bb_upper']) & (df['rsi14'] > 70)

        prev_long = cond_long.shift(1, fill_value=False)
        prev_short = cond_short.shift(1, fill_value=False)

        bullish_cond = cond_long & ~prev_long
        bearish_cond = cond_short & ~prev_short

        sl_bull = df['Close'] - 1.5 * df['atr']
        target_bull = df['bb_middle']
        valid_bull = bullish_cond & ((target_bull - df['Close']) > (df['Close'] - sl_bull))

        sl_bear = df['Close'] + 1.5 * df['atr']
        target_bear = df['bb_middle']
        valid_bear = bearish_cond & ((df['Close'] - target_bear) > (sl_bear - df['Close']))

        df.loc[valid_bull, 'signal'] = 1
        df.loc[valid_bull, 'stop_loss'] = sl_bull[valid_bull]
        df.loc[valid_bull, 'target'] = target_bull[valid_bull]

        df.loc[valid_bear, 'signal'] = -1
        df.loc[valid_bear, 'stop_loss'] = sl_bear[valid_bear]
        df.loc[valid_bear, 'target'] = target_bear[valid_bear]

        return df
