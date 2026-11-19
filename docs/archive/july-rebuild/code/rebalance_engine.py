"""The RebalanceEngine: the second of D9's two engines, for cross-sectional strategies.

A ranker (XS momentum, PEAD) cannot be expressed as `generate_signals(df)` -- it ranks the whole
universe and holds the best K, and the capital rotates between names. So this engine is panel-wide:
at each rebalance date it takes target weights, fills at the NEXT open (no intrabar lookahead), and
holds each sleeve to the next rebalance. **No per-trade stop** -- forcing one on a momentum sleeve
would be modelling fiction (D9), so there is no R-multiple here; the metric is the period return.

Two engines, one comparable result. A degenerate cross-sectional strategy that always holds exactly
one name must produce the same trades as the StopEngine on the same signals -- that cross-engine
invariant (ARCHITECTURE §3) is what proves the two are the same underlying model, and it is the next
slice. This one builds and proves the panel mechanism itself.

Sizing matches the slot atom (D8): a top-K sleeve funds `n_slots × ₹10,000`, split by weight, each
sleeve sized by buying power (delivery, 1×, no stop -- like `capital.size_unstopped`). Costs and
slippage are the same models the StopEngine and the friction gate use (D1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import floor

import numpy as np
import pandas as pd

from trading.core.capital import RiskConfig, load_risk_config
from trading.core.costs import CostModel
from trading.core.slippage import SlippageConfig, load_slippage_config, per_share
from trading.engine.stop_engine import EngineConfig  # shared fill config -> identical slippage (D1)


class Panel:
    """Aligned daily prices for a universe of symbols. Open drives fills, Close drives ranking.

    Built from the store's per-symbol frames. Symbols need not cover identical date ranges -- a
    name listed mid-history simply has NaNs before it existed, and a fill on a NaN open is skipped
    (you cannot buy a stock that was not trading).
    """

    def __init__(self, frames: dict[str, pd.DataFrame]):
        if not frames:
            raise ValueError("Panel needs at least one symbol")
        self.symbols = tuple(sorted(frames))
        self.open = pd.DataFrame({s: frames[s]["Open"] for s in self.symbols}).sort_index()
        self.close = pd.DataFrame({s: frames[s]["Close"] for s in self.symbols}).sort_index()
        self.dates = self.open.index

    def next_open(self, after: datetime, symbol: str) -> tuple[pd.Timestamp, float] | None:
        """The first (date, open) strictly after `after` for `symbol`, skipping NaN opens.

        This is the fill: a target decided as of a rebalance date is filled at the next real open,
        never on the rebalance bar itself (that would be lookahead).
        """
        col = self.open[symbol]
        future = col[(col.index > after) & col.notna()]
        if future.empty:
            return None
        return future.index[0], float(future.iloc[0])


@dataclass(frozen=True)
class Position:
    """One sleeve held across one rebalance period. No stop, so no R -- the edge is `net_return`."""

    symbol: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    qty: int
    weight: float
    gross: float
    cost: float

    @property
    def net(self) -> float:
        return self.gross - self.cost

    @property
    def net_return(self) -> float:
        """Net P&L as a fraction of the sleeve's deployed capital -- the per-period edge."""
        return self.net / (self.qty * self.entry)


@dataclass(frozen=True)
class RebalanceResult:
    positions: tuple[Position, ...]
    slot_capital: float
    n_slots: int
    total_costs: float
    unfilled: int  # target names with no tradeable open after the rebalance date

    @property
    def n_positions(self) -> int:
        return len(self.positions)

    @property
    def net_pnl(self) -> float:
        return sum(p.net for p in self.positions)

    @property
    def roi(self) -> float:
        """Net P&L over the whole funded commitment (n_slots × slot)."""
        return self.net_pnl / (self.n_slots * self.slot_capital)

    @property
    def avg_period_return(self) -> float | None:
        if not self.positions:
            return None
        return float(np.mean([p.net_return for p in self.positions]))

    @property
    def win_rate(self) -> float | None:
        if not self.positions:
            return None
        return sum(1 for p in self.positions if p.net > 0) / len(self.positions)


def run(
    panel: Panel,
    targets: pd.DataFrame,
    n_slots: int,
    cfg: EngineConfig | None = None,
    risk_cfg: RiskConfig | None = None,
    slip_cfg: SlippageConfig | None = None,
) -> RebalanceResult:
    """Turn target weights into rotated positions on the panel.

    `targets` is long-form: a MultiIndex (rebalance_ts, symbol) with a `weight` column. Each
    rebalance date's holdings are entered at the next open and exited at the open after the NEXT
    rebalance date (rotation); the final period is marked to the last available open.
    """
    cfg = cfg or EngineConfig()
    risk_cfg = risk_cfg or load_risk_config()
    slip_cfg = slip_cfg or load_slippage_config()
    cost_model = CostModel("1D")  # cross-sectional strategies are delivery
    leverage = risk_cfg.leverage_for("delivery")

    rebalance_dates = sorted(targets.index.get_level_values(0).unique())
    positions: list[Position] = []
    total_costs = 0.0
    unfilled = 0

    for k, t in enumerate(rebalance_dates):
        held = targets.loc[t]
        held = held[held["weight"] > 0]
        exit_after = rebalance_dates[k + 1] if k + 1 < len(rebalance_dates) else panel.dates[-1]

        for symbol, row in held.iterrows():
            weight = float(row["weight"])
            entered = panel.next_open(t, symbol)
            if entered is None:
                unfilled += 1
                continue
            entry_ts, entry_raw = entered
            entry = entry_raw + per_share(entry_raw, cfg.tick, cfg.spread, slip_cfg)

            sleeve_capital = n_slots * risk_cfg.slot_capital * weight
            qty = floor(sleeve_capital * leverage / entry)
            if qty <= 0:  # a single share costs more than the sleeve's buying power -> skip
                unfilled += 1
                continue

            exited = panel.next_open(exit_after, symbol)
            if exited is None:
                # No open after the exit date (series ended). Mark to the symbol's last close.
                last = panel.close[symbol].dropna()
                exit_ts, exit_raw = last.index[-1], float(last.iloc[-1])
            else:
                exit_ts, exit_raw = exited
            exit_fill = exit_raw - per_share(exit_raw, cfg.tick, cfg.spread, slip_cfg)

            gross = (exit_fill - entry) * qty  # long-only (D9: momentum sleeves are long)
            cost = cost_model.round_trip(qty * entry, qty * exit_fill)
            total_costs += cost
            positions.append(
                Position(symbol, entry_ts, exit_ts, entry, exit_fill, qty, weight, gross, cost)
            )

    return RebalanceResult(
        positions=tuple(positions),
        slot_capital=risk_cfg.slot_capital,
        n_slots=n_slots,
        total_costs=total_costs,
        unfilled=unfilled,
    )
