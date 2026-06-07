import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { INITIAL_CAPITAL } from '../common/risk';
import { toNum, round2, safePct, normalizeTradeMoney } from '../common/money';

@Injectable()
export class TradesService {
  constructor(private prisma: PrismaService) {}

  async findAll(filters?: {
    status?: string;
    strategyName?: string;
    holdDuration?: string;
    limit?: number;
  }) {
    const where: Record<string, string> = {};
    if (filters?.status) where.status = filters.status;
    if (filters?.strategyName) where.strategyName = filters.strategyName;
    if (filters?.holdDuration) where.holdDuration = filters.holdDuration;

    return this.prisma.trade.findMany({
      where,
      include: { stock: true },
      orderBy: { entryTime: 'desc' },
      take: filters?.limit || 200,
    });
  }

  async findOne(id: number) {
    return this.prisma.trade.findUnique({
      where: { id },
      include: { stock: true, signal: true },
    });
  }

  async getPortfolioStats() {
    const allTrades = await this.prisma.trade.findMany({
      orderBy: { entryTime: 'asc' },
    });

    const closedTrades = allTrades.filter((t) => t.status === 'CLOSED');
    const openTrades = allTrades.filter((t) => t.status === 'OPEN');

    const pnlOf = (t: { pnl: unknown }) => toNum(t.pnl as never);

    const totalPnl = closedTrades.reduce((sum, t) => sum + pnlOf(t), 0);
    const wins = closedTrades.filter((t) => t.outcome === 'WIN');
    const losses = closedTrades.filter((t) => t.outcome === 'LOSS');
    const winRate = closedTrades.length > 0 ? (wins.length / closedTrades.length) * 100 : 0;

    const avgWin =
      wins.length > 0 ? wins.reduce((sum, t) => sum + pnlOf(t), 0) / wins.length : 0;
    const avgLoss =
      losses.length > 0
        ? Math.abs(losses.reduce((sum, t) => sum + pnlOf(t), 0) / losses.length)
        : 0;
    const profitFactor =
      avgLoss > 0 ? (avgWin * wins.length) / (avgLoss * losses.length) : 0;

    // Best strategy by total P&L
    const strategyPnl: Record<string, { pnl: number; trades: number; wins: number }> = {};
    for (const t of closedTrades) {
      if (!strategyPnl[t.strategyName]) {
        strategyPnl[t.strategyName] = { pnl: 0, trades: 0, wins: 0 };
      }
      strategyPnl[t.strategyName].pnl += pnlOf(t);
      strategyPnl[t.strategyName].trades++;
      if (t.outcome === 'WIN') strategyPnl[t.strategyName].wins++;
    }

    const strategyBreakdown = Object.entries(strategyPnl)
      .map(([name, data]) => ({
        strategy: name,
        totalPnl: round2(data.pnl),
        trades: data.trades,
        wins: data.wins,
        winRate: data.trades > 0 ? round2((data.wins / data.trades) * 100) : 0,
      }))
      .sort((a, b) => b.totalPnl - a.totalPnl);

    const bestStrategy = strategyBreakdown.length > 0 ? strategyBreakdown[0].strategy : 'N/A';

    // Equity curve: cumulative P&L over time
    const sortedTrades = [...closedTrades].sort(
      (a, b) =>
        new Date(a.exitTime || a.entryTime).getTime() -
        new Date(b.exitTime || b.entryTime).getTime(),
    );
    let cumPnl = 0;
    const equityCurveMap = new Map<number, number>();
    for (const t of sortedTrades) {
      cumPnl += pnlOf(t);
      const tTime = Math.floor(new Date(t.exitTime || t.entryTime).getTime() / 1000);
      equityCurveMap.set(tTime, cumPnl);
    }
    const equityCurve = Array.from(equityCurveMap.entries()).map(([time, value]) => ({
      time,
      value: round2(value),
    }));

    // Hold duration breakdown
    const holdDurationStats: Record<string, { trades: number; pnl: number }> = {};
    for (const t of closedTrades) {
      const hd = t.holdDuration || 'UNKNOWN';
      if (!holdDurationStats[hd]) holdDurationStats[hd] = { trades: 0, pnl: 0 };
      holdDurationStats[hd].trades++;
      holdDurationStats[hd].pnl = round2(holdDurationStats[hd].pnl + pnlOf(t));
    }

    // Stock-wise Strategy Breakdown
    const stockWiseStrategyBreakdown: Array<Record<string, unknown>> = [];
    const stockStrategyMap = new Map<string, { pnl: number; trades: number; wins: number }>();
    for (const t of closedTrades) {
      const key = JSON.stringify({ symbol: t.symbol, strategy: t.strategyName });
      const stats = stockStrategyMap.get(key) || { pnl: 0, trades: 0, wins: 0 };
      stats.pnl += pnlOf(t);
      stats.trades++;
      if (t.outcome === 'WIN') stats.wins++;
      stockStrategyMap.set(key, stats);
    }
    for (const [key, data] of stockStrategyMap.entries()) {
      const parsed = JSON.parse(key);
      stockWiseStrategyBreakdown.push({
        symbol: parsed.symbol,
        strategy: parsed.strategy,
        totalPnl: round2(data.pnl),
        trades: data.trades,
        wins: data.wins,
        winRate: data.trades > 0 ? round2((data.wins / data.trades) * 100) : 0,
      });
    }
    stockWiseStrategyBreakdown.sort(
      (a, b) => (b.totalPnl as number) - (a.totalPnl as number),
    );

    return {
      totalTrades: allTrades.length,
      openTrades: openTrades.length,
      closedTrades: closedTrades.length,
      totalPnl: round2(totalPnl),
      winRate: round2(winRate),
      wins: wins.length,
      losses: losses.length,
      avgWin: round2(avgWin),
      avgLoss: round2(avgLoss),
      profitFactor: round2(profitFactor),
      bestStrategy,
      strategyBreakdown,
      stockWiseStrategyBreakdown,
      equityCurve,
      holdDurationStats,
      initialCapital: INITIAL_CAPITAL,
      currentCapital: round2(INITIAL_CAPITAL + totalPnl),
    };
  }

  /**
   * Portfolio-level risk engine. Aggregates OPEN positions into total exposure,
   * "heat" (sum of money at risk if every open stop is hit), and per-sector
   * concentration — none of which the app tracked before. Raises flags when the
   * book is over-exposed or too concentrated.
   */
  async getRiskMetrics() {
    const open = (await this.prisma.trade.findMany({ where: { status: 'OPEN' } })).map(
      (t) => normalizeTradeMoney(t)!,
    );

    const symbols = [...new Set(open.map((t) => t.symbol))];
    const sectorRows = symbols.length
      ? await this.prisma.nseStock.findMany({ where: { symbol: { in: symbols } } })
      : [];
    const sectorOf = new Map(sectorRows.map((r) => [r.symbol, r.sector || 'Unknown']));

    let exposure = 0;
    let heat = 0;
    const bySector: Record<string, number> = {};
    const positions = open.map((t) => {
      const qty = t.remainingQty ?? t.quantity;
      const posExposure = qty * t.entryPrice;
      const posRisk = qty * Math.abs(t.entryPrice - t.stopLoss);
      exposure += posExposure;
      heat += posRisk;
      const sector = sectorOf.get(t.symbol) || 'Unknown';
      bySector[sector] = round2((bySector[sector] || 0) + posExposure);
      return {
        symbol: t.symbol,
        strategy: t.strategyName,
        sector,
        qty,
        exposure: round2(posExposure),
        riskAtStop: round2(posRisk),
      };
    });

    const sectorConcentration = Object.entries(bySector)
      .map(([sector, exp]) => ({
        sector,
        exposure: exp,
        pctOfBook: exposure > 0 ? round2((exp / exposure) * 100) : 0,
      }))
      .sort((a, b) => b.exposure - a.exposure);

    const heatPct = safePct(heat, INITIAL_CAPITAL);
    const exposurePct = safePct(exposure, INITIAL_CAPITAL);
    const flags: string[] = [];
    if (heatPct > 6) flags.push(`Total heat ${heatPct.toFixed(1)}% exceeds the 6% guideline (3× the 2% per-trade rule).`);
    if (exposurePct > 100) flags.push(`Deployed capital ${exposurePct.toFixed(0)}% exceeds available capital — over-leveraged.`);
    const topSector = sectorConcentration[0];
    if (topSector && topSector.pctOfBook > 40)
      flags.push(`${topSector.pctOfBook.toFixed(0)}% of the book is in ${topSector.sector} — concentrated.`);

    return {
      openPositions: open.length,
      deployedCapital: round2(exposure),
      deployedPct: round2(exposurePct),
      totalHeat: round2(heat),
      heatPct: round2(heatPct),
      availableCapital: round2(INITIAL_CAPITAL - exposure),
      sectorConcentration,
      positions,
      flags,
    };
  }

  async updateNotes(id: number, notes: string) {
    return this.prisma.trade.update({ where: { id }, data: { notes } });
  }

  /**
   * Manually close a trade at a given price. Now partial-exit aware (uses
   * realizedPnl + remainingQty) and uses the same "% of capital" semantics as
   * SignalsService.closeWithPrice — previously it double-counted shares and used
   * a divergent price-move % metric.
   */
  async manualClose(id: number, exitPrice: number) {
    const raw = await this.prisma.trade.findUnique({ where: { id } });
    if (!raw || raw.status === 'CLOSED') return raw;
    const trade = normalizeTradeMoney(raw)!;

    const isBuy = trade.signalType === 'BUY';
    const pnlPerShare = isBuy ? exitPrice - trade.entryPrice : trade.entryPrice - exitPrice;
    const finalLotPnl = pnlPerShare * trade.remainingQty;
    const totalPnl = trade.realizedPnl + finalLotPnl;
    const pnlPercent = safePct(totalPnl, trade.capitalUsed);
    const outcome = totalPnl > 0 ? 'WIN' : totalPnl < 0 ? 'LOSS' : 'BREAKEVEN';

    return this.prisma.$transaction(async (tx) => {
      await tx.liveSignal.update({
        where: { id: trade.signalId },
        data: { status: 'CLOSED' },
      });
      return tx.trade.update({
        where: { id },
        data: {
          exitPrice,
          pnl: round2(totalPnl),
          pnlPercent: round2(pnlPercent),
          remainingQty: 0,
          outcome,
          exitTime: new Date(),
          status: 'CLOSED',
        },
      });
    });
  }

  async remove(id: number) {
    const trade = await this.prisma.trade.findUnique({ where: { id } });
    if (!trade) return null;
    // Deleting the signal cascades to the trade (Trade.signalId onDelete: Cascade),
    // so one delete is enough and keeps the two rows consistent.
    await this.prisma.liveSignal.delete({ where: { id: trade.signalId } });
    return trade;
  }
}
