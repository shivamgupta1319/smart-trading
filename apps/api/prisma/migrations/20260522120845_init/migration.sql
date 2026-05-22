-- CreateTable
CREATE TABLE "Stock" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
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
    "maxDrawdown" DOUBLE PRECISION NOT NULL,
    "expectancy" DOUBLE PRECISION NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "BacktestReport_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ActiveConfiguration" (
    "id" SERIAL NOT NULL,
    "stockId" INTEGER NOT NULL,
    "strategyName" TEXT NOT NULL,
    "timeframe" TEXT NOT NULL,
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
    "entryPrice" DOUBLE PRECISION NOT NULL,
    "stopLoss" DOUBLE PRECISION NOT NULL,
    "target" DOUBLE PRECISION NOT NULL,
    "timestamp" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT "LiveSignal_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Stock_symbol_key" ON "Stock"("symbol");

-- CreateIndex
CREATE INDEX "HistoricalData_stockId_timeframe_timestamp_idx" ON "HistoricalData"("stockId", "timeframe", "timestamp");

-- CreateIndex
CREATE UNIQUE INDEX "HistoricalData_stockId_timestamp_timeframe_key" ON "HistoricalData"("stockId", "timestamp", "timeframe");

-- CreateIndex
CREATE INDEX "BacktestReport_stockId_strategyName_idx" ON "BacktestReport"("stockId", "strategyName");

-- CreateIndex
CREATE UNIQUE INDEX "ActiveConfiguration_stockId_key" ON "ActiveConfiguration"("stockId");

-- CreateIndex
CREATE INDEX "LiveSignal_stockId_status_idx" ON "LiveSignal"("stockId", "status");

-- AddForeignKey
ALTER TABLE "HistoricalData" ADD CONSTRAINT "HistoricalData_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "BacktestReport" ADD CONSTRAINT "BacktestReport_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ActiveConfiguration" ADD CONSTRAINT "ActiveConfiguration_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LiveSignal" ADD CONSTRAINT "LiveSignal_stockId_fkey" FOREIGN KEY ("stockId") REFERENCES "Stock"("id") ON DELETE CASCADE ON UPDATE CASCADE;
