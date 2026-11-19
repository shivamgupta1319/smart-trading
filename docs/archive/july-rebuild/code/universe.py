"""Point-in-time index membership -- the fix for R3, the #1 way this project makes a wrong YES.

The universe we backtest must be the set of names that were index members *as of each past date*,
not today's members projected backward. The 60-name list we inherited was picked today by
liquidity, and a name is liquid today partly *because it went up* -- so ranking today's winners
over 2020-26 manufactures momentum out of nothing. Cross-sectional momentum is exactly the
strategy this bias flatters, so it is the strategy this module exists to protect.

The reconstruction is a backward walk. We anchor on the CURRENT constituent list (a known set at a
known date) and unwind the index's semi-annual reconstitutions: each event records what was ADDED
and REMOVED on its effective date, with a source. To get the members as of an earlier date D, undo
every event that took effect after D -- drop the names that were added later (they were not members
yet) and restore the names that were removed later (they still were).

**The property that kills survivorship: `ever_members()`.** A name that LEFT the index in 2023 is a
member in a 2022 query and absent from a 2024 one -- and, critically, it is in `ever_members()`, so
its prices get fetched and it competes for the ranking in 2022 exactly as it did in life. Leaving it
out (the survivorship trap) would silently delete every past loser and leave only the winners.

This module is the machinery and the format; the data itself (the current 200 list plus the
reconstitution log) is a sourced, human-curated file like `known_actions.yaml` -- every event is a
claim someone stands behind, with the NSE circular that backs it. `fetch_current_constituents`
pulls the anchor list; the change log is entered from NSE's reconstitution notices.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yaml

_CONFIG = Path(__file__).resolve().parents[3] / "config" / "universe" / "nifty200.yaml"
_NIFTY200_CSV = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"


def _as_date(value: object) -> date:
    """Coerce a date-like (date, datetime, Timestamp, ISO string) to a plain date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"cannot read a date from {value!r} ({type(value).__name__})")


@dataclass(frozen=True)
class MembershipChange:
    """One index reconstitution: the names that joined and left on `effective_date`. `source` is
    the NSE circular (or equivalent) that backs it -- an unsourced change is not admissible."""

    effective_date: date
    added: frozenset[str]
    removed: frozenset[str]
    source: str

    def __post_init__(self) -> None:
        overlap = self.added & self.removed
        if overlap:
            raise ValueError(
                f"{self.effective_date}: {sorted(overlap)} both added and removed in one event"
            )
        if not self.source:
            raise ValueError(f"{self.effective_date}: a change must cite its source")


class Universe:
    """Effective-dated index membership, reconstructed by unwinding reconstitutions from a current
    anchor. Query with `members_as_of(date)`; fetch prices for `ever_members()`."""

    def __init__(
        self,
        anchor_date: object,
        anchor_symbols: Iterable[str],
        changes: Iterable[MembershipChange],
    ):
        self.anchor_date = _as_date(anchor_date)
        self.anchor_symbols = frozenset(anchor_symbols)
        # Newest first: we unwind the most recent change before the ones before it.
        self.changes = tuple(sorted(changes, key=lambda c: c.effective_date, reverse=True))

        if not self.anchor_symbols:
            raise ValueError("the anchor constituent list is empty")
        dates = [c.effective_date for c in self.changes]
        if len(set(dates)) != len(dates):
            raise ValueError("two reconstitution changes share an effective_date; merge them")
        future = [d for d in dates if d > self.anchor_date]
        if future:
            raise ValueError(
                f"changes {future} are dated after the anchor {self.anchor_date}; the anchor must "
                "be the most recent known membership (we cannot unwind the future)"
            )

    def members_as_of(self, when: object) -> frozenset[str]:
        """The index constituents as of `when`. Undo every reconstitution effective strictly after
        `when` (a change effective ON `when` is already in force that day)."""
        d = _as_date(when)
        if d > self.anchor_date:
            raise ValueError(
                f"{d} is after the anchor {self.anchor_date}; membership past the anchor is unknown"
            )
        members = set(self.anchor_symbols)
        for change in self.changes:  # newest first
            if change.effective_date > d:
                members -= change.added  # not a member yet at `d`
                members |= change.removed  # still a member at `d`
        return frozenset(members)

    def ever_members(self) -> frozenset[str]:
        """Every name that was a member at any point in the covered span -- the anchor plus every
        name ever added or removed. This is the set to fetch prices for; dropping the names that
        later left is precisely the survivorship bias R3 is about."""
        names = set(self.anchor_symbols)
        for change in self.changes:
            names |= change.added
            names |= change.removed
        return frozenset(names)

    @property
    def covered_from(self) -> date | None:
        """Effective date of the earliest reconstitution -- membership queried before this is just
        the anchor unwound as far as the log goes, so treat earlier dates as lower-confidence."""
        return self.changes[-1].effective_date if self.changes else None


def load_universe(path: Path | None = None) -> Universe:
    """Load the sourced membership file. Shape:

    anchor: {as_of: YYYY-MM-DD, symbols: [...], source: "..."}
    changes:
      - {effective_date: YYYY-MM-DD, added: [...], removed: [...], source: "..."}
    """
    with open(path or _CONFIG) as f:
        raw = yaml.safe_load(f) or {}
    anchor = raw.get("anchor") or {}
    if "as_of" not in anchor or not anchor.get("symbols"):
        raise ValueError(
            f"{path or _CONFIG}: needs anchor.as_of and a non-empty anchor.symbols "
            "(the current constituent list -- see fetch_current_constituents)"
        )
    changes = [
        MembershipChange(
            effective_date=_as_date(c["effective_date"]),
            added=frozenset(c.get("added", [])),
            removed=frozenset(c.get("removed", [])),
            source=c.get("source", ""),
        )
        for c in raw.get("changes", [])
    ]
    return Universe(anchor["as_of"], anchor["symbols"], changes)


def fetch_current_constituents(url: str = _NIFTY200_CSV) -> list[str]:
    """Pull the current NIFTY-200 constituent symbols to seed the anchor. niftyindices.com serves
    the CSV only to a browser-like client (V2's seed_nse.py learned the same for NSE archives), so
    a User-Agent is required -- without it the request hangs or is refused. Network-only; the
    reconstruction logic above needs no network and is what the tests pin."""
    import io

    import requests

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    col = next((c for c in df.columns if c.strip().lower() == "symbol"), None)
    if col is None:
        raise ValueError(f"no 'Symbol' column in {url}; got {list(df.columns)}")
    return [s.strip().upper() for s in df[col].dropna()]
