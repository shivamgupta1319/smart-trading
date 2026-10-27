-- CreateTable
CREATE TABLE "DhanPosition" (
    "id" SERIAL NOT NULL,
    "signalId" INTEGER NOT NULL,
    "symbol" TEXT NOT NULL,
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
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "DhanPosition_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DhanDailyState" (
    "id" SERIAL NOT NULL,
    "dayKey" TEXT NOT NULL,
    "realizedLossToday" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "ordersToday" INTEGER NOT NULL DEFAULT 0,
    "killed" BOOLEAN NOT NULL DEFAULT false,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "DhanDailyState_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "DhanPosition_signalId_key" ON "DhanPosition"("signalId");

-- CreateIndex
CREATE INDEX "DhanPosition_status_idx" ON "DhanPosition"("status");

-- CreateIndex
CREATE UNIQUE INDEX "DhanDailyState_dayKey_key" ON "DhanDailyState"("dayKey");
