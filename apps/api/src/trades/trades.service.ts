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

  /**
   * Portfolio stats. When `range` is given, the P&L-derived metrics (totalPnl,
   * win rate, profit factor, strategy breakdowns, trade counts) are scoped to
   * trades CLOSED within [range.from, range.to) by exitTime — used by the daily/
   * weekly Telegram digests. Account-level fields (openTrades, currentCapital,
   * initialCapital) always reflect the full all-time state regardless of range.
   * With no range, output is identical to the all-time behaviour (used by /stats).
   */
  async getPortfolioStats(range?: { from: Date; to: Date }) {
    const allTrades = await this.prisma.trade.findMany({
      orderBy: { entryTime: 'asc' },
    });

    const allClosed = allTrades.filter((t) => t.status === 'CLOSED');
    const openTrades = allTrades.filter((t) => t.status === 'OPEN');

    // All-time realized P&L drives current capital (account-level, never scoped).
    const allTimePnl = allClosed.reduce((sum, t) => sum + (t.pnl || 0), 0);

    // Period-scoped set: trades closed within the range (by exitTime). No range → all closed.
    const closedTrades = range
      ? allClosed.filter((t) => {
          if (!t.exitTime) return false;
          const et = new Date(t.exitTime).getTime();
          return et >= range.from.getTime() && et < range.to.getTime();
        })
      : allClosed;

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

    // Stock-wise Strategy Breakdown
    const stockWiseStrategyBreakdown: any[] = [];
    const stockStrategyMap = new Map<string, { pnl: number; trades: number; wins: number }>();
    
    for (const t of closedTrades) {
      const key = JSON.stringify({ symbol: t.symbol, strategy: t.strategyName });
      const stats = stockStrategyMap.get(key) || { pnl: 0, trades: 0, wins: 0 };
      stats.pnl += t.pnl || 0;
      stats.trades++;
      if (t.outcome === 'WIN') stats.wins++;
      stockStrategyMap.set(key, stats);
    }
    
    for (const [key, data] of stockStrategyMap.entries()) {
      const parsed = JSON.parse(key);
      stockWiseStrategyBreakdown.push({
        symbol: parsed.symbol,
        strategy: parsed.strategy,
        totalPnl: Math.round(data.pnl * 100) / 100,
        trades: data.trades,
        wins: data.wins,
        winRate: data.trades > 0 ? Math.round((data.wins / data.trades) * 100 * 100) / 100 : 0,
      });
    }
    stockWiseStrategyBreakdown.sort((a, b) => b.totalPnl - a.totalPnl);

    return {
      totalTrades: allTrades.length,
      openTrades: openTrades.length, // all-time (account-level)
      closedTrades: closedTrades.length,
      periodTradeCount: closedTrades.length, // # closed trades in range (all closed when no range)
      totalPnl: Math.round(totalPnl * 100) / 100,
      winRate: Math.round(winRate * 100) / 100,
      wins: wins.length,
      losses: losses.length,
      avgWin: Math.round(avgWin * 100) / 100,
      avgLoss: Math.round(avgLoss * 100) / 100,
      profitFactor: Math.round(profitFactor * 100) / 100,
      bestStrategy,
      strategyBreakdown,
      stockWiseStrategyBreakdown,
      equityCurve,
      holdDurationStats,
      initialCapital: 100000,
      currentCapital: Math.round((100000 + allTimePnl) * 100) / 100, // all-time (account-level)
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
    // Only the still-open lot is closed here; already-booked partials live in realizedPnl. Using
    // trade.quantity (full size) would double-count partials and ignore realizedPnl. Mirror
    // closeWithPrice: total = realizedPnl + perShare * remainingQty, and pnlPercent off capitalUsed.
    const finalLotPnl = pnlPerShare * trade.remainingQty;
    const pnl = trade.realizedPnl + finalLotPnl;
    const pnlPercent = trade.capitalUsed > 0 ? (pnl / trade.capitalUsed) * 100 : 0;

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
        remainingQty: 0,
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
