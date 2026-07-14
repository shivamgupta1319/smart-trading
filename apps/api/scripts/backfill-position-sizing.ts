/**
 * One-off backfill: re-size existing paper `Trade` rows to the ₹1L per-trade notional cap.
 *
 * Background: before the fix in signals.service.ts, position size was `floor(₹2000 / stopDistance)`
 * with NO capital cap, so tight-stop high-priced stocks deployed multi-lakh notional on a ₹1L
 * account. This rescales every over-sized row to `min(riskBasedQty, floor(₹1L / entryPrice))`,
 * the exact formula the live path now uses. P&L is linear in quantity, so we scale pnl/realizedPnl
 * by the quantity ratio (pnlPercent is invariant and left untouched).
 *
 * Real-money DhanPosition rows are NOT touched — they were always independently notional-capped.
 *
 * Usage (from repo root, DB exposed on host port 5470 by docker-compose):
 *   DATABASE_URL="postgresql://trader:trader@localhost:5470/smart_trading" \
 *     node node_modules/jiti/lib/jiti-cli.mjs apps/api/scripts/backfill-position-sizing.ts          # dry-run
 *   DATABASE_URL="postgresql://trader:trader@localhost:5470/smart_trading" \
 *     node node_modules/jiti/lib/jiti-cli.mjs apps/api/scripts/backfill-position-sizing.ts --apply   # writes
 */
import { PrismaClient } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";
import { Pool } from "pg";
import { writeFileSync } from "node:fs";

// Must mirror the live sizing constants in apps/api/src/signals/signals.service.ts
const INITIAL_CAPITAL = 100000;
const RISK_PER_TRADE_PCT = 2;
const MAX_RISK_PER_TRADE = INITIAL_CAPITAL * (RISK_PER_TRADE_PCT / 100); // ₹2,000
const CAPITAL_PER_TRADE = INITIAL_CAPITAL; // ₹1,00,000 notional cap

const round2 = (n: number) => Math.round(n * 100) / 100;

/** Same formula as signals.service.ts create(): smaller of risk-based and notional-based qty. */
function correctQty(entryPrice: number, stopLoss: number): number {
  const riskPerShare = Math.abs(entryPrice - stopLoss);
  const riskBasedQty =
    riskPerShare > 0 ? Math.floor(MAX_RISK_PER_TRADE / riskPerShare) : Number.MAX_SAFE_INTEGER;
  const notionalCapQty = entryPrice > 0 ? Math.floor(CAPITAL_PER_TRADE / entryPrice) : 1;
  return Math.max(1, Math.min(riskBasedQty, notionalCapQty));
}

async function main() {
  const apply = process.argv.includes("--apply");
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is required");

  const pool = new Pool({ connectionString: url });
  const prisma = new PrismaClient({ adapter: new PrismaPg(pool) } as any);

  const trades = await prisma.trade.findMany({ orderBy: { id: "asc" } });

  const changes: {
    id: number;
    symbol: string;
    status: string;
    oldQty: number;
    newQty: number;
    oldCapital: number;
    newCapital: number;
    oldPnl: number | null;
    newPnl: number | null;
    update: Record<string, number>;
  }[] = [];
  const backup: unknown[] = [];

  let oldPnlTotal = 0;
  let newPnlTotal = 0;

  for (const t of trades) {
    if (t.pnl != null) oldPnlTotal += t.pnl;

    const newQty = correctQty(t.entryPrice, t.stopLoss);
    if (newQty >= t.quantity) {
      // Already within the cap — leave it, but still count its P&L toward the "new" total.
      if (t.pnl != null) newPnlTotal += t.pnl;
      continue;
    }

    const k = newQty / t.quantity; // linear scale factor
    const riskPerShare = Math.abs(t.entryPrice - t.stopLoss);
    const newCapitalUsed = round2(newQty * t.entryPrice);
    const newRiskAmount = round2(newQty * riskPerShare);
    const newRealizedPnl = round2(t.realizedPnl * k);
    const newRemainingQty =
      t.remainingQty > 0 ? Math.min(newQty, Math.max(1, Math.round(t.remainingQty * k))) : 0;
    const newPnl = t.pnl != null ? round2(t.pnl * k) : null;

    if (newPnl != null) newPnlTotal += newPnl;

    const update: Record<string, number> = {
      quantity: newQty,
      capitalUsed: newCapitalUsed,
      riskAmount: newRiskAmount,
      realizedPnl: newRealizedPnl,
      remainingQty: newRemainingQty,
    };
    if (newPnl != null) update.pnl = newPnl;
    // pnlPercent is invariant (pnl and capitalUsed both scale by k) — intentionally not updated.

    changes.push({
      id: t.id,
      symbol: t.symbol,
      status: t.status,
      oldQty: t.quantity,
      newQty,
      oldCapital: t.capitalUsed,
      newCapital: newCapitalUsed,
      oldPnl: t.pnl,
      newPnl,
      update,
    });
    backup.push(t);
  }

  // ── report ────────────────────────────────────────────────────────────────
  const inr = (n: number | null) =>
    n == null ? "—" : "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
  console.log(`\nScanned ${trades.length} trades — ${changes.length} over-sized (need rescale).\n`);
  console.log(
    "ID".padEnd(6) +
      "SYMBOL".padEnd(14) +
      "STATUS".padEnd(9) +
      "QTY".padStart(16) +
      "CAPITAL".padStart(24) +
      "PNL".padStart(22),
  );
  for (const c of changes) {
    console.log(
      String(c.id).padEnd(6) +
        c.symbol.slice(0, 13).padEnd(14) +
        c.status.padEnd(9) +
        `${c.oldQty}→${c.newQty}`.padStart(16) +
        `${inr(c.oldCapital)}→${inr(c.newCapital)}`.padStart(24) +
        `${inr(c.oldPnl)}→${inr(c.newPnl)}`.padStart(22),
    );
  }
  const maxCapAfter = trades.reduce((m, t) => {
    const c = changes.find((x) => x.id === t.id);
    return Math.max(m, c ? c.newCapital : t.capitalUsed);
  }, 0);
  console.log(
    `\nAll-time P&L: ${inr(round2(oldPnlTotal))} → ${inr(round2(newPnlTotal))}` +
      `  |  max capitalUsed after: ${inr(round2(maxCapAfter))}`,
  );

  if (!apply) {
    console.log("\nDRY-RUN — no rows written. Re-run with --apply to persist.\n");
    await prisma.$disconnect();
    await pool.end();
    return;
  }

  // ── apply ─────────────────────────────────────────────────────────────────
  const backupPath = `/tmp/claude-1000/-home-shivam-workspace-smart-trading/e9910d08-dce9-4b5d-b7ff-15a01db8aaee/scratchpad/trade-backup-before-resize.json`;
  writeFileSync(backupPath, JSON.stringify(backup, null, 2));
  console.log(`\nBackup of ${backup.length} original rows written to:\n  ${backupPath}\n`);

  await prisma.$transaction(
    changes.map((c) => prisma.trade.update({ where: { id: c.id }, data: c.update })),
  );
  console.log(`Applied ${changes.length} updates.\n`);

  await prisma.$disconnect();
  await pool.end();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
