import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

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

    const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
    const wins = closedTrades.filter((t) => t.outcome === 'WIN');
    const losses = closedTrades.filter((t) => t.outcome === 'LOSS');
    const winRate =
      closedTrades.length > 0
        ? (wins.length / closedTrades.length) * 100
        : 0;

    const avgWin =
      wins.length > 0
        ? wins.reduce((sum, t) => sum + (t.pnl || 0), 0) / wins.length
        : 0;
    const avgLoss =
      losses.length > 0
        ? Math.abs(
            losses.reduce((sum, t) => sum + (t.pnl || 0), 0) / losses.length,
          )
        : 0;
    const profitFactor =
      avgLoss > 0 ? (avgWin * wins.length) / (avgLoss * losses.length) : 0;

    // Best strategy by total P&L
    const strategyPnl: Record<
      string,
      { pnl: number; trades: number; wins: number }
    > = {};
    for (const t of closedTrades) {
      if (!strategyPnl[t.strategyName]) {
        strategyPnl[t.strategyName] = { pnl: 0, trades: 0, wins: 0 };
      }
      strategyPnl[t.strategyName].pnl += t.pnl || 0;
      strategyPnl[t.strategyName].trades++;
      if (t.outcome === 'WIN') strategyPnl[t.strategyName].wins++;
    }

    const strategyBreakdown = Object.entries(strategyPnl)
      .map(([name, data]) => ({
        strategy: name,
        totalPnl: Math.round(data.pnl * 100) / 100,
        trades: data.trades,
        wins: data.wins,
        winRate:
          data.trades > 0
            ? Math.round((data.wins / data.trades) * 100 * 100) / 100
            : 0,
      }))
      .sort((a, b) => b.totalPnl - a.totalPnl);

    const bestStrategy =
      strategyBreakdown.length > 0 ? strategyBreakdown[0].strategy : 'N/A';

    // Equity curve: cumulative P&L over time
    const sortedTrades = [...closedTrades].sort(
      (a, b) => new Date(a.exitTime || a.entryTime).getTime() - new Date(b.exitTime || b.entryTime).getTime()
    );
    let cumPnl = 0;
    const equityCurveMap = new Map<number, number>();
    for (const t of sortedTrades) {
      cumPnl += t.pnl || 0;
      const tTime = Math.floor(new Date(t.exitTime || t.entryTime).getTime() / 1000);
      equityCurveMap.set(tTime, cumPnl);
    }
    const equityCurve = Array.from(equityCurveMap.entries()).map(([time, value]) => ({
      time,
      value: Math.round(value * 100) / 100,
    }));

    // Hold duration breakdown
    const holdDurationStats: Record<string, { trades: number; pnl: number }> =
      {};
    for (const t of closedTrades) {
      const hd = t.holdDuration || 'UNKNOWN';
      if (!holdDurationStats[hd]) {
        holdDurationStats[hd] = { trades: 0, pnl: 0 };
      }
      holdDurationStats[hd].trades++;
      holdDurationStats[hd].pnl += t.pnl || 0;
    }

    return {
      totalTrades: allTrades.length,
      openTrades: openTrades.length,
      closedTrades: closedTrades.length,
      totalPnl: Math.round(totalPnl * 100) / 100,
      winRate: Math.round(winRate * 100) / 100,
      wins: wins.length,
      losses: losses.length,
      avgWin: Math.round(avgWin * 100) / 100,
      avgLoss: Math.round(avgLoss * 100) / 100,
      profitFactor: Math.round(profitFactor * 100) / 100,
      bestStrategy,
      strategyBreakdown,
      equityCurve,
      holdDurationStats,
      initialCapital: 100000,
      currentCapital: Math.round((100000 + totalPnl) * 100) / 100,
    };
  }

  async updateNotes(id: number, notes: string) {
    return this.prisma.trade.update({
      where: { id },
      data: { notes },
    });
  }

  async manualClose(id: number, exitPrice: number) {
    const trade = await this.prisma.trade.findUnique({ where: { id } });
    if (!trade || trade.status === 'CLOSED') return trade;

    const isBuy = trade.signalType === 'BUY';
    const pnlPerShare = isBuy
      ? exitPrice - trade.entryPrice
      : trade.entryPrice - exitPrice;
    const pnl = pnlPerShare * trade.quantity;
    const pnlPercent = (pnlPerShare / trade.entryPrice) * 100;

    let outcome = 'BREAKEVEN';
    if (pnl > 0) outcome = 'WIN';
    else if (pnl < 0) outcome = 'LOSS';

    // Also close the signal
    await this.prisma.liveSignal.update({
      where: { id: trade.signalId },
      data: { status: 'CLOSED' },
    });

    return this.prisma.trade.update({
      where: { id },
      data: {
        exitPrice,
        pnl: Math.round(pnl * 100) / 100,
        pnlPercent: Math.round(pnlPercent * 100) / 100,
        outcome,
        exitTime: new Date(),
        status: 'CLOSED',
      },
    });
  }

  async remove(id: number) {
    const trade = await this.prisma.trade.findUnique({ where: { id } });
    if (!trade) return null;
    
    await this.prisma.trade.delete({ where: { id } });
    
    try {
      await this.prisma.liveSignal.delete({ where: { id: trade.signalId } });
    } catch (e) {
      // ignore
    }
    
    return trade;
  }
}
