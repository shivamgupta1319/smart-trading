import pandas as pd
import numpy as np
import time
from concurrent.futures import ProcessPoolExecutor
import sys
sys.path.append("/home/shivam/workspace/smart-trading/apps/engine")
from strategies import STRATEGY_REGISTRY

def run_strategy(args):
    strategy_name, symbol, df = args
    if len(df) < 30:
        return None
    strategy = STRATEGY_REGISTRY[strategy_name]
    metrics = strategy.run_backtest(df)
    return {"symbol": symbol, "metrics": metrics}

if __name__ == "__main__":
    dfs = [( "EMA_RSI", f"SYM{i}", pd.DataFrame(np.random.randn(1000, 5), columns=["Open", "High", "Low", "Close", "Volume"]) ) for i in range(500)]
    start = time.time()
    with ProcessPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(run_strategy, dfs))
    print(f"Parallel 500 stocks: {time.time()-start:.2f}s")
