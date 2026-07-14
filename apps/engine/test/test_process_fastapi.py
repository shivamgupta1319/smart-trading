import pandas as pd
import numpy as np
import time
from concurrent.futures import ProcessPoolExecutor
import sys
sys.path.append("/home/shivam/workspace/smart-trading/apps/engine")
from strategies import STRATEGY_REGISTRY
from strategies.intraday.ema_rsi import EMARSIStrategy

# Pre-instantiate to avoid lookup issues
def process_stock(args):
    sym, df = args
    if df.empty or len(df) < 30:
        return None
    strategy = EMARSIStrategy()
    metrics = strategy.run_backtest(df)
    return {"symbol": sym, "metrics": metrics}

if __name__ == "__main__":
    dfs = [(f"SYM{i}", pd.DataFrame(np.random.randn(1000, 5), columns=["Open", "High", "Low", "Close", "Volume"])) for i in range(500)]
    start = time.time()
    with ProcessPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(process_stock, dfs))
    print(f"Parallel 500 processed: {time.time()-start:.2f}s")
