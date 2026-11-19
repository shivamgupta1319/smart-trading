-- Real-money (Dhan) layer. Idempotent.
--   Stock.dhanSecurityId            broker id for the stock
--   ActiveConfiguration.liveEnabled the owner's switch (real orders also need status PROVEN)
--   DhanPosition / DhanDailyState   durable positions and the daily kill-switch counters
--   DhanToken                       the current access token, so a restart reuses it
ALTER TABLE "Stock" ADD COLUMN IF NOT EXISTS "dhanSecurityId" TEXT;
ALTER TABLE "ActiveConfiguration" ADD COLUMN IF NOT EXISTS "liveEnabled" BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS "DhanPosition" (
    "id" SERIAL NOT NULL,
    "signalId" INTEGER NOT NULL,
    "symbol" TEXT NOT NULL,
    "securityId" TEXT,
    "side" TEXT NOT NULL,
    "qty" INTEGER NOT NULL,
    "simEntryPrice" DOUBLE PRECISION NOT NULL,
    "orderId" TEXT,
    "fillPrice" DOUBLE PRECISION,
    "stopPrice" DOUBLE PRECISION,
    "slOrderId" TEXT,
    "status" TEXT NOT NULL DEFAULT 'OPEN',
    "exitOrderId" TEXT,
    "exitFillPrice" DOUBLE PRECISION,
    "realizedPnl" DOUBLE PRECISION,
    "closeReason" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "DhanPosition_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "DhanPosition_signalId_key" ON "DhanPosition"("signalId");
CREATE INDEX IF NOT EXISTS "DhanPosition_status_idx" ON "DhanPosition"("status");

CREATE TABLE IF NOT EXISTS "DhanDailyState" (
    "id" SERIAL NOT NULL,
    "dayKey" TEXT NOT NULL,
    "realizedLossToday" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "ordersToday" INTEGER NOT NULL DEFAULT 0,
    "killed" BOOLEAN NOT NULL DEFAULT false,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "DhanDailyState_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "DhanDailyState_dayKey_key" ON "DhanDailyState"("dayKey");

CREATE TABLE IF NOT EXISTS "DhanToken" (
    "id" INTEGER NOT NULL DEFAULT 1,
    "token" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "DhanToken_pkey" PRIMARY KEY ("id")
);
