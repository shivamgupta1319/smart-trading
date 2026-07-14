import pandas as pd
import numpy as np
import time
import pandas_ta as ta

df = pd.DataFrame(np.random.randn(1000, 5), columns=["Open", "High", "Low", "Close", "Volume"])
df['ema9'] = ta.ema(df['Close'], length=9)
df['ema15'] = ta.ema(df['Close'], length=15)
df['rsi14'] = ta.rsi(df['Close'], length=14)
df['signal'] = 0
df['stop_loss'] = 0.0
df['target'] = 0.0

start = time.time()

# Bullish
prev_ema9 = df['ema9'].shift(1)
prev_ema15 = df['ema15'].shift(1)
ema_cross_up = (prev_ema9 <= prev_ema15) & (df['ema9'] > df['ema15'])
bull_cond = ema_cross_up & (df['rsi14'] > 50)

# Bearish
ema_cross_down = (prev_ema9 >= prev_ema15) & (df['ema9'] < df['ema15'])
bear_cond = ema_cross_down & (df['rsi14'] < 50)

df.loc[bull_cond, 'signal'] = 1
df.loc[bear_cond, 'signal'] = -1

# For stop loss/target, it's a bit tricky because of 5-bar swing.
# Rolling min/max
df['swing_low'] = df['Low'].rolling(window=5).min().shift(1)
df['swing_high'] = df['High'].rolling(window=5).max().shift(1)

df.loc[bull_cond, 'stop_loss'] = df['swing_low']
df.loc[bull_cond, 'target'] = df['Close'] + 2 * (df['Close'] - df['swing_low'])

df.loc[bear_cond, 'stop_loss'] = df['swing_high']
df.loc[bear_cond, 'target'] = df['Close'] - 2 * (df['swing_high'] - df['Close'])

print(f"Vectorized generate_signals: {time.time()-start:.4f}s")
