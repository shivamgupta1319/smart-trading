-- Full schema for a FRESH database (the merged product, 2026-11).
--
-- Generated from apps/api/prisma/schema.prisma with
--   npx prisma migrate diff --from-empty --to-schema apps/api/prisma/schema.prisma --script
-- plus the one index Prisma's schema language cannot express (at the end).
-- Run ONCE against an empty database:
--   docker exec -i smart-trading-db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 < init-fresh-db.sql
-- The files under apps/api/prisma/migrations/ are the history of how the older
-- databases were changed by hand; a fresh database does not need them.

-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateTable
CREATE TABLE "NseStock" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "companyName" TEXT NOT NULL,
    "sector" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NseStock_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Stock" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "sector" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Stock_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "HistoricalData" (
    "id" SERIAL NOT NULL,
    "stockId" INTEGER NOT NULL,
    "timestamp" TIMESTAMP(3) NOT NULL,
    "open" DOUBLE PRECISION NOT NULL,
    "high" DOUBLE PRECISION NOT NULL,
    "low" DOUBLE PRECISION NOT NULL,
    "close" DOUBLE PRECISION NOT NULL,
    "volume" DOUBLE PRECISION NOT NULL,
    "timeframe" TEXT NOT NULL,

    CONSTRAINT "HistoricalData_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "BacktestReport" (
    "id" SERIAL NOT NULL,
    "stockId" INTEGER NOT NULL,
    "strategyName" TEXT NOT NULL,
    "timeframe" TEXT NOT NULL,
    "winRate" DOUBLE PRECISION NOT NULL,
    "totalTrades" INTEGER NOT NULL,
    "netProfit" DOUBLE PRECISION NOT NULL,
    "maxDrawdown" DOUBLE PRECISION NOT NULL,
    "roiPercentage" DOUBLE PRECISION NOT NULL,
    "avgRMultiple" DOUBLE PRECISION,
    "profitFactor" DOUBLE PRECISION,
    "maxDrawdownPct" DOUBLE PRECISION,
    "expectancy" DOUBLE PRECISION,
    "spanYears" DOUBLE PRECISION,
    "engineVersion" TEXT NOT NULL DEFAULT 'unversioned',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "BacktestReport_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ActiveConfiguration" (
    "id" SERIAL NOT NULL,
    "stockId" INTEGER NOT NULL,
    "strategyName" TEXT NOT NULL,
    "timeframe" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'TESTING',
    "statusReason" TEXT,
    "statusChangedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ActiveConfiguration_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LiveSignal" (
    "id" SERIAL NOT NULL,
    "stockId" INTEGER NOT NULL,
    "strategyName" TEXT NOT NULL,
    "signalType" TEXT NOT NULL,
    "entryPrice" DECIMAL(18,4) NOT NULL,
    "stopLoss" DECIMAL(18,4) NOT NULL,
    "target" DECIMAL(18,4) NOT NULL,
    "holdDuration" TEXT,
    "timestamp" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT "LiveSignal_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Trade" (
    "id" SERIAL NOT NULL,
    "signalId" INTEGER NOT NULL,
    "stockId" INTEGER NOT NULL,
    "symbol" TEXT NOT NULL,
    "strategyName" TEXT NOT NULL,
    "signalType" TEXT NOT NULL,
    "holdDuration" TEXT NOT NULL,
    "entryPrice" DECIMAL(18,4) NOT NULL,
    "exitPrice" DECIMAL(18,4),
    "stopLoss" DECIMAL(18,4) NOT NULL,
    "target" DECIMAL(18,4) NOT NULL,
    "quantity" INTEGER NOT NULL DEFAULT 1,
    "capitalUsed" DECIMAL(18,4) NOT NULL DEFAULT 0,
    "riskAmount" DECIMAL(18,4) NOT NULL DEFAULT 0,
    "pnl" DECIMAL(18,4),
    "pnlPercent" DOUBLE PRECISION,
    "outcome" TEXT,
    "entryTime" TIMESTAMP(3) NOT NULL,
    "exitTime" TIMESTAMP(3),
    "status" TEXT NOT NULL DEFAULT 'OPEN',
    "notes" TEXT,
    "originalStopLoss" DECIMAL(18,4),
    "trailingState" TEXT NOT NULL DEFAULT 'INITIAL',
    "peakPrice" DECIMAL(18,4),
    "realizedPnl" DECIMAL(18,4) NOT NULL DEFAULT 0,
    "remainingQty" INTEGER NOT NULL DEFAULT 1,
    "cellStatusAtEntry" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Trade_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "NseStock_symbol_key" ON "NseStock"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "Stock_symbol_key" ON "Stock"("symbol");

-- CreateIndex
CREATE INDEX "HistoricalData_stockId_timeframe_timestamp_idx" ON "HistoricalData"("stockId", "timeframe", "timestamp");

-- CreateIndex
CREATE UNIQUE INDEX "HistoricalData_stockId_timestamp_timeframe_key" ON "HistoricalData"("stockId", "timestamp", "timeframe");

-- CreateIndex
CREATE INDEX "BacktestReport_stockId_strategyName_idx" ON "BacktestReport"("stockId", "strategyName");

-- CreateIndex
CREATE UNIQUE INDEX "BacktestReport_stockId_strategyName_timeframe_key" ON "BacktestReport"("stockId", "strategyName", "timeframe");

-- CreateIndex
CREATE INDEX "ActiveConfiguration_status_idx" ON "ActiveConfiguration"("status");

-- CreateIndex
CREATE UNIQUE INDEX "ActiveConfiguration_stockId_strategyName_key" ON "ActiveConfiguration"("stockId", "strategyName");

-- CreateIndex
CREATE INDEX "LiveSignal_stockId_status_idx" ON "LiveSignal"("stockId", "status");

-- CreateIndex
CREATE UNIQUE INDEX "Trade_signalId_key" ON "Trade"("signalId");

-- CreateIndex
CREATE INDEX "Trade_stockId_status_idx" ON "Trade"("stockId", "status");

-- CreateIndex
CREATE INDEX "Trade_status_idx" ON "Trade"("status");

-- CreateIndex
CREATE INDEX "Trade_strategyName_idx" ON "Trade"("strategyName");

-- AddForeignKey
ALTER TABLE "HistoricalData" ADD CONSTRAINT "HistoricalData_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "BacktestReport" ADD CONSTRAINT "BacktestReport_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ActiveConfiguration" ADD CONSTRAINT "ActiveConfiguration_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LiveSignal" ADD CONSTRAINT "LiveSignal_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Trade" ADD CONSTRAINT "Trade_signalId_fkey" FOREIGN KEY ("signalId") REFERENCES "LiveSignal"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Trade" ADD CONSTRAINT "Trade_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Real-money (Dhan) layer (see apps/api/src/dhan/)
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

-- Market condition at entry (see apps/engine/market_condition.py)
ALTER TABLE "Trade"
  ADD COLUMN IF NOT EXISTS "regimeAtEntry"          TEXT,
  ADD COLUMN IF NOT EXISTS "marketDirectionAtEntry" TEXT,
  ADD COLUMN IF NOT EXISTS "breadthAtEntry"         DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS "alignedWithMarket"      BOOLEAN;

-- Stock data flag (see apps/engine/data_checks.py)
ALTER TABLE "Stock"
  ADD COLUMN IF NOT EXISTS "dataFlag"       TEXT,
  ADD COLUMN IF NOT EXISTS "dataFlagDetail" TEXT;

-- CreateTable
CREATE TABLE IF NOT EXISTS "SentDigest" (
    "id" SERIAL NOT NULL,
    "period" TEXT NOT NULL,
    "periodKey" TEXT NOT NULL,
    "sentAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "SentDigest_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "SentDigest_period_periodKey_key" ON "SentDigest"("period", "periodKey");

-- Stock: the intraday list flag and three measured figures (apps/engine/universe.py).
-- Safe to run twice. When the flag is first added, every existing stock keeps intraday
-- on, because until now every stock was fetched and tested for intraday.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'Stock' AND column_name = 'intraday') THEN
    ALTER TABLE "Stock" ADD COLUMN "intraday" BOOLEAN NOT NULL DEFAULT false;
    UPDATE "Stock" SET "intraday" = true;
  END IF;
END $$;
ALTER TABLE "Stock" ADD COLUMN IF NOT EXISTS "tradedValueCr" DOUBLE PRECISION;
ALTER TABLE "Stock" ADD COLUMN IF NOT EXISTS "dayRangePct" DOUBLE PRECISION;
ALTER TABLE "Stock" ADD COLUMN IF NOT EXISTS "lastClose" DOUBLE PRECISION;

-- One stored luck check per run (apps/engine/luck_check.py). Safe to run twice.
CREATE TABLE IF NOT EXISTS "LuckCheckRun" (
    "id" SERIAL NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "engineVersion" TEXT NOT NULL,
    "stocks" INTEGER NOT NULL,
    "trials" INTEGER NOT NULL,
    "rows" JSONB NOT NULL,
    CONSTRAINT "LuckCheckRun_pkey" PRIMARY KEY ("id")
);

-- At most one ACTIVE signal per cell. This is the real guard behind the API's
-- duplicate check (a partial unique index, not expressible in schema.prisma).
CREATE UNIQUE INDEX IF NOT EXISTS "LiveSignal_active_unique"
  ON "LiveSignal" ("stockId", "strategyName")
  WHERE status = 'ACTIVE';
