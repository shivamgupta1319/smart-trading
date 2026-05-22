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
        df.index = pd.to_datetime(df.index)
        df['date'] = df.index.date
        df['vwap'] = 0.0
        for date, grp in df.groupby('date'):
            typical = (grp['High'] + grp['Low'] + grp['Close']) / 3
            cum_vol = grp['Volume'].cumsum()
            cum_tpv = (typical * grp['Volume']).cumsum()
            df.loc[grp.index, 'vwap'] = cum_tpv / cum_vol.replace(0, 1)

        # Supertrend(10, 3)
        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        # pandas-ta returns columns like SUPERT_10_3.0, SUPERTd_10_3.0
        st_col = [c for c in st.columns if c.startswith('SUPERT_') and not 'd_' in c]
        std_col = [c for c in st.columns if 'SUPERTd' in c]
        if not st_col or not std_col:
            df['signal'] = 0
            df['stop_loss'] = 0.0
            df['target'] = 0.0
            return df

        df['supertrend'] = st[st_col[0]].values
        df['st_direction'] = st[std_col[0]].values  # 1 = uptrend, -1 = downtrend

        df['signal'] = 0
        df['stop_loss'] = 0.0
        df['target'] = 0.0

        for i in range(1, len(df)):
            row = df.iloc[i]
            if row['Close'] > row['vwap'] and row['st_direction'] == 1:
                sl = row['supertrend']
                rr = row['Close'] - sl
                df.iloc[i, df.columns.get_loc('signal')] = 1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = row['Close'] + 2 * rr
            elif row['Close'] < row['vwap'] and row['st_direction'] == -1:
                sl = row['supertrend']
                rr = sl - row['Close']
                df.iloc[i, df.columns.get_loc('signal')] = -1
                df.iloc[i, df.columns.get_loc('stop_loss')] = sl
                df.iloc[i, df.columns.get_loc('target')] = row['Close'] - 2 * rr

        return df
