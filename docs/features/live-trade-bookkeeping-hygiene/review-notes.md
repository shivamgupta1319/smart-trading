# FEAT-002 — Live Trade Bookkeeping Hygiene · Review Notes

- **Reviewed:** 2026-06-17
- **Docs:** understanding.md, implementation_plan.md, tasks.md, verification.md (no
  architecture/ui-ux/edge_cases files — this is a focused 4-file set; edge cases folded in).

## Verdict: **REVISE → then APPROVE** (edits applied 2026-06-17; now ready to implement)

The scope is correct and small. Review against the actual code surfaced four concrete gaps;
all four have been folded into the docs and are reflected below. After these edits the
feature is ready to implement.

## Verified against code

- `Trade.riskAmount` **exists** ([schema.prisma](../../../apps/api/prisma/schema.prisma),
  `Decimal @default(0)`, "= (entry − SL) × quantity") — so the band's risk reference is
  real. **But it defaults to 0**, so `|pnl / riskAmount|` can divide by zero on any trade
  where it was never populated. Fallback to `capitalUsed`, then to an absolute ₹ floor.
- Two outcome formulas confirmed:
  [signals.service.ts:286](../../../apps/api/src/signals/signals.service.ts#L286) and
  [trades.service.ts:311](../../../apps/api/src/trades/trades.service.ts#L311) — AC #3 (shared
  helper) is justified.
- A **second** `totalPnl = realizedPnl + finalLotPnl` close path exists at
  [trades.service.ts:309](../../../apps/api/src/trades/trades.service.ts#L309) — Phase 2 must
  patch the realizedPnl write-back here too, not only in signals.service.ts.

## Gaps found (now fixed in docs)

1. **Win-rate denominator was mis-stated.** The doc's AC #2 assumed win-rate = `WIN/(WIN+LOSS)`.
   The live code computes `wins / fundedClosed.length`
   ([trades.service.ts:59-61](../../../apps/api/src/trades/trades.service.ts#L59-L61)) — i.e.
   **WIN ÷ all funded closed** (BREAKEVEN/LOSS in the denominator). There is a second site
   ([trades.service.ts:94-126](../../../apps/api/src/trades/trades.service.ts#L94-L126),
   per-strategy group) and the Telegram emoji at
   [telegram.service.ts:116](../../../apps/api/src/telegram/telegram.service.ts#L116).
   **Decision required and now recorded:** exclude BREAKEVEN from *both* numerator and
   denominator (`WIN/(WIN+LOSS)`). This is a behavior change — directional effect: removing
   the 3 scratch "wins" from the numerator *and* the 4 scratches from the denominator;
   net effect on the 52.5% headline must be measured, not assumed.
2. **riskAmount=0 / null not handled** — div-by-zero. Fallback chain added to understanding.md.
3. **realizedPnl scope clarified.** Account equity already sums `pnl`
   ([signals.service.ts:87](../../../apps/api/src/signals/signals.service.ts#L87)), so the
   realizedPnl fix is about making the *column* self-consistent (so the analyst's
   `SUM(realizedPnl)=SUM(pnl)` assertion passes) — it does **not** change displayed equity.
   This lowers Phase 2's risk and is now stated as scope.
4. **All win-rate consumers enumerated** in the plan so none is missed.

## Risks / open questions

- **Band value (0.1R) is a policy choice.** 0.1R on a tight intraday stop is a few rupees;
  on a wide swing stop it's larger. Confirm 0.1R is sensible across horizons or make it
  per-horizon. Left configurable (default 0.1) — acceptable for v1.
- **Backfill (Phase 3) rewrites recorded history.** Correctly gated on explicit approval +
  CSV snapshot. Recommend shipping Phases 1–2 first and deciding on backfill from the
  measured win-rate delta.
- **SHADOW trades:** outcome classification applies to them too, but win-rate uses only
  FUNDED closed — confirm that's intended (it is, per the slot model) and that SHADOW
  outcomes are still labelled correctly for research.

## Required doc edits before implementation — **DONE**

- [x] understanding.md: win-rate denominator decision + concrete sites; riskAmount=0 fallback;
      realizedPnl-scope clarification.
- [x] implementation_plan.md: enumerate all three win-rate/emoji sites; add the
      trades.service.ts:309 close path to Phase 2.
- [x] verification.md: reconcile AC #2 query to the chosen denominator; add a riskAmount=0 case.
- [x] tasks.md: reflect the above.

## Phase sizing

Phase 1 ~80–130 LOC, Phase 2 ~40–70 LOC, Phase 3 (optional) a script — all well under 500
and independently reviewable. ✓
