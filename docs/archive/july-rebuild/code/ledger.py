"""The Ledger: the one place the two engines become comparable, and the slot budget is enforced.

D9 gives us two engines because one signal interface cannot honestly cover both a per-symbol
stop model and a panel-wide ranker (ARCHITECTURE §3). They are unified not at the signal
function -- that would be a fake abstraction -- but here, at a shared `Trade` record and a
`Ledger` that both feed. Each engine keeps its own rich native record (`stop_engine.Trade`
carries the R-multiple and the gap flag; `rebalance_engine.Position` carries the sleeve weight
and period return); this module maps both down to the common facts every trade has -- who,
when, how much, what it cost -- and nothing it does not.

**The slot budget (D8 / ARCHITECTURE §2).** The owner funds a *concurrent position*, not a
stock: a time-series cell is 1 slot (Rs 10k); a cross-sectional top-K cell is K slots (Rs
10k each). The danger is a strategy that quietly holds K+1 names -- spending money that does
not exist. `Ledger.check` computes the peak number of simultaneously-open positions and
raises `SlotBreach` if it exceeds the declared slots. It fails loudly rather than reporting a
plausible return on capital that was never funded.

**Why the tie-break matters.** A slot rotates: one sleeve exits at exactly the timestamp the
next enters (the RebalanceEngine fills both at `next_open(rebalance_date)`). If that counted as
an overlap, every rotating top-K would read as 2K concurrent and every strategy would breach.
So at a shared timestamp exits are processed before entries -- the slot frees before it is
reused -- and a clean rotation reads as exactly K, which is what it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from trading.engine.rebalance_engine import RebalanceResult
    from trading.engine.stop_engine import Result


@dataclass(frozen=True)
class Trade:
    """The common facts of one round trip, shared by both engines.

    `entry_ts`/`exit_ts` are any orderable time key -- bar positions from the StopEngine,
    Timestamps from the RebalanceEngine. A single Ledger only ever holds one engine's trades
    (a cell runs on one engine), so the keys are never mixed within a comparison.
    """

    slot_id: str  # which cell/sleeve this belongs to -- provenance, not the concurrency key
    symbol: str
    side: int
    entry_ts: Any
    exit_ts: Any
    entry: float
    exit: float
    qty: int
    gross: float
    cost: float  # broker round-trip

    @property
    def net(self) -> float:
        return self.gross - self.cost


class SlotBreach(AssertionError):
    """A cell held more concurrent positions than it funded. Raised, never swallowed."""


def from_stop_result(result: Result, symbol: str, slot_id: str) -> tuple[Trade, ...]:
    """Map a StopEngine `Result` to shared trades. Time keys are bar positions (entry_idx/
    exit_idx) -- a time-series cell is one slot and never overlaps itself, so positional keys
    are all the concurrency check needs."""
    return tuple(
        Trade(
            slot_id=slot_id,
            symbol=symbol,
            side=t.side,
            entry_ts=t.entry_idx,
            exit_ts=t.exit_idx,
            entry=t.entry,
            exit=t.exit,
            qty=t.qty,
            gross=t.gross,
            cost=t.cost,
        )
        for t in result.trades
    )


def from_rebalance_result(result: RebalanceResult, slot_id: str) -> tuple[Trade, ...]:
    """Map a RebalanceEngine `RebalanceResult` to shared trades. Momentum sleeves are long-only
    (D9), so `side` is always LONG. All sleeves of one top-K cell share the cell's `slot_id`;
    the K-slot budget is enforced by peak overlap, not by the id."""
    from trading.engine.stop_engine import LONG

    return tuple(
        Trade(
            slot_id=slot_id,
            symbol=p.symbol,
            side=LONG,
            entry_ts=p.entry_ts,
            exit_ts=p.exit_ts,
            entry=p.entry,
            exit=p.exit,
            qty=p.qty,
            gross=p.gross,
            cost=p.cost,
        )
        for p in result.positions
    )


def _peak(trades: tuple[Trade, ...]) -> tuple[int, Any, tuple[str, ...]]:
    """Sweep the open/close events and return (peak_concurrent, ts_at_peak, symbols_at_peak).

    Events sort by (ts, delta): -1 (exit) sorts before +1 (entry) at an equal timestamp, so a
    slot that frees and is reused on the same bar reads as one position, not two.
    """
    if not trades:
        return 0, None, ()
    events: list[tuple[Any, int, str]] = []
    for t in trades:
        events.append((t.entry_ts, 1, t.symbol))
        events.append((t.exit_ts, -1, t.symbol))
    events.sort(key=lambda e: (e[0], e[1]))

    open_syms: list[str] = []
    running = 0
    peak = 0
    peak_ts: Any = None
    peak_syms: tuple[str, ...] = ()
    for ts, delta, sym in events:
        if delta == -1:
            # A symbol may be held twice sequentially; drop the first matching open marker.
            if sym in open_syms:
                open_syms.remove(sym)
            running -= 1
        else:
            open_syms.append(sym)
            running += 1
            if running > peak:
                peak, peak_ts, peak_syms = running, ts, tuple(open_syms)
    return peak, peak_ts, peak_syms


def max_concurrent(trades: tuple[Trade, ...]) -> int:
    """The peak number of positions open at the same time across `trades`."""
    return _peak(trades)[0]


@dataclass(frozen=True)
class Ledger:
    """Enforces one cell's slot budget. `slots` is the funded concurrency (1 for time-series,
    K for cross-sectional top-K)."""

    slots: int

    def check(self, trades: tuple[Trade, ...]) -> int:
        """Assert the cell never held more than it funded. Returns the peak concurrency on
        success; raises `SlotBreach` (with the offending timestamp and names) otherwise."""
        peak, ts, syms = _peak(trades)
        if peak > self.slots:
            raise SlotBreach(
                f"cell held {peak} concurrent positions at {ts} "
                f"({', '.join(syms)}) but funded only {self.slots} slot(s)"
            )
        return peak
