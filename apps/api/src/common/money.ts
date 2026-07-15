/**
 * Money helpers. Ledger columns are stored as Postgres NUMERIC (Prisma
 * `Decimal`) to avoid IEEE-754 drift. Prisma returns those as `Prisma.Decimal`
 * objects, so we normalize to plain `number` at the read boundary and do the
 * (integer-share) arithmetic in JS, rounding to paise on write.
 */

type DecimalLike = { toNumber: () => number } | number | string | null | undefined;

/** Convert a Prisma.Decimal | number | string | null to a finite number. */
export function toNum(v: DecimalLike): number {
  if (v == null) return 0;
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0;
  if (typeof v === 'string') {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }
  if (typeof (v as { toNumber?: unknown }).toNumber === 'function') {
    const n = (v as { toNumber: () => number }).toNumber();
    return Number.isFinite(n) ? n : 0;
  }
  return 0;
}

/** Round to 2 decimal places (paise). */
export function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

/** Safe percentage: returns 0 when the denominator is 0/invalid (no NaN/Infinity). */
export function safePct(numerator: number, denominator: number): number {
  if (!denominator || !Number.isFinite(denominator)) return 0;
  const pct = (numerator / denominator) * 100;
  return Number.isFinite(pct) ? pct : 0;
}

const MONEY_FIELDS = [
  'entryPrice', 'exitPrice', 'stopLoss', 'target',
  'capitalUsed', 'riskAmount', 'pnl', 'pnlPercent',
  'originalStopLoss', 'peakPrice', 'realizedPnl',
] as const;

/**
 * Returns a shallow copy of a Trade with all Decimal money fields coerced to
 * plain numbers, so downstream arithmetic is ordinary JS-number math. Call this
 * immediately after loading a trade from Prisma.
 */
export function normalizeTradeMoney<T extends Record<string, unknown>>(trade: T | null): T | null {
  if (!trade) return trade;
  const out: Record<string, unknown> = { ...trade };
  for (const f of MONEY_FIELDS) {
    if (f in out && out[f] != null) out[f] = toNum(out[f] as DecimalLike);
  }
  return out as T;
}
