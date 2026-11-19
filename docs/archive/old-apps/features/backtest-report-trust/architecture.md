# FEAT-001 — Backtest Report Trust · Architecture (source of truth)

## Summary of the change

Make `BacktestReport` a **latest-per-cell** table by construction, fix the leaderboard to
read it that way with honest confidence, and apply the per-position notional cap so
single-cell ROI is bounded. Three independent slices (data → ranking → sizing).

## Data model

### `BacktestReport` (Prisma — `apps/api/prisma/schema.prisma`)

Current columns: `id, stockId, strategyName, timeframe, winRate, totalTrades, netProfit,
maxDrawdown, roiPercentage, createdAt`. No unique constraint → append-only duplication.

**Changes:**

```prisma
model BacktestReport {
  // ...existing columns...
  engineVersion String?  @default("unversioned") // stamp of the engine/config that produced this row
  updatedAt     DateTime @default(now())         // last recompute time (createdAt = first seen)

  @@unique([stockId, strategyName, timeframe])   // one row per cell — enables UPSERT
  @@index([stockId, strategyName])               // keep existing
}
```

> **Why `@default(now())` and NOT `@updatedAt`:** `BacktestReport` is written **only by the
> engine via raw SQL** (the API/Prisma never `create`s it — it only reads in
> [configs.service.ts:19](../../../apps/api/src/configs/configs.service.ts#L19)). Prisma's
> `@updatedAt` magic only fires on Prisma client writes, so it would never update here. The
> engine's UPSERT therefore sets `updatedAt = NOW()` **explicitly** on both insert and update.

- **`@@unique([stockId, strategyName, timeframe])`** is the keystone: it lets every writer
  `UPSERT` (INSERT … ON CONFLICT DO UPDATE) so the table is latest-per-cell automatically and
  every consumer becomes correct without per-query dedup.
- **`engineVersion`** = a short identifier the engine knows about itself (see below). Lets us
  detect "this cell was computed by an old engine" in future without re-introducing dupes.
- `createdAt` keeps its meaning (first time the cell was ever backtested); `updatedAt` is the
  latest recompute. The migration sets both to the surviving row's `createdAt`.

### Migration (raw SQL, applied to a clone first)

`apps/api/prisma/migrations/<ts>_backtest_report_latest_per_cell/migration.sql`:

1. Add `engineVersion`, `updatedAt` columns (nullable / defaulted).
2. **Collapse duplicates to latest:** delete all but the newest row per
   `(stockId, strategyName, timeframe)`. The tie-break on `id` is **inline, not optional** —
   batch runs can share a `createdAt`, and without it those dupes survive and the unique
   constraint in step 3 then fails:
   ```sql
   DELETE FROM "BacktestReport" a
   USING "BacktestReport" b
   WHERE a."stockId"=b."stockId" AND a."strategyName"=b."strategyName"
     AND a.timeframe=b.timeframe
     AND (a."createdAt" < b."createdAt"
          OR (a."createdAt" = b."createdAt" AND a.id < b.id));
   ```
   After this, assert `SELECT count(*) = count(DISTINCT (stockId,strategyName,timeframe))`
   **before** adding the constraint.
3. Add the unique constraint (now safe — duplicates are gone).
4. Optional: drop `totalTrades = 0` rows (empty-strategy noise, F5) — **gated behind review**;
   default is to *keep but exclude in aggregates* (less destructive).

> A baseline migration that includes the `Trade` table is a known pre-existing gap (system
> review H3) — **not** in scope here; this migration is additive and self-contained.

## Engine version identity

A single source: `apps/engine/backtest_config.py` exposes
`ENGINE_VERSION = os.getenv("BT_ENGINE_VERSION", "<git-short-sha-or-semver>")`. Both writers
stamp it. Bumping it is a manual, deliberate act when the fill/sizing math changes — so a
future "version mismatch" is greppable. (We do **not** auto-recompute on mismatch in this
feature; that's a possible follow-up.)

## Write path (both writers UPSERT)

`save_report()` in [backtest.py:50-62](../../../apps/engine/routers/backtest.py#L50-L62) and
the equivalent in [auto_select.py:130-141](../../../apps/engine/routers/auto_select.py#L130-L141)
change from `INSERT` to:

```sql
INSERT INTO "BacktestReport"
  ("stockId","strategyName","timeframe","winRate","totalTrades","maxDrawdown",
   "netProfit","roiPercentage","engineVersion","createdAt","updatedAt")
VALUES (:sid,:sn,:tf,:wr,:tt,:md,:np,:roi,:ev,NOW(),NOW())
ON CONFLICT ("stockId","strategyName","timeframe") DO UPDATE SET
  "winRate"=EXCLUDED."winRate", "totalTrades"=EXCLUDED."totalTrades",
  "maxDrawdown"=EXCLUDED."maxDrawdown", "netProfit"=EXCLUDED."netProfit",
  "roiPercentage"=EXCLUDED."roiPercentage", "engineVersion"=EXCLUDED."engineVersion",
  "updatedAt"=NOW();
```

The two writers share one helper (extract `save_report` to a common module imported by both,
removing the current duplication) — a small reuse win called out in the system review (LOW).

## Read path — leaderboard

`/leaderboard` in [advanced_backtest.py:21-59](../../../apps/engine/routers/advanced_backtest.py#L21-L59).
After the table is latest-per-cell, the existing `GROUP BY strategyName` becomes *correct by
construction* (one row per cell). Remaining fixes:

- **Exclude empties:** `WHERE "totalTrades" > 0`.
- **Confidence on distinct cells:** today `confidence = reports/10`; `reports` is now the
  count of distinct cells (since dupes are gone), which is the intended meaning — keep the
  formula but document that it now counts *symbols backing the strategy*, not re-runs.
- No change to the Calmar-like score itself.

`configs.service.ts` ([19-30](../../../apps/api/src/configs/configs.service.ts#L19-L30)) already
dedupes in app code; once the table is unique-per-cell its `latestByKey` map becomes a no-op
(each key has one row). **Leave it as-is** (harmless, defensive) — no change needed.

## Sizing model — `strategies/base.py`

Per the **Key decision** in [understanding.md](understanding.md), implement the option chosen
at the review gate. Recommended (A): in `simulate()`
([base.py:127-233](../../../apps/engine/strategies/base.py#L127-L233)), replace the
compounding `current_capital` sizing with a **fixed slot capped at `RISK.max_position_value`**:

```python
slot = RISK.slot_capital
qty = max(1, int(min(slot, RISK.max_position_value) / entry))
```

and compute ROI/drawdown against the fixed `slot` rather than a running compounded balance.
This activates the previously-dead `max_position_value` cap and bounds single-cell ROI.
(Option B keeps `current_capital` compounding but wraps the `qty` numerator in
`min(current_capital, RISK.max_position_value)`.)

The metrics math in `_metrics()` already divides ROI by `slot_capital`, so with fixed-slot
sizing ROI is naturally bounded; the `max_dd_pct` peak-relative logic still holds.

## Component / file map

| File | Change | Slice |
|------|--------|-------|
| `apps/api/prisma/schema.prisma` | add `engineVersion`, `updatedAt`, `@@unique` | P1 |
| `apps/api/prisma/migrations/<ts>_.../migration.sql` | collapse dupes + add constraint | P1 |
| `apps/engine/backtest_config.py` | `ENGINE_VERSION` constant | P1 |
| `apps/engine/routers/backtest.py` | `save_report` → shared UPSERT helper | P1 |
| `apps/engine/routers/auto_select.py` | use shared UPSERT helper | P1 |
| `apps/engine/routers/advanced_backtest.py` | exclude empties; confidence semantics | P2 |
| `apps/engine/strategies/base.py` | apply notional cap / sizing model | P3 |
| `apps/engine/test/test_backtest_engine.py` | new assertions (idempotency, cap) | P1–P3 |

## Backwards compatibility

- API response shapes are unchanged (same JSON keys). `engineVersion`/`updatedAt` are
  additive and not required by the frontend.
- After the sizing fix, **reported ROI numbers will drop** for previously-compounding cells.
  This is intended (they were wrong) and must be called out in the rollout notes so the user
  isn't surprised that "the leaderboard got less rosy."
