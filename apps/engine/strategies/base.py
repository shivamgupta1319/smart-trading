"""Abstract base class for all trading strategies."""
from abc import ABC, abstractmethod
import math
import numpy as np
import pandas as pd

from backtest_config import RISK, CostModel


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

    def _apply_bucket_target(self, df: pd.DataFrame) -> pd.DataFrame:
        """Override the `target` column to a bucket-specific reward:risk multiple
        (the validated R:R-by-horizon model). The STOP is left exactly as the
        strategy set it — only the reward distance changes. For buckets with no
        configured multiple (e.g. INTRADAY) the native target is kept unchanged.

        Applied in BOTH the backtest (via simulate) and live signals (via the
        scanner), so the two never diverge. Reward is measured from the signal
        bar's Close, the same reference each strategy uses for its own target.
        """
        from backtest_config import target_r_for_bucket
        try:
            from strategies import STRATEGY_HOLD_DURATIONS
            bucket = STRATEGY_HOLD_DURATIONS.get(getattr(self, "name", ""), None)
        except Exception:
            bucket = None
        r = target_r_for_bucket(bucket)
        if r is None or "signal" not in df.columns or "stop_loss" not in df.columns:
            return df

        df = df.copy()
        sig = df["signal"].to_numpy()
        close = df["Close"].to_numpy(dtype=float)
        sl = df["stop_loss"].to_numpy(dtype=float)
        tgt = (df["target"].to_numpy(dtype=float).copy()
               if "target" in df.columns else np.full(len(df), np.nan))
        long = (sig > 0) & np.isfinite(sl) & (close > sl)
        short = (sig < 0) & np.isfinite(sl) & (sl > close)
        tgt[long] = close[long] + r * (close[long] - sl[long])
        tgt[short] = close[short] - r * (sl[short] - close[short])
        df["target"] = tgt
        return df

    def run_backtest(self, df: pd.DataFrame) -> dict:
        """Run a realistic backtest and return aggregate metrics."""
        sim = self.simulate(df)
        return self._metrics(
            sim["net_trades"], sim["gross_trades"], sim["total_costs"],
            sim["max_dd"], sim["skipped_invalid"],
        )

    def simulate(self, df: pd.DataFrame) -> dict:
        """Run the realistic fill simulation and return per-trade P&L lists.

        Fill model (removes the optimistic biases of the old close-only engine):
          * Entry on the NEXT bar's open (configurable), with adverse slippage.
          * Stop-loss / target evaluated against each subsequent bar's intrabar
            High/Low — not the close. If a single bar straddles both levels we
            assume the worse (SL) filled first (pessimistic_intrabar).
          * Risk-based position sizing: size each trade so the SL distance risks
            a fixed % of capital (matches the live 2% rule), capped by no-leverage
            max position value.
          * Indian transaction costs + slippage subtracted to report NET P&L
            alongside GROSS.

        Returns {net_trades, gross_trades, total_costs, max_dd, skipped_invalid}.
        """
        df = self.generate_signals(df).copy()
        df = self._apply_bucket_target(df)  # bucket reward:risk override (R:R-by-horizon)
        tf = getattr(self, "timeframe", "1D")
        costs = CostModel(tf)

        o = df["Open"].to_numpy(dtype=float)
        h = df["High"].to_numpy(dtype=float)
        low = df["Low"].to_numpy(dtype=float)
        c = df["Close"].to_numpy(dtype=float)
        sig = df.get("signal", pd.Series(0, index=df.index)).fillna(0).to_numpy(dtype=float)
        sl_arr = df.get("stop_loss", pd.Series(np.nan, index=df.index)).to_numpy(dtype=float)
        tp_arr = df.get("target", pd.Series(np.nan, index=df.index)).to_numpy(dtype=float)

        n = len(df)
        slip = RISK.slippage_bps / 10_000.0
        # A single-cell backtest simulates ONE portfolio slot (₹10k) traded
        # repeatedly, so its P&L/ROI is comparable to one live slot rather than
        # to the whole ₹1L account.
        initial_capital = RISK.slot_capital
        risk_budget = initial_capital * RISK.risk_per_trade_pct / 100.0

        net_trades: list[float] = []
        gross_trades: list[float] = []
        total_costs = 0.0
        current_capital = initial_capital
        peak = initial_capital
        max_dd = 0.0
        skipped_invalid = 0

        i = 0
        while i < n - 1:
            if current_capital <= 0:
                break  # bankrupt
            if sig[i] == 0:
                i += 1
                continue

            ttype = 1 if sig[i] > 0 else -1
            entry_idx = i + 1 if RISK.next_bar_entry else i
            entry_raw = o[entry_idx] if RISK.next_bar_entry else c[i]
            if not math.isfinite(entry_raw) or entry_raw <= 0:
                i += 1
                continue

            # Adverse slippage on entry (buy fills higher, short fills lower)
            entry = entry_raw * (1 + slip) if ttype == 1 else entry_raw * (1 - slip)

            sl = sl_arr[i] if math.isfinite(sl_arr[i]) else entry * (0.98 if ttype == 1 else 1.02)
            tp = tp_arr[i] if math.isfinite(tp_arr[i]) else entry * (1.04 if ttype == 1 else 0.96)

            # Validate geometry: SL on the losing side, TP on the winning side.
            valid = (ttype == 1 and sl < entry < tp) or (ttype == -1 and tp < entry < sl)
            risk_per_share = abs(entry - sl)
            if not valid or risk_per_share <= 0:
                skipped_invalid += 1
                i += 1
                continue

            qty = int(min(risk_budget / risk_per_share, RISK.max_position_value / entry))
            if qty < 1:
                i += 1
                continue

            # Walk forward to find the exit bar via intrabar High/Low.
            exit_price = None
            exit_idx = n - 1
            for j in range(entry_idx, n):
                hi, lo = h[j], low[j]
                if ttype == 1:
                    hit_sl, hit_tp = lo <= sl, hi >= tp
                else:
                    hit_sl, hit_tp = hi >= sl, lo <= tp
                if hit_sl and hit_tp:
                    exit_price = sl if RISK.pessimistic_intrabar else tp
                    exit_idx = j
                    break
                if hit_sl:
                    exit_price, exit_idx = sl, j
                    break
                if hit_tp:
                    exit_price, exit_idx = tp, j
                    break
            if exit_price is None:
                exit_price = c[n - 1]  # still open at series end → mark to last close

            # Adverse slippage on exit
            exit_fill = exit_price * (1 - slip) if ttype == 1 else exit_price * (1 + slip)

            if ttype == 1:
                gross = (exit_fill - entry) * qty
                buy_val, sell_val = qty * entry, qty * exit_fill
            else:
                gross = (entry - exit_fill) * qty
                sell_val, buy_val = qty * entry, qty * exit_fill

            cost = costs.round_trip(buy_val, sell_val)
            net = gross - cost
            total_costs += cost
            gross_trades.append(gross)
            net_trades.append(net)

            current_capital += net
            if current_capital > peak:
                peak = current_capital
            dd = peak - current_capital
            if dd > max_dd:
                max_dd = dd

            i = exit_idx + 1  # no overlapping positions

        return {
            "net_trades": net_trades,
            "gross_trades": gross_trades,
            "total_costs": total_costs,
            "max_dd": max_dd,
            "skipped_invalid": skipped_invalid,
        }

    @staticmethod
    def _metrics(net_trades, gross_trades, total_costs, max_dd, skipped_invalid) -> dict:
        # ROI / drawdown are reported against one slot's capital (see simulate()).
        initial_capital = RISK.slot_capital
        if not net_trades:
            return {
                "winRate": 0.0, "totalTrades": 0, "netProfit": 0.0,
                "grossProfit": 0.0, "totalCosts": 0.0, "maxDrawdown": 0.0,
                "maxDrawdownPct": 0.0, "roiPercentage": 0.0, "grossRoiPercentage": 0.0,
                "profitFactor": 0.0, "avgWin": 0.0, "avgLoss": 0.0,
                "expectancy": 0.0, "skippedInvalid": skipped_invalid,
            }

        wins = [t for t in net_trades if t > 0]
        losses = [t for t in net_trades if t <= 0]
        win_rate = len(wins) / len(net_trades) * 100
        net_profit = sum(net_trades)
        gross_profit = sum(gross_trades)
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)
        avg_win = (gross_win / len(wins)) if wins else 0.0
        avg_loss = (gross_loss / len(losses)) if losses else 0.0
        expectancy = net_profit / len(net_trades)

        return {
            "winRate": round(win_rate, 2),
            "totalTrades": len(net_trades),
            "netProfit": round(net_profit, 2),
            "grossProfit": round(gross_profit, 2),
            "totalCosts": round(total_costs, 2),
            "maxDrawdown": round(max_dd, 2),
            "maxDrawdownPct": round(max_dd / initial_capital * 100, 2),
            "roiPercentage": round(net_profit / initial_capital * 100, 2),
            "grossRoiPercentage": round(gross_profit / initial_capital * 100, 2),
            "profitFactor": round(profit_factor, 2),
            "avgWin": round(avg_win, 2),
            "avgLoss": round(avg_loss, 2),
            "expectancy": round(expectancy, 2),
            "skippedInvalid": skipped_invalid,
        }
