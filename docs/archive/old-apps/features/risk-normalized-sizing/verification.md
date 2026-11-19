# FEAT-005 — Risk-Normalized Sizing · Verification & Rollout

## Test strategy

1. **Unit (API, TS):** `qty` for tight-stop intraday (notional binds), wide-stop swing (risk cap
   binds, IFCI example = 38), entry==stop (no throw), cap-disabled regression (P3).
2. **Unit (engine, Python):** same four cases via `pytest` inside `smart-trading-v2-engine`
   (`pip install -r requirements-dev.txt` first — pytest only in dev reqs).
3. **Parity:** the shared worked example asserted on both sides yields identical qty.
4. **Backtest re-run:** full backtest across the active roster with the cap on; capture new
   payoff / avg-R / PF / typical size. Confirm the chosen `RISK_PER_TRADE_PCT` restores payoff ≥ 1.
5. **Backfill dry-run:** `--dry-run` prints k-distribution + restated aggregate on the work-pc data;
   review before any write.
6. **End-to-end restatement:** after `--apply` (post-backup), re-run `scratchpad/audit.sql`:
   confirm avg win ≥ avg loss, PF > 1, and losers no longer carry more ₹-risk than winners
   (re-check `avg_win_risk_rs` vs `avg_loss_risk_rs`).

## Rollout checklist

- [ ] Phase 1 PR merged (API + engine in one PR for parity); unit + parity tests green.
- [ ] `nx build api` and `nx build frontend` succeed (frontend unaffected but part of CI).
- [ ] Engine `pytest` green in-container.
- [ ] Deploy per [docs/work-pc-deployment.md]: engine = `docker restart smart-trading-v2-engine`
      (+ `-scanner`); api = `docker compose build api && up -d api`.
- [ ] Confirm `RISK_PER_TRADE_PCT` set (or defaulted) identically for api + engine on work-pc.
- [ ] Phase 2 value chosen and recorded.
- [ ] Phase 3: `pg_dump` backup taken; `--dry-run` reviewed; `--apply` run; audit SQL re-checked.
- [ ] Analyst re-run (the 2026-07-14 audit) confirms the restated book: avg win ≥ avg loss, PF > 1.

## Success metric

The owner's original symptom is gone: **average profit per trade ≥ average loss per trade**
(payoff ≥ 1) on the restated + forward book, with PF > 1, driven by equalized per-trade ₹-risk
(not by hiding losers). Backtest and live sizing produce the same qty for the same signal.

## Rollback

- Phase 1: single-PR revert (both files). `RISK_PER_TRADE_PCT=1.0` makes the cap inert without a
  code change if an emergency knob is needed.
- Phase 3: restore from `pg_dump` / JSON snapshot taken before `--apply`.
