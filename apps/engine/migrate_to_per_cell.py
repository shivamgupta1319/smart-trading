"""One-time data migration: re-express existing Trade history under the per-cell ₹10k
compounding-fund + leverage model (and long-only swing), IN PLACE — no reset, so all
history is kept but shown as if it had always used the new sizing.

Faithful because per-trade P&L is LINEAR in share count: the recorded entry/exit prices
(hence per-share P&L) are unchanged; only the share count is re-derived from each cell's
compounding ₹10k fund, and P&L scales with it.

Steps:
  1. Delete invalid swing/positional SELL trades (long-only rule) via LiveSignal cascade.
  2. Per (stockId, strategyName) cell, in entry-time order, re-size each trade:
        qty = max(1, floor(cellCapital × leverage / entry))   (intraday 5×, else 1×)
        capitalUsed = qty × entry ;  riskAmount = qty × |entry − stop|
        for CLOSED trades: pnl = qty × (old_pnl / old_qty), realizedPnl = pnl, remainingQty = 0
                           cellCapital = max(cellCapital + pnl, MIN_CELL_CAPITAL)
        for OPEN trades:   resize only (remainingQty = qty), no compounding yet
  Runs in a single transaction — safe to re-run (idempotent-ish: re-sizing already-migrated
  rows converges, but intended as a one-shot after a fresh DB backup).

Run inside the engine container AFTER `prisma migrate deploy`:
    docker exec smart-trading-v2-engine python migrate_to_per_cell.py
"""
import logging
from sqlalchemy import text
from db.client import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BASE_CELL_CAPITAL = 10000.0
MIN_CELL_CAPITAL = 500.0


def _leverage(hold_duration: str) -> float:
    return 5.0 if hold_duration == "INTRADAY" else 1.0


def main():
    with engine.begin() as conn:
        # 1. Long-only: drop swing/positional SELL trades (delete the LiveSignal → Trade cascades).
        deleted = conn.execute(text(
            """
            DELETE FROM "LiveSignal" ls
            USING "Trade" t
            WHERE t."signalId" = ls.id
              AND t."signalType" = 'SELL'
              AND t."holdDuration" <> 'INTRADAY'
            """
        )).rowcount
        logging.info(f"Deleted {deleted} invalid swing/positional SELL trades (long-only).")

        # 2. Re-size + recompute P&L per cell, in entry-time order.
        rows = conn.execute(text(
            """
            SELECT id, "stockId", "strategyName", "holdDuration",
                   "entryPrice", "stopLoss", quantity, pnl, status
            FROM "Trade"
            ORDER BY "stockId", "strategyName", "entryTime"
            """
        )).fetchall()

        cell_cap: dict = {}
        closed_updated = open_updated = 0
        for r in rows:
            key = (r.stockId, r.strategyName)
            cap = cell_cap.get(key, BASE_CELL_CAPITAL)
            lev = _leverage(r.holdDuration)
            entry = float(r.entryPrice)
            old_qty = r.quantity or 1
            new_qty = max(1, int((cap * lev) / entry)) if entry > 0 else 1
            new_capital = round(new_qty * entry, 2)
            new_risk = round(new_qty * abs(entry - float(r.stopLoss)), 2)

            if r.status == "CLOSED" and r.pnl is not None and old_qty > 0:
                pnl_per_share = float(r.pnl) / old_qty
                new_pnl = round(new_qty * pnl_per_share, 2)
                new_pnl_pct = round((new_pnl / new_capital) * 100, 4) if new_capital else 0.0
                conn.execute(text(
                    """
                    UPDATE "Trade"
                    SET quantity = :q, "capitalUsed" = :cap, "riskAmount" = :risk,
                        pnl = :pnl, "pnlPercent" = :pct, "realizedPnl" = :pnl, "remainingQty" = 0
                    WHERE id = :id
                    """
                ), {"q": new_qty, "cap": new_capital, "risk": new_risk, "pnl": new_pnl, "pct": new_pnl_pct, "id": r.id})
                cap = round(max(cap + new_pnl, MIN_CELL_CAPITAL), 2)
                closed_updated += 1
            else:
                conn.execute(text(
                    """
                    UPDATE "Trade"
                    SET quantity = :q, "capitalUsed" = :cap, "riskAmount" = :risk, "remainingQty" = :q
                    WHERE id = :id
                    """
                ), {"q": new_qty, "cap": new_capital, "risk": new_risk, "id": r.id})
                open_updated += 1

            cell_cap[key] = cap

        logging.info(
            f"Re-sized {closed_updated} closed + {open_updated} open trades across {len(cell_cap)} cells."
        )
    logging.info("Migration committed.")


if __name__ == "__main__":
    main()
