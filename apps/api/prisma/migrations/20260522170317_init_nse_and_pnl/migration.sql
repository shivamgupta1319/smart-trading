/*
  Warnings:

  - You are about to drop the column `expectancy` on the `BacktestReport` table. All the data in the column will be lost.
  - You are about to drop the column `name` on the `Stock` table. All the data in the column will be lost.
  - Added the required column `netProfit` to the `BacktestReport` table without a default value. This is not possible if the table is not empty.
  - Added the required column `roiPercentage` to the `BacktestReport` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "BacktestReport" DROP COLUMN "expectancy",
ADD COLUMN     "netProfit" DOUBLE PRECISION NOT NULL,
ADD COLUMN     "roiPercentage" DOUBLE PRECISION NOT NULL;

-- AlterTable
ALTER TABLE "Stock" DROP COLUMN "name";

-- CreateTable
CREATE TABLE "NseStock" (
    "id" SERIAL NOT NULL,
    "symbol" TEXT NOT NULL,
    "companyName" TEXT NOT NULL,
    "sector" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NseStock_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "NseStock_symbol_key" ON "NseStock"("symbol");
