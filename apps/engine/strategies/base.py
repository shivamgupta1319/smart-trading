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
        """Run the strategy and compute backtest metrics."""
        df = df.copy()
        df = self.generate_signals(df)

        trades = []
        in_trade = False
        entry_price = 0.0
        sl = 0.0
        tp = 0.0
        trade_type = 0

        for i, row in df.iterrows():
            if not in_trade and row.get('signal', 0) != 0:
                in_trade = True
                entry_price = row['Close']
                sl = row.get('stop_loss', entry_price * 0.98)
                tp = row.get('target', entry_price * 1.04)
                trade_type = row['signal']
            elif in_trade:
                close = row['Close']
                hit_sl = (trade_type == 1 and close <= sl) or (trade_type == -1 and close >= sl)
                hit_tp = (trade_type == 1 and close >= tp) or (trade_type == -1 and close <= tp)
                if hit_sl or hit_tp:
                    pnl = (tp - entry_price) if hit_tp else (sl - entry_price)
                    if trade_type == -1:
                        pnl = -pnl
                    trades.append(pnl)
                    in_trade = False

        if not trades:
            return {'winRate': 0.0, 'totalTrades': 0, 'maxDrawdown': 0.0, 'expectancy': 0.0}

        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t <= 0]
        win_rate = len(wins) / len(trades) * 100

        # Equity curve for max drawdown
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            equity += t
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0
        expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

        return {
            'winRate': round(win_rate, 2),
            'totalTrades': len(trades),
            'maxDrawdown': round(max_dd, 2),
            'expectancy': round(expectancy, 2),
        }
