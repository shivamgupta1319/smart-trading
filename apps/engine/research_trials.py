"""The trials ledger: an append-only record of every strategy evaluation ever run.

Brought over from the July rebuild (`trading/research/trials.py`).

The Deflated Sharpe Ratio and BH-FDR both need N, the number of trials. N is the whole game: the
earlier apps ran 1,860 cells and corrected for none. The danger in *any* correction is that N is
whatever the person reporting it says it is -- and the temptation to quietly shrink it (to make the
best strategy look less lucky) is exactly the temptation this project exists to resist.

So N is not a number anyone types. It is `len(TrialsLedger.read())`. The ledger is **append-only,
written by the runner** as each evaluation completes; understating N therefore requires *deleting
lines from a file on disk* -- a deliberate, visible act, not a quiet omission. The backtest tool writes it
next to its output file.

**A trial is a strategy × variant**, not a cell: the hypothesis under test is the
strategy, so its cells are aggregated to one return series before it is recorded once. `sharpes()`
returns the per-trial Sharpes to feed straight into `deflated_sharpe_ratio`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Trial:
    """One evaluated strategy variant. `timestamp` is supplied by the caller (ISO-8601) so the
    ledger has no hidden clock -- the runner stamps it, the tests pin it."""

    strategy: str
    variant: str  # the parameter combination, e.g. "lookback=12,skip=1"
    instrument_set: str  # "RELIANCE" | "NIFTY200"
    sharpe: float
    n_obs: int
    timestamp: str

    @property
    def key(self) -> tuple[str, str, str]:
        """Identity of the hypothesis: strategy × variant × instrument set."""
        return (self.strategy, self.variant, self.instrument_set)


class TrialsLedger:
    """Append-only JSONL at `path`. Opened per-write so a crash mid-run cannot corrupt earlier
    lines, and so N is always exactly what is durably on disk."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def record(self, trial: Trial) -> None:
        """Append one trial. The runner calls this as each evaluation finishes; nothing rewrites
        or de-duplicates -- a re-run is a new trial and legitimately raises N."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(trial), sort_keys=True) + "\n")

    def read(self) -> list[Trial]:
        """Every trial on disk, in the order recorded. Empty (not an error) when nothing has run."""
        if not self.path.exists():
            return []
        trials = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    trials.append(Trial(**json.loads(line)))
        return trials

    def n_trials(self) -> int:
        """N for the multiple-testing correction -- the count of durable trials, nothing else."""
        return len(self.read())

    def sharpes(self) -> list[float]:
        """The per-trial Sharpes, to feed `deflated_sharpe_ratio`."""
        return [t.sharpe for t in self.read()]
