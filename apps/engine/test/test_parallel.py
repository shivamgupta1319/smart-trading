import pandas as pd
import numpy as np
import time
from concurrent.futures import ProcessPoolExecutor
import sys
sys.path.append("/home/shivam/workspace/smart-trading/apps/engine")
from strategies import STRATEGY_REGISTRY

strategy = STRATEGY_REGISTRY["EMA_RSI"]

def process_stock(df):
    try:
        return strategy.run_backtest(df)
    except Exception as e:
        return None

if __name__ == "__main__":
    # Create 100 fake dataframes
    dfs = [pd.DataFrame(np.random.randn(1000, 5), columns=["Open", "High", "Low", "Close", "Volume"]) for _ in range(100)]
    
    start = time.time()
    for df in dfs:
        process_stock(df)
    print(f"Sequential: {time.time()-start:.2f}s")
    
    start = time.time()
    with ProcessPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(process_stock, dfs))
    print(f"Parallel: {time.time()-start:.2f}s")
