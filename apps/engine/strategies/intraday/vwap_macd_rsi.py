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
        if df.empty or len(df) < 50:
            return df

        # Calculate VWAP
        df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])
        
        # Calculate RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # Calculate MACD
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        # Check column names output by pandas_ta
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

        for i in range(1, len(df)):
            close = df['Close'].iloc[i]
            vwap = df['VWAP'].iloc[i]
            rsi = df['RSI'].iloc[i]
            macd_hist = df['MACD_Hist'].iloc[i]
            prev_macd_hist = df['MACD_Hist'].iloc[i-1]

            # Long conditions
            if close > vwap and rsi > 60 and macd_hist > 0 and prev_macd_hist <= 0:
                df.at[df.index[i], 'signal'] = 1
                df.at[df.index[i], 'stop_loss'] = df['Low'].iloc[i] - (close * 0.005) # 0.5% SL
                df.at[df.index[i], 'target'] = close + (close - df.at[df.index[i], 'stop_loss']) * 2 # 1:2 RR

            # Short conditions
            elif close < vwap and rsi < 40 and macd_hist < 0 and prev_macd_hist >= 0:
                df.at[df.index[i], 'signal'] = -1
                df.at[df.index[i], 'stop_loss'] = df['High'].iloc[i] + (close * 0.005) # 0.5% SL
                df.at[df.index[i], 'target'] = close - (df.at[df.index[i], 'stop_loss'] - close) * 2 # 1:2 RR

        return df
