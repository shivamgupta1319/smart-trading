"""Abstract base class for all trading strategies."""
from abc import ABC, abstractmethod
import math
import numpy as np
import pandas as pd

from backtest_config import (
    RISK, CostModel, uses_trailing_exit, trail_mult_for_bucket, SWING_TRAIL_ATR_PERIOD,
    LEVERAGE_INTRADAY, LEVERAGE_DELIVERY, RISK_PER_TRADE_PCT, time_stop_bars_for_bucket,
    MAX_COST_TO_RISK, cost_to_risk, slippage_per_share,
)
from entry_limits import candle_length, entry_allowed, intraday_entry_time_ok, limits_for_bucket
from intraday_exits import (
    PHASE2_TRIGGER, PHASE3_TRIGGER, REVERSAL_ZONE_START,
    PARTIAL_FRACTION, MIN_QTY_FOR_PARTIAL, SQUARE_OFF_TIME,
    progress_price, breakeven_stop, candle_trail_stop, detect_reversal,
)


def _atr_array(h, low, c, period: int):
    """Wilder-ish ATR via a simple rolling mean of True Range (period bars)."""
    prev_c = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum.reduce([h - low, np.abs(h - prev_c), np.abs(low - prev_c)])
    return pd.Series(tr).rolling(period, min_periods=1).mean().to_numpy()


def stop_fill_price(stop: float, bar_open: float, is_buy: bool) -> float:
    """Price a triggered stop actually fills at on a bar.

    If the bar opens beyond the stop (a gap through it), the fill is that open:
    a long with a ₹100 stop on a bar opening at ₹92 exits at ₹92, not ₹100.
    Otherwise the stop price itself. Slippage is applied by the caller.
    """
    if not RISK.gap_through_stop_at_open or not math.isfinite(bar_open):
        return stop
    return min(stop, bar_open) if is_buy else max(stop, bar_open)


def position_qty(notional_budget: float, risk_budget: float, entry: float, risk_per_share: float) -> int:
    """Shares to trade: the smaller of what the notional budget buys and what the
    rupee-risk budget allows (FEAT-005). Returns 0 when even ONE share breaks either
    bound — the caller skips the trade. It used to be forced to 1 share, which on a
    ₹10k fund let a high-priced, wide-stop stock risk several times the 2% cap.

    MUST match `sizePosition` in apps/api/src/common/risk.ts.
    """
    if entry <= 0:
        return 0
    notional_qty = int(notional_budget / entry)
    risk_qty = int(risk_budget / risk_per_share) if risk_per_share > 0 else notional_qty
    return max(0, min(notional_qty, risk_qty))


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

    def _hold_bucket(self):
        """This strategy's hold-duration bucket (INTRADAY/SHORT_SWING/…) or None.
        Lazy import avoids a circular dependency with the strategies package."""
        try:
            from strategies import STRATEGY_HOLD_DURATIONS
            return STRATEGY_HOLD_DURATIONS.get(getattr(self, "name", ""), None)
        except Exception:
            return None

    def _apply_bucket_target(self, df: pd.DataFrame) -> pd.DataFrame:
        """Override the `target` column to a bucket-specific reward:risk multiple
        (the validated R:R-by-horizon model). The STOP is left exactly as the
        strategy set it — only the reward distance changes. For buckets with no
        configured multiple (e.g. INTRADAY) the native target is kept unchanged.

        Applied in BOTH the backtest (via simulate) and live signals (via the
        scanner), so the two never diverge. Reward is measured from the signal
        bar's Close, the same reference each strategy uses for its own target.

        Also enforces LONG-ONLY for non-intraday buckets: swing/positional trades are
        equity delivery (CNC) and can't be held short overnight in the cash segment,
        so any SELL (signal == -1) is dropped. Intraday (MIS) may still short.
        """
        from backtest_config import target_r_for_bucket
        bucket = self._hold_bucket()
        if bucket != "INTRADAY" and "signal" in df.columns and (df["signal"].to_numpy() < 0).any():
            df = df.copy()
            df.loc[df["signal"] < 0, "signal"] = 0
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

    def run_backtest(self, df: pd.DataFrame, trade_from: int = 0) -> dict:
        """Run a realistic backtest and return aggregate metrics.

        trade_from: bar position before which signals are ignored. The earlier bars
        are still fed to the strategy so its indicators are warmed up (walk-forward).
        """
        sim = self.simulate(df, trade_from=trade_from)
        m = self._metrics(
            sim["net_trades"], sim["gross_trades"], sim["total_costs"],
            sim["max_dd"], sim["max_dd_pct"], sim["skipped_invalid"],
            sim["r_trades"],
        )
        m["spanYears"] = self._span_years(df)
        return m

    @staticmethod
    def _span_years(df: pd.DataFrame) -> float:
        """Calendar years the bars actually cover — measured, not assumed per timeframe.

        roiPercentage is raw cumulative over whatever history happens to be stored, and
        that window differs ~13× between buckets (1D fetches 5y, 15m/5m 60d), so the
        same "19%" is ~3.7%/yr on a swing cell but ~49%/yr on an intraday one. Reporting
        this alongside lets ROI be annualised honestly and compared across buckets.
        Returns 0.0 when the span isn't derivable (callers must treat it as unknown).
        """
        try:
            if len(df) < 2 or not isinstance(df.index, pd.DatetimeIndex):
                return 0.0
            days = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
            return round(days / 365.25, 4) if days > 0 else 0.0
        except (TypeError, ValueError, AttributeError):
            return 0.0

    def simulate(self, df: pd.DataFrame, trade_from: int = 0) -> dict:
        """Run the realistic fill simulation and return per-trade P&L lists.

        Fill model (removes the optimistic biases of the old close-only engine):
          * Entry on the NEXT bar's open (configurable), with adverse slippage.
          * Stop-loss / target evaluated against each subsequent bar's intrabar
            High/Low — not the close. If a single bar straddles both levels we
            assume the worse (SL) filled first (pessimistic_intrabar).
          * A bar that opens beyond the stop fills at that open, not at the stop
            (gap_through_stop_at_open) — see `stop_fill_price`.
          * Notional position sizing: qty = cell equity × bucket leverage / entry
            (intraday 5×, swing/delivery 1×), matching the live per-cell fund model.
            Notional is capped at max_position_value unless BT_CAP_POSITION_VALUE
            is off, so a compounding cell doesn't size geometrically.
          * Indian transaction costs + slippage subtracted to report NET P&L
            alongside GROSS.

        Returns {net_trades, gross_trades, r_trades, total_costs, max_dd,
        max_dd_pct, skipped_invalid}.
        """
        df = self.generate_signals(df).copy()
        df = self._apply_bucket_target(df)  # bucket reward:risk override (R:R-by-horizon)
        tf = getattr(self, "timeframe", "1D")
        costs = CostModel(tf)

        o = df["Open"].to_numpy(dtype=float)
        h = df["High"].to_numpy(dtype=float)
        low = df["Low"].to_numpy(dtype=float)
        c = df["Close"].to_numpy(dtype=float)
        # A strategy that bails out early (its minimum-bars guard) returns no `signal`
        # column. That is "could not evaluate", not "no trades" — report it so a
        # zero-trade backtest on too little data is not read as a clean result.
        no_signal_column = "signal" not in df.columns
        sig = df.get("signal", pd.Series(0, index=df.index)).fillna(0).to_numpy(dtype=float)
        if trade_from > 0:
            # Warm-up bars: indicators have seen them, but no trade may start there.
            sig = sig.copy()
            sig[:trade_from] = 0
        sl_arr = df.get("stop_loss", pd.Series(np.nan, index=df.index)).to_numpy(dtype=float)
        tp_arr = df.get("target", pd.Series(np.nan, index=df.index)).to_numpy(dtype=float)
        vol = df.get("Volume", pd.Series(0.0, index=df.index)).to_numpy(dtype=float)
        # Bar timestamps drive the intraday 15:15 square-off; kept as-is (IST-naive,
        # per load_historical). The swing/delivery path never reads them.
        ts = df.index

        n = len(df)
        # Swing/mid/long trail the stop (chandelier); intraday keeps fixed SL/TP.
        _bucket = self._hold_bucket()
        trailing = uses_trailing_exit(_bucket)
        atr = _atr_array(h, low, c, SWING_TRAIL_ATR_PERIOD) if trailing else None
        trail_mult = trail_mult_for_bucket(_bucket)
        # Bars to hold a swing before exiting flat (None = unbounded). Mirrored in
        # scanner/live_scanner.auto_close_signals — see backtest_config (audit F3).
        time_stop_bars = time_stop_bars_for_bucket(_bucket)
        # A single-cell backtest simulates ONE portfolio slot (₹10k) traded
        # repeatedly, so its P&L/ROI is comparable to one live slot rather than
        # to the whole ₹1L account.
        initial_capital = RISK.slot_capital

        net_trades: list[float] = []
        gross_trades: list[float] = []
        r_trades: list[float] = []  # per-trade R-multiple (net ÷ rupee risked) — horizon/compounding-independent edge
        total_costs = 0.0
        current_capital = initial_capital
        peak = initial_capital
        max_dd = 0.0
        max_dd_pct = 0.0
        skipped_invalid = 0
        # Entry-limit state (None for buckets that are not limited).
        limits = limits_for_bucket(_bucket)
        limit_day = None       # trading day `trades_on_day` counts
        trades_on_day = 0
        last_exit_ts = None    # bar on which this cell's previous trade closed
        skipped_limits = 0
        skipped_window = 0     # INTRADAY signals outside 09:30-15:00 or from an earlier day
        skipped_unsizable = 0  # signals where one share already broke a sizing bound
        skipped_costly = 0     # signals whose round-trip cost was too large a share of the risk
        # One row per trade taken: which candle signalled, where it entered and exited.
        # Read by the replay test that compares this engine with the live scanner.
        trade_log: list[dict] = []

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

            # Per-cell entry limits (daily cap + cooldown after an exit) — the same
            # `entry_allowed` the live scanner calls. A blocked signal is dropped,
            # exactly as live drops it; the next signal is judged on its own.
            entry_ts = ts[entry_idx]
            # INTRADAY entry window and no stale overnight signals: the rule the live
            # scanner applies. Without it the backtest opened trades at 15:00 and 15:15
            # that live never takes, and squared them off at once for a cost.
            if _bucket == "INTRADAY" and hasattr(entry_ts, "time"):
                # The signal candle completes as the entry candle opens.
                ok, _why = intraday_entry_time_ok(entry_ts, entry_ts)
                if not ok:
                    skipped_window += 1
                    i += 1
                    continue
            if limits is not None and hasattr(entry_ts, "date"):
                if entry_ts.date() != limit_day:
                    limit_day, trades_on_day = entry_ts.date(), 0
                ok, _why = entry_allowed(limits, trades_on_day, last_exit_ts, entry_ts)
                if not ok:
                    skipped_limits += 1
                    i += 1
                    continue

            # Adverse slippage on entry (buy fills higher, short fills lower)
            entry = entry_raw + slippage_per_share(entry_raw) if ttype == 1 else entry_raw - slippage_per_share(entry_raw)

            sl = sl_arr[i] if math.isfinite(sl_arr[i]) else entry * (0.98 if ttype == 1 else 1.02)
            tp = tp_arr[i] if math.isfinite(tp_arr[i]) else entry * (1.04 if ttype == 1 else 0.96)

            # Validate geometry: SL on the losing side, TP on the winning side.
            valid = (ttype == 1 and sl < entry < tp) or (ttype == -1 and tp < entry < sl)
            risk_per_share = abs(entry - sl)
            # The quote itself must also be on the right side of the stop: the cost rule
            # below is judged on the quote, and a stop exactly at the quote has no risk
            # to judge against (live drops it too: entry_geometry_ok).
            if not valid or risk_per_share <= 0 or abs(entry_raw - sl) <= 0:
                skipped_invalid += 1
                i += 1
                continue

            # Per-cell fund sizing, COMPOUNDING + leverage — size from this cell's
            # CURRENT equity (grows with prior P&L), identical to the live model
            # (cellCapital × leverage of notional). Intraday (MIS) deploys 5× the
            # fund, swing/delivery (CNC) 1×. See `position_qty` for the two bounds.
            leverage = LEVERAGE_INTRADAY if _bucket == "INTRADAY" else LEVERAGE_DELIVERY
            notional = current_capital * leverage
            if RISK.cap_position_value:
                # Bound notional so a compounding cell doesn't size geometrically —
                # keeps ROI/DD/PF honest for selection (see backtest_config).
                notional = min(notional, RISK.max_position_value)
            # Risk at most 2% of what the trade may deploy (fund × leverage, capped like the
            # notional): Rs 1,000 intraday, Rs 200 swing on a Rs 10k fund. Same rule as the API.
            qty = position_qty(notional, notional * RISK_PER_TRADE_PCT, entry, risk_per_share)
            if qty < 1:
                # One share already breaks the notional or the risk cap: live rejects
                # this signal (signals.service), so the backtest must not take it either.
                skipped_unsizable += 1
                i += 1
                continue

            # Cost-to-risk gate: what the round trip costs (charges + slippage both
            # ways) as a share of the rupees risked. With a tight stop the costs alone
            # can be half the risk, so the trade needs an unrealistic edge to pay.
            if MAX_COST_TO_RISK > 0:
                # Judged on the quote and the stop as the API sees them (before the
                # simulated slippage), so both sides drop the same borderline trades.
                if cost_to_risk(qty, entry_raw, abs(entry_raw - sl), tf) > MAX_COST_TO_RISK:
                    skipped_costly += 1
                    i += 1
                    continue

            # Walk forward to the exit bar. INTRADAY models the live 3-phase exit
            # (partials + breakeven + candle-trail + reversal + 15:15 square-off);
            # swing/mid/long use the chandelier-trail / fixed-SL walk below.
            if _bucket == "INTRADAY":
                exit_idx, gross, buy_val, sell_val = self._intraday_exit(
                    entry_idx, entry, sl, tp, ttype, qty,
                    o, h, low, c, vol, ts, n,
                )
            else:
                # For swing buckets `cur_sl` ratchets up with a chandelier trail
                # (peak ∓ k·ATR); for the rest it stays fixed (== sl).
                exit_price = None
                exit_idx = n - 1
                cur_sl = sl
                px_peak = entry  # best PRICE since entry (for the chandelier trail)
                for j in range(entry_idx, n):
                    hi, lo = h[j], low[j]
                    if ttype == 1:
                        hit_sl, hit_tp = lo <= cur_sl, hi >= tp
                    else:
                        hit_sl, hit_tp = hi >= cur_sl, lo <= tp
                    if hit_sl and hit_tp:
                        exit_price = stop_fill_price(cur_sl, o[j], ttype == 1) if RISK.pessimistic_intrabar else tp
                        exit_idx = j
                        break
                    if hit_sl:
                        exit_price, exit_idx = stop_fill_price(cur_sl, o[j], ttype == 1), j
                        break
                    if hit_tp:
                        exit_price, exit_idx = tp, j
                        break
                    # Time-stop (F3): N bars held, neither stop nor target hit. The
                    # condition is only knowable once bar j has CLOSED, so the exit
                    # lands on the NEXT bar's open — the session in which live's first
                    # poll fires it. live_scanner.auto_close_signals mirrors this by
                    # checking the time-stop BEFORE its SL/TP check, so the two agree
                    # on which bar ends the trade.
                    if time_stop_bars is not None and (j - entry_idx) >= time_stop_bars:
                        if j + 1 < n:
                            exit_price, exit_idx = o[j + 1], j + 1
                        else:
                            exit_price, exit_idx = c[j], j  # series ends → mark to close
                        break
                    # Ratchet the trailing stop using THIS bar's extreme, applied to
                    # the NEXT bar (so no intrabar lookahead).
                    if trailing:
                        if ttype == 1:
                            if hi > px_peak:
                                px_peak = hi
                            new_sl = px_peak - trail_mult * atr[j]
                            if new_sl > cur_sl:
                                cur_sl = new_sl
                        else:
                            if lo < px_peak:
                                px_peak = lo
                            new_sl = px_peak + trail_mult * atr[j]
                            if new_sl < cur_sl:
                                cur_sl = new_sl
                if exit_price is None:
                    exit_price = c[n - 1]  # still open at series end → mark to last close

                # Adverse slippage on exit
                exit_fill = exit_price - slippage_per_share(exit_price) if ttype == 1 else exit_price + slippage_per_share(exit_price)

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
            # R-multiple = net P&L ÷ rupees risked at entry (risk_per_share × qty,
            # both > 0 here). Compounding- and horizon-independent, so it's the
            # honest edge metric to rank cells on. Uses NET (after costs).
            r_trades.append(net / (risk_per_share * qty))

            trade_log.append({
                "signal_ts": ts[i], "entry_ts": ts[entry_idx], "exit_ts": ts[exit_idx],
                "side": "BUY" if ttype == 1 else "SELL", "entry": float(entry_raw), "qty": int(qty),
            })

            current_capital += net
            if current_capital > peak:
                peak = current_capital
            dd = peak - current_capital
            if dd > max_dd:
                max_dd = dd
            # Peak-relative drawdown — the standard "max drawdown %". With a
            # compounding curve, % of INITIAL capital is meaningless (a late dip
            # can exceed 100% of the seed); % of the running peak is correct.
            dd_pct = dd / peak if peak > 0 else 0.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

            if limits is not None:
                trades_on_day += 1
                # The exit happened somewhere inside the exit candle. Count the cooldown
                # from that candle's END: live counts from the real exit time, and from
                # the candle's start the backtest re-entered a candle earlier than live.
                last_exit_ts = ts[exit_idx] + candle_length(tf) if hasattr(ts[exit_idx], "date") else None

            i = exit_idx + 1  # no overlapping positions

        return {
            "no_signal_column": no_signal_column,
            "skipped_limits": skipped_limits,
            "skipped_window": skipped_window,
            "skipped_unsizable": skipped_unsizable,
            "skipped_costly": skipped_costly,
            "net_trades": net_trades,
            "gross_trades": gross_trades,
            "r_trades": r_trades,
            "total_costs": total_costs,
            "max_dd": max_dd,
            "max_dd_pct": max_dd_pct,
            "skipped_invalid": skipped_invalid,
            "trade_log": trade_log,
        }

    def _intraday_exit(self, entry_idx, entry, sl0, tp, ttype, qty,
                       o, h, low, c, vol, ts, n):
        """Model the LIVE intraday 3-phase exit bar-by-bar (15m bars), mirroring
        `scanner/live_scanner.auto_close_signals` via the shared `intraday_exits`
        primitives so backtest ⇄ live can't drift.

        Per bar (buy shown; short is the mirror), in the same order live polls:
          1. Stop first — pessimistic: an intrabar stop hit ends the trade.
          2. 15:15 square-off — MIS is force-flattened at the entry day's close bar
             (exit at that bar's open ≈ the 15:15 price); no partials/target there.
          3. Partials — at the 50%/75% progress LEVELS book 35% of the ORIGINAL qty
             (only if qty ≥ MIN_QTY_FOR_PARTIAL and a runner survives); phase-2 moves
             the stop to breakeven, phase-3 starts the candle trail.
          4. Target — books ALL remaining at tp.
          5. Reversal — once past the 80% level, exit the remainder at the bar close
             on a reversal candle pattern.
          6. Phase-3 candle trail — ratchet the stop to this bar's low/high, applied
             to the NEXT bar (uses bar j's extreme, checked at j+1 — no lookahead).

        Returns (exit_idx, gross, buy_val, sell_val). Costs at intraday sizes are
        linear in turnover (the ₹20 brokerage cap never binds, DP = 0), so the
        weighted multi-leg sell can be costed on aggregate buy_val + summed sell_val.
        """
        is_buy = ttype == 1
        lvl50 = progress_price(entry, tp, PHASE2_TRIGGER, is_buy)
        lvl75 = progress_price(entry, tp, PHASE3_TRIGGER, is_buy)
        lvl80 = progress_price(entry, tp, REVERSAL_ZONE_START, is_buy)

        # Same-day boundary for the square-off (index is IST-naive per load_historical).
        entry_ts = ts[entry_idx]
        entry_day = entry_ts.date() if hasattr(entry_ts, "date") else None

        cur_sl = sl0
        state = "INITIAL"
        remaining = qty
        legs: list[tuple[int, float]] = []  # (leg_qty, leg_price) before slippage
        exit_idx = n - 1
        # Live gates partials on the FULL qty; book 35% but always leave a runner.
        can_partial = qty >= MIN_QTY_FOR_PARTIAL
        partial_qty = max(1, int(qty * PARTIAL_FRACTION))

        for j in range(entry_idx, n):
            hi, lo = h[j], low[j]

            # 1) Stop first (pessimistic).
            if (is_buy and lo <= cur_sl) or (not is_buy and hi >= cur_sl):
                legs.append((remaining, stop_fill_price(cur_sl, o[j], is_buy)))
                remaining = 0
                exit_idx = j
                break

            # 2) 15:15 square-off (or any bar rolled onto a later day).
            ts_j = ts[j]
            if entry_day is not None and hasattr(ts_j, "time"):
                if ts_j.date() != entry_day or ts_j.time() >= SQUARE_OFF_TIME:
                    legs.append((remaining, o[j]))
                    remaining = 0
                    exit_idx = j
                    break

            # 3) Partial phase transitions — book at the threshold LEVEL price.
            if can_partial and state == "INITIAL" and \
                    ((is_buy and hi >= lvl50) or (not is_buy and lo <= lvl50)) and \
                    remaining - partial_qty >= 1:
                legs.append((partial_qty, lvl50))
                remaining -= partial_qty
                be = breakeven_stop(entry, is_buy)
                if (is_buy and be > cur_sl) or (not is_buy and be < cur_sl):
                    cur_sl = be
                state = "PHASE2"
            if can_partial and state == "PHASE2" and \
                    ((is_buy and hi >= lvl75) or (not is_buy and lo <= lvl75)) and \
                    remaining - partial_qty >= 1:
                legs.append((partial_qty, lvl75))
                remaining -= partial_qty
                state = "PHASE3"

            # 4) Target books all remaining.
            if (is_buy and hi >= tp) or (not is_buy and lo <= tp):
                legs.append((remaining, tp))
                remaining = 0
                exit_idx = j
                break

            # 5) Reversal exit on the remainder once in the 80% zone (at bar close).
            if (is_buy and hi >= lvl80) or (not is_buy and lo <= lvl80):
                s = max(0, j - 9)  # last up-to-10 bars, like live get_recent_candles
                wdf = pd.DataFrame({
                    "Open": o[s:j + 1], "High": h[s:j + 1], "Low": low[s:j + 1],
                    "Close": c[s:j + 1], "Volume": vol[s:j + 1],
                })
                is_rev, _ = detect_reversal(wdf, is_buy)
                if is_rev:
                    legs.append((remaining, c[j]))
                    remaining = 0
                    exit_idx = j
                    break

            # 6) Phase-3 candle trail (ratchet to bar j's extreme, applied next bar).
            if state == "PHASE3":
                trail = candle_trail_stop(low[j], h[j], is_buy)
                if (is_buy and trail > cur_sl) or (not is_buy and trail < cur_sl):
                    cur_sl = trail

        if remaining > 0:
            legs.append((remaining, c[n - 1]))  # open at series end → last close
            exit_idx = n - 1

        # Aggregate legs with adverse slippage; keep the round_trip buy/sell convention.
        entry_val = qty * entry
        exit_val = 0.0
        gross = 0.0
        for lq, lp in legs:
            fill = lp - slippage_per_share(lp) if is_buy else lp + slippage_per_share(lp)
            exit_val += lq * fill
            gross += (fill - entry) * lq if is_buy else (entry - fill) * lq
        if is_buy:
            buy_val, sell_val = entry_val, exit_val
        else:
            sell_val, buy_val = entry_val, exit_val
        return exit_idx, gross, buy_val, sell_val

    @staticmethod
    def _metrics(net_trades, gross_trades, total_costs, max_dd, max_dd_pct, skipped_invalid, r_trades=None) -> dict:
        # ROI is the compounded return on one slot's capital; maxDrawdownPct is the
        # peak-relative max drawdown (see simulate()). avgRMultiple is the mean
        # per-trade R (net ÷ risk) — the compounding-independent edge metric.
        initial_capital = RISK.slot_capital
        r_trades = r_trades or []
        if not net_trades:
            return {
                "winRate": 0.0, "totalTrades": 0, "netProfit": 0.0,
                "grossProfit": 0.0, "totalCosts": 0.0, "maxDrawdown": 0.0,
                "maxDrawdownPct": 0.0, "roiPercentage": 0.0, "grossRoiPercentage": 0.0,
                "profitFactor": 0.0, "avgWin": 0.0, "avgLoss": 0.0,
                "expectancy": 0.0, "avgRMultiple": 0.0, "skippedInvalid": skipped_invalid,
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
        avg_r_multiple = (sum(r_trades) / len(r_trades)) if r_trades else 0.0

        return {
            "winRate": round(win_rate, 2),
            "totalTrades": len(net_trades),
            "netProfit": round(net_profit, 2),
            "grossProfit": round(gross_profit, 2),
            "totalCosts": round(total_costs, 2),
            "maxDrawdown": round(max_dd, 2),
            "maxDrawdownPct": round(max_dd_pct * 100, 2),
            "roiPercentage": round(net_profit / initial_capital * 100, 2),
            "grossRoiPercentage": round(gross_profit / initial_capital * 100, 2),
            "profitFactor": round(profit_factor, 2),
            "avgWin": round(avg_win, 2),
            "avgLoss": round(avg_loss, 2),
            "expectancy": round(expectancy, 2),
            "avgRMultiple": round(avg_r_multiple, 3),
            "skippedInvalid": skipped_invalid,
        }
