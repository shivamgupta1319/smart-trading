# FEAT-004 — Live-vs-Backtest Reconciliation · Implementation Plan

> **Status: BLOCKED.** Do not start until **FEAT-001** (trustworthy backtest table) and
> **FEAT-002** (trustworthy live bookkeeping) are both `DONE`. This plan is a sketch to be
> firmed up at unblock time — the exact shape depends on what FEAT-001's corrected numbers
> look like. Kept here so the work is sequenced and visible, not so it can begin now.

All work against the DB clone per [v2-environment.md](../../v2-environment.md); a single
branch + PR off `roadmap-v2` per phase.

---

## Phase 1 — Reconciliation report (read-only)

**Goal:** a reproducible per-cell join of live realized R vs corrected backtest expectancy
+ Monte-Carlo band, with an inside/outside-band label.

1. Query live-traded cells (`Trade` joined to symbol/strategy/timeframe) and their realized
   R, using FEAT-002's corrected `outcome`/`pnl`.
2. For each, recompute capped/deduped backtest expectancy on the exact symbol over the live
   window via the existing walk-forward + bootstrap helpers
   ([auto_select.py:110-121](../../../apps/engine/routers/auto_select.py#L110-L121)).
3. Label each cell inside/outside the Monte-Carlo band; emit a table + the corrected-top-set
   vs current-93-monitored-cells diff (flag the 25/93 thin-sample cells).
4. Output to `docs/agent-reports/` (mirrors the analyst-report convention) — read-only,
   no DB writes.

**Done when:** AC #1, #2, #4. Pure analysis; no schema/live change.

---

## Phase 2 (optional) — Trust signal into auto-select

**Goal:** let auto-select demote cells with a proven, out-of-band live-vs-backtest gap.

1. Persist a per-cell trust delta (new column or side table) produced by Phase 1.
2. Add an auto-select demotion/penalty term that consumes it; gate behind a config flag.
3. Tests + a dry-run diff of the selected set with/without the trust signal.

**Done when:** AC #3. Depends on Phase 1 and a user decision to wire it in.

---

## Sequencing

```
(FEAT-001 DONE) + (FEAT-002 DONE) → unblock → review-docs (firm up plan)
  → Phase 1 (PR) → verify → [Phase 2 if approved] → verify-feature
```

## Rollback

Phase 1 writes only a report file — nothing to roll back. Phase 2 is a single-PR revert
behind a config flag (default off until validated).
