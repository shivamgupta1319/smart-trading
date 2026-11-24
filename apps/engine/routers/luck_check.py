"""Luck check: is any strategy's backtest more than chance? See `luck_check.py`."""
from fastapi import APIRouter, HTTPException

import luck_check
import strategy_map
import switch_rules

router = APIRouter()


@router.get("/luck-check")
def get_luck_check():
    """The latest stored run, or {"run": null} when none has been computed yet."""
    return {"run": luck_check.latest()}


@router.get("/strategy-map")
def get_strategy_map():
    """Where each strategy works: broadly, on particular stocks, or nowhere."""
    return strategy_map.latest()


@router.get("/switch-rules")
def get_switch_rules():
    """The market-condition rule table: how each strategy did in each NIFTY regime."""
    return switch_rules.latest()


@router.post("/luck-check/run")
def run_luck_check():
    """Recompute on stored candles (about a minute) and store the result."""
    run = luck_check.run_and_store()
    if run is None:
        raise HTTPException(status_code=409, detail="A luck check is already running. Try again in a minute.")
    return {"run": run}
