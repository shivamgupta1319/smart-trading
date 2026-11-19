"""Settings shared with the NestJS API — read from config/trading.json.

Every constant the two runtimes must agree on (fund size, leverage, risk cap,
transaction costs) used to be typed twice, once in Python and once in TypeScript,
held together by "MUST match" comments. One copy had already gone stale. Both
sides now read the same file; `apps/api/src/common/shared-config.ts` is the twin.

Lookup order for a value: environment variable of the same name → the file.
There is no third, in-code default: a missing key is an error at start-up.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _candidates() -> list[Path]:
    paths = []
    if os.getenv("TRADING_CONFIG_PATH"):
        paths.append(Path(os.environ["TRADING_CONFIG_PATH"]))
    paths.append(_HERE / "config" / "trading.json")              # inside the image (/app/config)
    if len(_HERE.parents) > 1:                                    # repo checkout (apps/engine → root)
        paths.append(_HERE.parents[1] / "config" / "trading.json")
    return paths


@lru_cache(maxsize=1)
def _values() -> dict[str, float]:
    for path in _candidates():
        if path.is_file():
            raw = json.loads(path.read_text())
            flat: dict[str, float] = {}
            for section, body in raw.items():
                if isinstance(body, dict):
                    flat.update(body)
            return flat
    tried = ", ".join(str(p) for p in _candidates())
    raise FileNotFoundError(f"config/trading.json not found (tried: {tried})")


def shared(name: str) -> float:
    """A shared setting as a float: env override first, else the file."""
    env = os.getenv(name)
    if env not in (None, ""):
        try:
            return float(env)
        except ValueError as exc:
            raise ValueError(f"{name}={env!r} is not a number") from exc
    try:
        return float(_values()[name])
    except KeyError as exc:
        raise KeyError(f"{name} is not defined in config/trading.json") from exc


def risk_per_trade_fraction() -> float:
    """RISK_PER_TRADE_PCT as a fraction, refusing a percent-style value.

    `RISK_PER_TRADE_PCT=2` (meant as 2%) used to be read as 200% of the fund,
    which silently switched the risk cap off. Fail loudly instead.
    """
    value = shared("RISK_PER_TRADE_PCT")
    if not 0 < value <= 0.2:
        raise ValueError(
            f"RISK_PER_TRADE_PCT={value} must be a fraction of the fund between 0 and 0.2 "
            "(0.02 means 2%). A value like 2 would disable the risk cap."
        )
    return value
