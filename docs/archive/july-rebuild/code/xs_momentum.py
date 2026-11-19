"""XS Momentum 12-1 -- the one Phase-1 candidate that clears the friction gate.

Cross-sectional momentum: at each quarterly rebalance, rank the universe by its return over the
past 12 months **skipping the most recent month**, and hold the top K equal-weighted until the
next rebalance. The 12-1 window is not a detail -- the skipped month is what separates momentum
(11-month trend) from short-term reversal (last month tends to mean-revert), and a strategy that
forgets the skip is buying last month's spike, which is a different, worse bet. So the skip is a
tested invariant here, not a comment.

It rebalances ~4×/year and rotates a handful of names, so its friction is the quarterly figure
the gate passes (~2.8%/yr on ₹10k sleeves) -- unlike the intraday pair, whose 180-trades/year toll
the same gate rejects. This is the whole reason "both" was worth keeping (D9): momentum is the
side of the book that might survive its costs.

**What this file does NOT settle: R3.** The universe handed to `generate_targets` is chosen
elsewhere, and if it is today's liquid names ranked back over 2020-26, the momentum it "finds" is
survivorship, not edge -- a name is in the list *because* it went up. The ranking logic here is
correct and hand-verified; whether its output means anything depends entirely on a point-in-time
universe, which is still unbuilt and still the #1 wrong-YES risk (CLAUDE.md, HANDOFF).

Sizing follows the slot atom (D8): top-K equal weight ⇒ each sleeve funds exactly one ₹10,000
slot, so the K-name book is a ₹K×10,000 commitment. No per-trade stop (D9): the RebalanceEngine
holds each sleeve to the next rebalance, and the metric is the period return, not R.
"""

from __future__ import annotations

import pandas as pd

from trading.data.universe import Universe
from trading.engine.rebalance_engine import Panel
from trading.research.friction import Proposal
from trading.strategy.base import CrossSectionalStrategy
from trading.strategy.registry import HoldBucket, StrategyKind, StrategySpec, strategy

_TRADING_DAYS_PER_MONTH = 21  # the standard approximation; 12mo ≈ 252 bars, the skip ≈ 21


def _quarterly_rebalance_positions(dates: pd.DatetimeIndex, first_eligible: int) -> list[int]:
    """The integer positions of the first trading day of each quarter, from `first_eligible` on.

    Positions (not timestamps) so the momentum lookback is a clean array slice. `first_eligible`
    is the earliest bar with a full lookback behind it -- rebalances before that have no history
    to rank on and are skipped, not guessed.
    """
    positions: list[int] = []
    last_quarter: tuple[int, int] | None = None
    for i in range(first_eligible, len(dates)):
        q = (dates[i].year, dates[i].quarter)
        if q != last_quarter:
            positions.append(i)
            last_quarter = q
    return positions


class XSMomentum(CrossSectionalStrategy):
    """12-1 cross-sectional momentum, top-K equal weight, quarterly. Parameters are constructor
    args so a variant (a different lookback/skip/K) is a distinct trial for the ledger (P10)."""

    def __init__(
        self,
        lookback_months: int = 12,
        skip_months: int = 1,
        top_k: int = 6,
        universe: Universe | None = None,
    ):
        if lookback_months <= skip_months:
            raise ValueError(
                f"lookback_months ({lookback_months}) must exceed skip_months ({skip_months}): "
                "the momentum window is the span between them"
            )
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        self.lookback_months = lookback_months
        self.skip_months = skip_months
        self.top_k = top_k
        # The point-in-time universe (R3). WITHOUT it, ranking runs over every name in the panel --
        # fine for testing the ranking logic, but a real momentum number computed that way is
        # survivorship-biased (today's list judged over the past). WITH it, each rebalance ranks
        # only the names that were index members on that date.
        self.universe = universe
        self.lookback_days = lookback_months * _TRADING_DAYS_PER_MONTH
        self.skip_days = skip_months * _TRADING_DAYS_PER_MONTH

    def generate_targets(self, panel: Panel) -> pd.DataFrame:
        """Rank on close, hold the top K equal-weighted from each quarterly rebalance date.

        Momentum at bar i is `close[i - skip] / close[i - lookback] - 1` -- the return from a
        year ago up to one month ago. A name with no price at either endpoint (listed mid-window)
        cannot be ranked and is dropped, not treated as zero momentum.
        """
        close = panel.close
        dates = close.index
        rebalance_positions = _quarterly_rebalance_positions(
            dates, first_eligible=self.lookback_days
        )

        weight = 1.0 / self.top_k
        rows: list[tuple[pd.Timestamp, str, float]] = []
        for i in rebalance_positions:
            start = close.iloc[i - self.lookback_days]
            end = close.iloc[i - self.skip_days]
            momentum = (end / start - 1.0).dropna()  # drops names missing either endpoint
            if self.universe is not None:
                # Survivorship guard (R3): only names that were index members on this rebalance
                # date are eligible, whatever the panel happens to contain.
                members = self.universe.members_as_of(dates[i])
                momentum = momentum[momentum.index.isin(members)]
            if momentum.empty:
                continue
            winners = momentum.sort_values(ascending=False).head(self.top_k)
            for symbol in winners.index:
                rows.append((dates[i], symbol, weight))

        return pd.DataFrame(
            [w for *_, w in rows],
            columns=["weight"],
            index=pd.MultiIndex.from_tuples(
                [(t, s) for t, s, _ in rows], names=["rebalance_ts", "symbol"]
            ),
        )


_PROPOSAL = Proposal(
    name="xs_momentum_12_1",
    timeframe="1D",
    trades_per_year=6,  # ~4 rebalances/yr, but rotation books ~6 round trips (CLAUDE.md fact 1)
    entry_price=100.0,
    stop_pct=None,  # cross-sectional: no per-trade stop (D9) -> the bps arm gates it
    expected_edge_bps_gross=300.0,  # author's optimistic prior: ~3% gross per quarterly hold
    note="12-1 momentum, top-6, quarterly. The bps prior must clear ~74 bps at 2x margin.",
)

_SPEC = StrategySpec(
    name="xs_momentum_12_1",
    kind=StrategyKind.CROSS_SECTIONAL,
    timeframe="1D",
    bucket=HoldBucket.LONG_POSITIONAL,
    min_bars=12 * _TRADING_DAYS_PER_MONTH,  # a full 12-month lookback before the first rebalance
    slots=6,  # top-6 => a ₹60,000 commitment (D8), stated so it cannot surprise the owner
    proposal=_PROPOSAL,
)


@strategy(spec=_SPEC)
class XSMomentum121(XSMomentum):
    """The registered 12-1 top-6 configuration. Subclass so the tunable base can be reused for
    variant trials without re-registering the name."""
