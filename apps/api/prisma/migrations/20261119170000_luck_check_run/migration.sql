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
