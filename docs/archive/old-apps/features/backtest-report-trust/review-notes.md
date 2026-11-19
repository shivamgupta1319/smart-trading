# FEAT-001 — Backtest Report Trust · Review Notes (Phase 2)

**Reviewed:** 2026-06-12 · **Reviewer:** Claude (verified against the codebase + live clone DB)

## Summary verdict: ✅ APPROVE (required edits applied during review)

The docs are accurate, internally consistent, and grounded in **verified** root causes (not
the analyst agent's mistaken "non-deterministic engine" claim, which this review chain already
rejected). Scope is a correctness fix, correctly split into three ≤500-LOC slices. The four
issues found during review were small and have been fixed in-place; none block implementation.

## What was checked against the actual code

| Claim in docs | Verified? |
|---|---|
| `save_report` always INSERTs ([backtest.py:50](../../../apps/engine/routers/backtest.py#L50), [auto_select.py:130](../../../apps/engine/routers/auto_select.py#L130)) | ✅ |
| Leaderboard averages all rows, no dedup ([advanced_backtest.py:21-59](../../../apps/engine/routers/advanced_backtest.py#L21-L59)) | ✅ |
| Monitored-stocks view already dedupes to latest-per-cell ([configs.service.ts:19-30](../../../apps/api/src/configs/configs.service.ts#L19-L30)) | ✅ |
| `max_position_value` is dead code, never applied ([base.py:161](../../../apps/engine/strategies/base.py#L161), [backtest_config.py:59-61](../../../apps/engine/backtest_config.py#L59-L61)) | ✅ |
| Baseline numbers: 1363 rows / 323 cells; avg ROI 26.96 → 15.00 deduped | ✅ (re-queried) |
| Engine is deterministic (six identical consecutive runs) | ✅ |
| Repo uses hand-authored timestamped migrations (not `db push`) | ✅ — 4 migrations present; `…000000_…` convention matches the plan |

## Issues found & resolved (required edits — DONE)

1. **`updatedAt @updatedAt` would never populate.** The API never writes `BacktestReport` via
   Prisma (engine-only raw SQL), so Prisma's `@updatedAt` magic never fires. → Changed to
   `@default(now())`; engine sets it explicitly in the UPSERT. *(architecture.md)*
2. **Dedup DELETE could leave duplicates** when rows share a `createdAt` (batch runs), which
   would make the unique-constraint creation fail. → Tie-break on `id` is now **inline** in the
   canonical SQL, with a post-delete assertion. *(architecture.md)*
3. **Migration/code ordering unstated.** `ON CONFLICT` errors without the unique index. →
   Added explicit "migration before engine code" ordering to Phase 1. *(implementation_plan.md)*
4. **`timeframe` casing could escape dedup.** If `"1D"`/`"1d"` both exist they'd be distinct
   cells. → Added a pre-flight check to normalize/verify `timeframe` values. *(implementation_plan.md)*

## Remaining risks & open questions (non-blocking)

- **R1 — Live migration is destructive of duplicate rows.** Mitigated: clone-first, CSV
  snapshot, run in a maintenance window (already in edge_cases + verification). The dropped
  rows are stale-version duplicates — acceptable and intended. *Confirm the CSV snapshot step
  is actually performed at promotion.*
- **R2 — Reported ROI will visibly drop** after Phases 2–3 (top strategies lose ~30–50% of
  apparent ROI; 600%+ cells fall to realistic). Not a bug — but must be communicated so it
  doesn't read as a regression. Already in ui-ux-flow + rollout note.
- **R3 — `engineVersion` is informational only.** This feature stamps it but does **not**
  auto-recompute on version mismatch. That's deliberate (out of scope); flagged so a future
  reader doesn't assume staleness is auto-healed.
- **R4 — Frontend leaderboard has no test.** Backend response shape is unchanged, so risk is
  low; verification relies on a manual smoke check. Acceptable for a backend feature.
- **Q1 — Empty (`totalTrades=0`) rows:** default is keep-but-exclude-in-aggregates (non-
  destructive). Confirm at `/execute-phase` whether you'd rather hard-delete them (e.g.
  Episodic_Pivot's 17 empty rows). Either is fine; default is safer.

## Phase sizing / reviewability

- Phase 1 ~150–250 LOC, Phase 2 ~40–80, Phase 3 ~60–120 — all well under 500 and independently
  reviewable. Phase 1 gates 2 & 3; 2 & 3 are mutually independent. ✅
- The sizing decision (Option A) is resolved and locked into Phase 3 — no open gate remains.

## Edge-case coverage check

Auth (no change — no new endpoints), concurrency (UPSERT serialization, migration pause),
empty states (`totalTrades=0`), failure modes (NaN metrics, tie-breaks, penny/expensive-stock
sizing) are all covered in edge_cases_and_testing.md with a 10-row test matrix mapped to phases.
✅

## Conclusion

Approved for implementation. Proceed to `/execute-phase` starting with **Phase 1**. Apply the
migration to the clone first and verify the 1363 → 323 collapse before adding the constraint.
