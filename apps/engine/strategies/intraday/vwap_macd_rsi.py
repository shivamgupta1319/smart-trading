import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class VWAPMACDRSIStrategy(BaseStrategy):
    """
    VWAP + MACD/RSI Confluence Strategy
    Timeframe: 15m
    Logic:
    - Long: Price > VWAP, RSI > 60, MACD crosses bullishly (or is positive)
    - Short: Price < VWAP, RSI < 40, MACD crosses bearishly (or is negative)
    """
    name = "VWAP_MACD_RSI"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.empty or len(df) < 50:
            return df

        # Calculate VWAP
        df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])
        
        # Calculate RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # Calculate MACD
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd is None or macd.empty:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        macd_col = [c for c in macd.columns if c.startswith('MACD_')][0]
        hist_col = [c for c in macd.columns if c.startswith('MACDh_')][0]
        signal_col = [c for c in macd.columns if c.startswith('MACDs_')][0]
        
        df['MACD'] = macd[macd_col]
        df['MACD_Hist'] = macd[hist_col]
        df['MACD_Signal'] = macd[signal_col]

        # Generate signals
        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        prev_macd_hist = df['MACD_Hist'].shift(1)

        # Long conditions
        bullish_cond = (df['Close'] > df['VWAP']) & (df['RSI'] > 60) & (df['MACD_Hist'] > 0) & (prev_macd_hist <= 0)

        # Short conditions
        bearish_cond = (df['Close'] < df['VWAP']) & (df['RSI'] < 40) & (df['MACD_Hist'] < 0) & (prev_macd_hist >= 0)

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = df['Low'][bullish_cond] - (df['Close'][bullish_cond] * 0.005)
        sl_diff_bull = df['Close'][bullish_cond] - df.loc[bullish_cond, 'stop_loss']
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + sl_diff_bull * 2

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = df['High'][bearish_cond] + (df['Close'][bearish_cond] * 0.005)
        sl_diff_bear = df.loc[bearish_cond, 'stop_loss'] - df['Close'][bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - sl_diff_bear * 2

        return df
