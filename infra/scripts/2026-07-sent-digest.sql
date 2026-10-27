-- Restart-safe idempotency for scheduled Telegram digests (see ReportsService).
-- Surgical additive change — safe to run against the live DB, idempotent.
-- Apply on work-pc:
--   ssh work-pc 'docker exec -i smart-trading-db psql -U trader -d smart_trading' < infra/scripts/2026-07-sent-digest.sql

CREATE TABLE IF NOT EXISTS "SentDigest" (
  "id"        SERIAL PRIMARY KEY,
  "period"    TEXT NOT NULL,
  "periodKey" TEXT NOT NULL,
  "sentAt"    TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS "SentDigest_period_periodKey_key"
  ON "SentDigest" ("period", "periodKey");
