"""Point-in-time universe tests: the survivorship guarantee, on a synthetic reconstitution log.

The load-bearing test is `test_a_departed_name_is_a_member_only_while_it_belonged`: a name that
left the index in a later review must appear in an earlier query and in `ever_members()`, and must
NOT appear after it left. That is exactly the property that stops us deleting past losers and
ranking only the winners -- the R3 failure. The reconstruction is pure logic (no network), so it
is fully pinned here; the live constituent fetch has its own guarded smoke test.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from trading.data.universe import MembershipChange, Universe, load_universe


def change(eff, added=(), removed=(), source="NSE circular"):
    return MembershipChange(
        effective_date=date.fromisoformat(eff),
        added=frozenset(added),
        removed=frozenset(removed),
        source=source,
    )


def a_universe():
    """Anchor of {A,B,C,D} as of 2026-01-01, with two prior reconstitutions:
    - 2025-04-01: X left, A joined.
    - 2023-04-01: Y left, B joined.
    So before 2023 the members were {C, D, X, Y}; X and Y are departed names."""
    return Universe(
        anchor_date="2026-01-01",
        anchor_symbols={"A", "B", "C", "D"},
        changes=[
            change("2025-04-01", added=["A"], removed=["X"]),
            change("2023-04-01", added=["B"], removed=["Y"]),
        ],
    )


class TestReconstruction:
    def test_at_the_anchor_the_members_are_the_anchor(self):
        assert a_universe().members_as_of("2026-01-01") == {"A", "B", "C", "D"}

    def test_between_the_two_changes(self):
        # After 2025-04-01 A is in, X is out; B is still in (joined 2023). -> {A,B,C,D}
        assert a_universe().members_as_of("2025-06-01") == {"A", "B", "C", "D"}
        # Just before 2025-04-01: undo that change -> A not yet in, X still in -> {B,C,D,X}
        assert a_universe().members_as_of("2025-01-01") == {"B", "C", "D", "X"}

    def test_before_all_changes(self):
        # Before 2023-04-01: undo both -> A,B not yet in; X,Y still in -> {C,D,X,Y}
        assert a_universe().members_as_of("2022-01-01") == {"C", "D", "X", "Y"}

    def test_a_change_is_in_force_on_its_effective_date(self):
        # On 2025-04-01 itself the change is live: A in, X out.
        assert "A" in a_universe().members_as_of("2025-04-01")
        assert "X" not in a_universe().members_as_of("2025-04-01")

    def test_accepts_timestamp_and_date_inputs(self):
        u = a_universe()
        assert u.members_as_of(pd.Timestamp("2022-06-01")) == u.members_as_of(date(2022, 6, 1))


class TestSurvivorship:
    def test_a_departed_name_is_a_member_only_while_it_belonged(self):
        """THE test. X was removed on 2025-04-01. It must be a member before then, absent after,
        and -- the part that kills survivorship -- present in ever_members() so its prices are
        fetched and it competes for the ranking during the years it was in the index."""
        u = a_universe()
        assert "X" in u.members_as_of("2024-01-01")  # X was in the index then
        assert "X" not in u.members_as_of("2025-06-01")  # and gone after it left
        assert "X" in u.ever_members()  # NOT deleted from history -> no survivorship

    def test_ever_members_is_the_full_cast(self):
        # Everyone who was ever in: anchor {A,B,C,D} plus the departed X, Y.
        assert a_universe().ever_members() == {"A", "B", "C", "D", "X", "Y"}

    def test_todays_list_alone_would_hide_the_losers(self):
        # The anchor (today's members) omits X and Y entirely -- ranking on it manufactures
        # momentum. ever_members() restores them; that difference IS the bias.
        u = a_universe()
        assert u.ever_members() - u.anchor_symbols == {"X", "Y"}


class TestValidation:
    def test_a_change_after_the_anchor_is_rejected(self):
        with pytest.raises(ValueError, match="after the anchor"):
            Universe("2020-01-01", {"A"}, [change("2021-04-01", added=["B"])])

    def test_querying_past_the_anchor_is_rejected(self):
        with pytest.raises(ValueError, match="after the anchor"):
            a_universe().members_as_of("2027-01-01")

    def test_duplicate_effective_dates_are_rejected(self):
        with pytest.raises(ValueError, match="share an effective_date"):
            Universe(
                "2026-01-01",
                {"A"},
                [change("2025-04-01", added=["B"]), change("2025-04-01", removed=["C"])],
            )

    def test_added_and_removed_cannot_overlap(self):
        with pytest.raises(ValueError, match="both added and removed"):
            change("2025-04-01", added=["A"], removed=["A"])

    def test_a_change_must_cite_a_source(self):
        with pytest.raises(ValueError, match="cite its source"):
            change("2025-04-01", added=["A"], source="")

    def test_empty_anchor_is_rejected(self):
        with pytest.raises(ValueError, match="anchor constituent list is empty"):
            Universe("2026-01-01", [], [])


class TestConfigLoader:
    def test_shipped_config_loads_the_populated_anchor(self):
        # The anchor is populated (200 real NIFTY-200 names, fetched 2026-07-16). The change log is
        # still empty, so members_as_of() returns the anchor unchanged -- documented as NOT yet
        # survivorship-safe until the reconstitution events are entered.
        u = load_universe()
        assert len(u.anchor_symbols) == 200
        assert "RELIANCE" in u.anchor_symbols
        assert u.covered_from is None  # no reconstitution events yet

    def test_empty_anchor_config_raises(self, tmp_path):
        # A config with an empty anchor must fail loudly, never silently return an empty universe.
        p = tmp_path / "empty.yaml"
        p.write_text("anchor:\n  as_of: 2026-01-01\n  symbols: []\nchanges: []\n")
        with pytest.raises(ValueError, match="non-empty anchor.symbols"):
            load_universe(p)

    def test_loads_a_populated_file(self, tmp_path):
        p = tmp_path / "u.yaml"
        p.write_text(
            "anchor:\n"
            "  as_of: 2026-01-01\n"
            "  source: test\n"
            "  symbols: [A, B, C, D]\n"
            "changes:\n"
            "  - effective_date: 2025-04-01\n"
            "    added: [A]\n"
            "    removed: [X]\n"
            "    source: NSE circular\n"
        )
        u = load_universe(p)
        assert u.members_as_of("2024-01-01") == {"B", "C", "D", "X"}
        assert "X" in u.ever_members()
