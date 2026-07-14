/**
 * One-off backfill (FEAT-005): re-size every paper `Trade` row to the per-trade RISK CAP
 * introduced in apps/api/src/signals/signals.service.ts + apps/engine/strategies/base.py.
 *
 * Why: sizing used to be pure notional (`qty = floor(cellCapital × leverage / entry)`), so a
 * wide-stop trade risked multiples of a tight-stop one on the same fund — the payoff-ratio leak
 * (avg ₹-loss > avg ₹-win) in docs/agent-reports/2026-07-14-avg-loss-gt-avg-win-audit.md. The new
 * sizing also bounds rupee-risk: `qty = max(1, min(notionalQty, floor(cellCapital × pct / riskPerShare)))`.
 * This script restates the recorded history to that sizing so the equity curve / avg-win/loss the
 * owner reads are correct.
 *
 * Method (faithful):
 *   • Replay each (stock × strategy) CELL in entryTime order, compounding the RE-SIZED realized
 *     P&L into cellCapital exactly like the live path (cellCapital = max(₹10k + Σ cell realized, MIN)).
 *   • Size each trade off its PLANNED stop `originalStopLoss` (never the trailed `stopLoss` — a v1 bug).
 *   • P&L is linear in qty, so recover the real gross (gross = storedNetPnl + recomputedOldCost),
 *     scale it by k = newQty/oldQty, then RE-BOOK net costs on the new turnover (costs have fixed
 *     components — don't linearly scale them). `pnlPercent` is scale-invariant (left untouched).
 *
 * Rows with a null `originalStopLoss` or (for closed) null `exitPrice` are LEFT AS-IS (their stored
 * P&L still feeds the cell's compounding chain so later trades size correctly).
 *
 * Cost env MUST match the deployed config (defaults here mirror costs.ts / backtest_config.py).
 *
 * Usage (from repo root; tunnel the work-pc DB first: `ssh -N -L 5471:localhost:5471 work-pc &`):
 *   DATABASE_URL="postgresql://trader:trader@localhost:5471/smart_trading" \
 *     node node_modules/jiti/lib/jiti-cli.mjs apps/api/scripts/backfill-position-sizing.ts            # dry-run
 *   DATABASE_URL="postgresql://trader:trader@localhost:5471/smart_trading" \
 *     node node_modules/jiti/lib/jiti-cli.mjs apps/api/scripts/backfill-position-sizing.ts --apply    # writes (JSON backup first)
 */
import { PrismaClient } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";
import { Pool } from "pg";
import { writeFileSync } from "node:fs";
import { roundTripCost } from "../src/common/costs";

// ── Sizing constants — MUST mirror apps/api/src/common/risk.ts ───────────────
const BASE_CELL_CAPITAL = Number(process.env.BASE_CELL_CAPITAL || 10000);
const MIN_CELL_CAPITAL = Number(process.env.MIN_CELL_CAPITAL || 500);
const LEVERAGE_INTRADAY = Number(process.env.LEVERAGE_INTRADAY || 5);
const LEVERAGE_DELIVERY = Number(process.env.LEVERAGE_DELIVERY || 1);
const RISK_PER_TRADE_PCT = Number(process.env.RISK_PER_TRADE_PCT || 0.02);

const toNum = (x: unknown): number => (x == null ? 0 : Number(x));
const round2 = (n: number) => Math.round(n * 100) / 100;
const leverageFor = (h: string | null) => (h === "INTRADAY" ? LEVERAGE_INTRADAY : LEVERAGE_DELIVERY);

/** Capped qty — identical formula to signals.service.ts / base.py. */
function cappedQty(cellCapital: number, leverage: number, entry: number, riskPerShare: number): number {
  const notionalQty = entry > 0 ? Math.floor((cellCapital * leverage) / entry) : 1;
  const riskBudget = cellCapital * RISK_PER_TRADE_PCT;
  const riskCappedQty = riskPerShare > 0 ? Math.floor(riskBudget / riskPerShare) : notionalQty;
  return Math.max(1, Math.min(notionalQty, riskCappedQty));
}

/** Round-trip cost for a position of `qty` bought at `entry`, sold at `exit` (BUY vs SELL side). */
function costFor(qty: number, entry: number, exit: number, isBuy: boolean, hold: string | null): number {
  const buyValue = isBuy ? qty * entry : qty * exit;
  const sellValue = isBuy ? qty * exit : qty * entry;
  return roundTripCost(buyValue, sellValue, hold);
}

async function main() {
  const apply = process.argv.includes("--apply");
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is required");

  const pool = new Pool({ connectionString: url });
  const prisma = new PrismaClient({ adapter: new PrismaPg(pool) } as any);

  const trades = await prisma.trade.findMany({ orderBy: [{ entryTime: "asc" }, { id: "asc" }] });

  // Group by cell, preserving entryTime order.
  const cells = new Map<string, typeof trades>();
  for (const t of trades) {
    const key = `${t.stockId}|${t.strategyName}`;
    if (!cells.has(key)) cells.set(key, [] as any);
    (cells.get(key) as any).push(t);
  }

  type Change = {
    id: number; symbol: string; status: string; hold: string;
    oldQty: number; newQty: number; k: number;
    oldPnl: number | null; newPnl: number | null;
    update: Record<string, number>;
  };
  const changes: Change[] = [];
  const backup: unknown[] = [];
  let skippedNoStop = 0;

  for (const [, cellTrades] of cells) {
    let runningRealized = 0; // Σ re-sized realized P&L of this cell's CLOSED trades so far
    for (const t of cellTrades) {
      const isBuy = t.signalType === "BUY";
      const hold = t.holdDuration ?? null;
      const entry = toNum(t.entryPrice);
      const plannedStop = t.originalStopLoss == null ? null : toNum(t.originalStopLoss);
      const cellCapital = Math.max(BASE_CELL_CAPITAL + runningRealized, MIN_CELL_CAPITAL);
      const oldQty = t.quantity;
      const oldPnl = t.pnl == null ? null : toNum(t.pnl);

      // Can't re-size without a planned stop — leave the row, but keep the compounding chain.
      if (plannedStop == null) {
        skippedNoStop++;
        if (t.status === "CLOSED" && oldPnl != null) runningRealized += oldPnl;
        continue;
      }

      const riskPerShare = Math.abs(entry - plannedStop);
      const newQty = cappedQty(cellCapital, leverageFor(hold), entry, riskPerShare);
      const k = oldQty > 0 ? newQty / oldQty : 1;
      const newCapitalUsed = round2(newQty * entry);
      const newRiskAmount = round2(newQty * riskPerShare);

      let newPnl: number | null = null;
      const update: Record<string, number> = {
        quantity: newQty,
        capitalUsed: newCapitalUsed,
        riskAmount: newRiskAmount,
      };

      if (t.status === "CLOSED" && t.exitPrice != null && oldPnl != null) {
        const exit = toNum(t.exitPrice);
        // Recover real gross (incl. any partial legs) then rescale linearly + re-book net cost.
        const grossOld = oldPnl + costFor(oldQty, entry, exit, isBuy, hold);
        const grossNew = grossOld * k;
        newPnl = round2(grossNew - costFor(newQty, entry, exit, isBuy, hold));
        update.pnl = newPnl;
        update.realizedPnl = newPnl; // closed ⇒ realizedPnl == pnl (FEAT-002)
        update.remainingQty = 0;
        runningRealized += newPnl;
      } else if (t.status === "OPEN") {
        update.remainingQty = newQty; // no partials modelled on open rows
      } else if (oldPnl != null) {
        // Closed but missing exitPrice — leave P&L, feed compounding.
        runningRealized += oldPnl;
      }

      changes.push({
        id: t.id, symbol: t.symbol, status: t.status, hold: hold ?? "—",
        oldQty, newQty, k, oldPnl, newPnl, update,
      });
      backup.push(t);
    }
  }

  // ── Report ──────────────────────────────────────────────────────────────
  const inr = (n: number | null) => (n == null ? "—" : "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 }));
  const agg = (rows: { pnl: number | null }[]) => {
    const closed = rows.filter((r) => r.pnl != null) as { pnl: number }[];
    const wins = closed.filter((r) => r.pnl > 0);
    const losses = closed.filter((r) => r.pnl < 0);
    const sum = (a: { pnl: number }[]) => a.reduce((s, r) => s + r.pnl, 0);
    const avgW = wins.length ? sum(wins) / wins.length : 0;
    const avgL = losses.length ? sum(losses) / losses.length : 0;
    return {
      n: closed.length, net: sum(closed), avgW, avgL,
      payoff: avgL !== 0 ? avgW / Math.abs(avgL) : 0,
      pf: sum(losses) !== 0 ? sum(wins) / Math.abs(sum(losses)) : 0,
    };
  };
  const before = agg(changes.map((c) => ({ pnl: c.oldPnl })));
  const after = agg(changes.map((c) => ({ pnl: c.newPnl ?? c.oldPnl })));

  const resized = changes.filter((c) => c.newQty !== c.oldQty);
  console.log(`\nScanned ${trades.length} trades across ${cells.size} cells.`);
  console.log(`Re-sized ${resized.length}; unchanged qty ${changes.length - resized.length}; skipped (null originalStopLoss) ${skippedNoStop}.\n`);
  console.log("ID".padEnd(6) + "SYMBOL".padEnd(12) + "HOLD".padEnd(14) + "QTY".padStart(14) + "PNL".padStart(22));
  for (const c of resized) {
    console.log(
      String(c.id).padEnd(6) + c.symbol.slice(0, 11).padEnd(12) + c.hold.slice(0, 13).padEnd(14) +
      `${c.oldQty}→${c.newQty}`.padStart(14) + `${inr(c.oldPnl)}→${inr(c.newPnl)}`.padStart(22),
    );
  }
  const line = (l: string, a: ReturnType<typeof agg>) =>
    console.log(`  ${l.padEnd(7)} n=${a.n}  net=${inr(round2(a.net))}  avgWin=${inr(round2(a.avgW))}  avgLoss=${inr(round2(a.avgL))}  payoff=${a.payoff.toFixed(3)}  PF=${a.pf.toFixed(3)}`);
  console.log("\nClosed-trade aggregates:");
  line("BEFORE", before);
  line("AFTER", after);
  console.log(`\n  payoff ${before.payoff.toFixed(3)} → ${after.payoff.toFixed(3)}  (target ≥ 1.0)\n`);

  if (!apply) {
    console.log("DRY-RUN — no rows written. Re-run with --apply (writes a JSON backup first).");
    await prisma.$disconnect();
    return;
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const backupPath = `/tmp/backfill-position-sizing-backup-${stamp}.json`;
  writeFileSync(backupPath, JSON.stringify(backup, null, 2));
  console.log(`Backup of ${backup.length} pre-change rows → ${backupPath}`);

  let written = 0;
  for (const c of changes) {
    await prisma.trade.update({ where: { id: c.id }, data: c.update as any });
    written++;
  }
  console.log(`APPLIED — updated ${written} rows.`);
  await prisma.$disconnect();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
