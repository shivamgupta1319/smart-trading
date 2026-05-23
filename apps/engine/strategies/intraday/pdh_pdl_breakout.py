import pandas as pd
from strategies.base import BaseStrategy

class PDHPDLBreakoutStrategy(BaseStrategy):
    """
    Previous Day High/Low (PDH/PDL) Breakout Strategy
    Timeframe: 5m
    Logic:
    - Calculates PDH and PDL.
    - Long if price breaks above PDH.
    - Short if price breaks below PDL.
    """
    name = "PDH_PDL_Breakout"
    timeframe = "5m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 10:
            return df

        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)

        df['Date'] = df.index.date
        
        # Calculate daily aggregates
        daily_data = df.groupby('Date').agg({
            'High': 'max',
            'Low': 'min'
        }).shift(1) # Shift 1 to get previous day's data
        
        df['PDH'] = pd.Series(index=df.index, dtype=float)
        df['PDL'] = pd.Series(index=df.index, dtype=float)
        
        for date, row in daily_data.iterrows():
            mask = df['Date'] == date
            df.loc[mask, 'PDH'] = row['High']
            df.loc[mask, 'PDL'] = row['Low']

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            pdh = df['PDH'].iloc[i]
            pdl = df['PDL'].iloc[i]
            
            if pd.isna(pdh) or pd.isna(pdl):
                continue
                
            close = df['Close'].iloc[i]
            prev_close = df['Close'].iloc[i-1]
            low = df['Low'].iloc[i]
            high = df['High'].iloc[i]

            # Long breakout: previous close below PDH, current close above PDH
            if prev_close <= pdh and close > pdh:
                df.at[df.index[i], 'signal'] = 1
                df.at[df.index[i], 'stop_loss'] = low - (close * 0.002) # Stop below entry candle
                df.at[df.index[i], 'target'] = close + (close - df.at[df.index[i], 'stop_loss']) * 2

            # Short breakout: previous close above PDL, current close below PDL
            elif prev_close >= pdl and close < pdl:
                df.at[df.index[i], 'signal'] = -1
                df.at[df.index[i], 'stop_loss'] = high + (close * 0.002) # Stop above entry candle
                df.at[df.index[i], 'target'] = close - (df.at[df.index[i], 'stop_loss'] - close) * 2

        df.drop(columns=['Date', 'PDH', 'PDL'], inplace=True)
        return df
