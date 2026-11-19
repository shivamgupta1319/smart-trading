-- Telegram digests: one row per digest already sent, so a restart never sends a second
-- copy. (period, periodKey) is the once-only key: DAILY/OVERALL use the IST date, WEEKLY
-- the IST date of that week's Monday. Idempotent.
CREATE TABLE IF NOT EXISTS "SentDigest" (
    "id" SERIAL NOT NULL,
    "period" TEXT NOT NULL,
    "periodKey" TEXT NOT NULL,
    "sentAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "SentDigest_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "SentDigest_period_periodKey_key" ON "SentDigest"("period", "periodKey");
