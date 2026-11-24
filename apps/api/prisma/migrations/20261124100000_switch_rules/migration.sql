-- Market-condition switching (apps/engine/switch_rules.py). Safe to run twice.
CREATE TABLE IF NOT EXISTS "SwitchRule" (
    "id" SERIAL NOT NULL,
    "strategyName" TEXT NOT NULL,
    "regime" TEXT NOT NULL,
    "trades" INTEGER NOT NULL,
    "avgR" DOUBLE PRECISION,
    "approved" BOOLEAN,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "SwitchRule_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "SwitchRule_strategyName_regime_key" ON "SwitchRule"("strategyName", "regime");
ALTER TABLE "Trade" ADD COLUMN IF NOT EXISTS "switchApproved" BOOLEAN;
