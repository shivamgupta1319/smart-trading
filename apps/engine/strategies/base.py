"""Abstract base class for all trading strategies."""
from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    name: str
    timeframe: str

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes a DataFrame with OHLCV columns and returns the same DataFrame
        with additional columns: 'signal' (1=BUY, -1=SELL, 0=HOLD),
        'stop_loss', 'target'.
        """
        pass

    def run_backtest(self, df: pd.DataFrame) -> dict:
        """Run the strategy and compute backtest metrics with a running bankroll."""
        df = df.copy()
        df = self.generate_signals(df)

        trades = []
        in_trade = False
        entry_price = 0.0
        sl = 0.0
        tp = 0.0
        trade_type = 0
        
        initial_capital = 100000.0
        current_capital = initial_capital
        max_position_size = 100000.0
        
        peak = initial_capital
        max_dd = 0.0

        for i, row in df.iterrows():
            if current_capital <= 0:
                break # Bankrupt

            if not in_trade and row.get('signal', 0) != 0:
                in_trade = True
                entry_price = row['Close']
                sl = row.get('stop_loss', entry_price * 0.98)
                tp = row.get('target', entry_price * 1.04)
                trade_type = row['signal']
                invested_amount = min(current_capital, max_position_size)
            elif in_trade:
                close = row['Close']
                hit_sl = (trade_type == 1 and close <= sl) or (trade_type == -1 and close >= sl)
                hit_tp = (trade_type == 1 and close >= tp) or (trade_type == -1 and close <= tp)
                if hit_sl or hit_tp:
                    shares = invested_amount / entry_price
                    exit_price = tp if hit_tp else sl
                    
                    if trade_type == 1:
                        pnl_rs = (exit_price - entry_price) * shares
                    else:
                        pnl_rs = (entry_price - exit_price) * shares
                        
                    trades.append(pnl_rs)
                    current_capital += pnl_rs
                    in_trade = False

                    # Update equity curve
                    if current_capital > peak:
                        peak = current_capital
                    dd = peak - current_capital
                    if dd > max_dd:
                        max_dd = dd

        if not trades:
            return {'winRate': 0.0, 'totalTrades': 0, 'netProfit': 0.0, 'maxDrawdown': 0.0, 'roiPercentage': 0.0}

        wins = [t for t in trades if t > 0]
        win_rate = len(wins) / len(trades) * 100

        net_profit = current_capital - initial_capital
        roi_percentage = (net_profit / initial_capital) * 100

        return {
            'winRate': round(win_rate, 2),
            'totalTrades': len(trades),
            'netProfit': round(net_profit, 2),
            'maxDrawdown': round(max_dd, 2),
            'roiPercentage': round(roi_percentage, 2),
        }
