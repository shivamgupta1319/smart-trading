"""Strategy 2: VWAP + Supertrend (10, 3)"""
import pandas as pd
import pandas_ta as ta
from strategies.base import BaseStrategy

class VWAPSupertrendStrategy(BaseStrategy):
    name = "VWAP_Supertrend"
    timeframe = "15m"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # Compute VWAP (cumulative intraday, reset by date)
        if not pd.api.types.is_datetime64_any_dtype(df.index):
            df.index = pd.to_datetime(df.index)
        df['date'] = df.index.date
        
        # Vectorized VWAP
        typical = (df['High'] + df['Low'] + df['Close']) / 3
        tpv = typical * df['Volume']
        
        cum_vol = df.groupby('date')['Volume'].cumsum()
        tpv_series = pd.Series(tpv, index=df.index)
        cum_tpv = tpv_series.groupby(df['date']).cumsum()
        df['vwap'] = cum_tpv / cum_vol.replace(0, 1)

        # Supertrend(10, 3)
        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        if st is None or st.empty:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        st_col = [c for c in st.columns if c.startswith('SUPERT_') and not 'd_' in c]
        std_col = [c for c in st.columns if 'SUPERTd' in c]

        df['supertrend'] = st[st_col[0]].values
        df['st_direction'] = st[std_col[0]].values  # 1 = uptrend, -1 = downtrend

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        # Edge-triggered logic: we want the signal only when the condition BECOMES true
        # So we check if condition is true NOW, and was false PREVIOUSLY
        cond_long = (df['Close'] > df['vwap']) & (df['st_direction'] == 1)
        cond_short = (df['Close'] < df['vwap']) & (df['st_direction'] == -1)
        
        prev_cond_long = cond_long.shift(1, fill_value=False)
        prev_cond_short = cond_short.shift(1, fill_value=False)

        bullish_cond = cond_long & ~prev_cond_long
        bearish_cond = cond_short & ~prev_cond_short

        df.loc[bullish_cond, 'signal'] = 1
        df.loc[bullish_cond, 'stop_loss'] = df['supertrend'][bullish_cond]
        df.loc[bullish_cond, 'target'] = df['Close'][bullish_cond] + 2 * (df['Close'][bullish_cond] - df['supertrend'][bullish_cond])

        df.loc[bearish_cond, 'signal'] = -1
        df.loc[bearish_cond, 'stop_loss'] = df['supertrend'][bearish_cond]
        df.loc[bearish_cond, 'target'] = df['Close'][bearish_cond] - 2 * (df['supertrend'][bearish_cond] - df['Close'][bearish_cond])

        df.drop(columns=['date'], inplace=True)
        return df
