# FEAT-002 — Live Trade Bookkeeping Hygiene · Implementation Plan

Two small vertical slices, each independently shippable and verifiable, each well under
500 LOC. Both are pure correctness fixes in the API layer — no engine, no strategy logic.
Each phase is its own branch + PR off `roadmap-v2`. Work against the DB clone per
[v2-environment.md](../../v2-environment.md); never touch the running stack until promotion.

---

## Phase 1 — BREAKEVEN band on outcome classification

**Goal:** sub-band scratches classify as `BREAKEVEN`; win-rate stops counting them.

1. Add a shared helper `classifyOutcome(pnl, riskRef): "WIN" | "LOSS" | "BREAKEVEN"`
   (e.g. in a small `trades/outcome.util.ts`) implementing
   `|pnl / riskRef| < BREAKEVEN_R ? "BREAKEVEN" : pnl > 0 ? "WIN" : "LOSS"`.
   `riskRef` resolves `riskAmount` → `capitalUsed` (if `riskAmount` is 0/null, the schema
   default) → ₹ floor. **The 0-default fallback is mandatory** (div-by-zero guard).
2. Replace the inline ternary at
   [signals.service.ts:286](../../../apps/api/src/signals/signals.service.ts#L286) and
   [trades.service.ts:311](../../../apps/api/src/trades/trades.service.ts#L311) with the
   helper so the two cannot drift.
3. Make `BREAKEVEN_R` configurable (constant + env override, default 0.1).
4. Update **all three** win-rate consumers to `WIN / (WIN + LOSS)` (BREAKEVEN excluded
   from numerator and denominator):
   [trades.service.ts:59-61](../../../apps/api/src/trades/trades.service.ts#L59-L61)
   (portfolio), [trades.service.ts:94-126](../../../apps/api/src/trades/trades.service.ts#L94-L126)
   (per-strategy group). The Telegram emoji
   [telegram.service.ts:116](../../../apps/api/src/telegram/telegram.service.ts#L116) is
   display-only (already maps non-WIN/LOSS to ➖) — verify, no math change.
5. Tests: a +0.04R close → BREAKEVEN; a −0.114R close → BREAKEVEN; a +1.0R close → WIN;
   a −1.0R close → LOSS; a `riskAmount=0` close uses fallback and does not divide by zero;
   win-rate excludes BREAKEVEN from both numerator and denominator.

**Done when:** AC #1, #2, #3, #5. ~60–120 LOC incl. tests.

---

## Phase 2 — Reconcile `realizedPnl` to `pnl` (decision A)

**Goal:** `realizedPnl` includes the final leg so it reconciles to `pnl`.

1. In the full-close path
   ([signals.service.ts:288-304](../../../apps/api/src/signals/signals.service.ts#L288-L304)),
   also write `realizedPnl: round2(totalPnl)` in the same `update`.
2. Patch the **second** close path at
   [trades.service.ts:309](../../../apps/api/src/trades/trades.service.ts#L309) (same
   `totalPnl = realizedPnl + finalLotPnl` shape) — it must write `realizedPnl` back too.
   Also confirm `closeTradePartial`'s FULL-close branch at
   [signals.service.ts:233-243](../../../apps/api/src/signals/signals.service.ts#L233-L243)
   delegates to `closeWithPrice` and thus inherits the fix.
3. Tests: open → full close with no partial ⇒ `realizedPnl === pnl`; open → partial →
   full close ⇒ `realizedPnl === pnl === partialLeg + finalLeg`.

**Done when:** AC #4. ~30–60 LOC incl. tests. Independent of Phase 1.

---

## Phase 3 (optional) — One-time backfill of historical rows

**Goal:** make already-closed trades consistent with the new rules, if the user wants
historical reports corrected (not just new trades).

1. Hand-written, reviewed SQL/script: recompute `outcome` via the band and set
   `realizedPnl = pnl` for CLOSED trades. Apply to the **clone** first; snapshot to CSV.
2. Record the win-rate delta (expected to drop from 52.5%) and confirm
   `SUM(realizedPnl)=SUM(pnl)` post-backfill.

**Done when:** AC #6. Gate on explicit user approval — backfill rewrites recorded history.

---

## Sequencing & rollback

```
review-docs → Phase 1 (PR) → verify → Phase 2 (PR) → verify → [Phase 3 if approved] → verify-feature
```

- Phases 1 and 2 are independent and could be parallel PRs.
- Each phase is a single-PR revert. Phase 3 is the only non-trivial rollback (rewrites
  rows) — CSV snapshot first; restore from snapshot if needed.
