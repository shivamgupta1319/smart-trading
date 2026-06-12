import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import {
  INITIAL_CAPITAL,
  MAX_HEAT_PCT,
  MIN_TRADES_FOR_CONFIDENCE,
  leverageFor,
} from '../common/risk';
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

    type AnyTrade = (typeof allTrades)[number];
    const closedTrades = allTrades.filter((t) => t.status === 'CLOSED');
    const openTrades = allTrades.filter((t) => t.status === 'OPEN');
    // Portfolio P&L/ROI reflect only FUNDED trades (what the ₹1L account could afford).
    // Research breakdowns below use ALL closed trades (funded + shadow) so the
    // strategy×stock edge analysis stays unbiased by capital availability.
    const fundedClosed = closedTrades.filter((t) => t.fundingStatus === 'FUNDED');

    const pnlOf = (t: { pnl: unknown }) => toNum(t.pnl as never);
    const riskOf = (t: { riskAmount: unknown }) => toNum(t.riskAmount as never);

    // ---- Portfolio metrics (FUNDED closed only) -------------------------------
    const totalPnl = fundedClosed.reduce((sum, t) => sum + pnlOf(t), 0);
    const wins = fundedClosed.filter((t) => t.outcome === 'WIN');
    const losses = fundedClosed.filter((t) => t.outcome === 'LOSS');
    const winRate = fundedClosed.length > 0 ? (wins.length / fundedClosed.length) * 100 : 0;
    const avgWin =
      wins.length > 0 ? wins.reduce((sum, t) => sum + pnlOf(t), 0) / wins.length : 0;
    const avgLoss =
      losses.length > 0
        ? Math.abs(losses.reduce((sum, t) => sum + pnlOf(t), 0) / losses.length)
        : 0;
    const profitFactor =
      avgLoss > 0 ? (avgWin * wins.length) / (avgLoss * losses.length) : 0;
    const roiPct = safePct(totalPnl, INITIAL_CAPITAL);

    // Equity curve: cumulative FUNDED P&L over time
    const sortedTrades = [...fundedClosed].sort(
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

    // ---- Decision-grade edge metrics for a group of closed trades -------------
    // Computed over funded+shadow so a pair's edge is judged on every signal it fired.
    const cellMetrics = (group: AnyTrade[]) => {
      const trades = group.length;
      const grpWins = group.filter((t) => t.outcome === 'WIN');
      const grpLosses = group.filter((t) => t.outcome === 'LOSS');
      const grpPnl = group.reduce((s, t) => s + pnlOf(t), 0);
      const grossWin = grpWins.reduce((s, t) => s + pnlOf(t), 0);
      const grossLoss = Math.abs(grpLosses.reduce((s, t) => s + pnlOf(t), 0));
      const cellAvgWin = grpWins.length ? grossWin / grpWins.length : 0;
      const cellAvgLoss = grpLosses.length ? grossLoss / grpLosses.length : 0;
      // Avg R-multiple = mean(pnl / riskAmount). Normalizes capped (sub-2%) and full
      // trades onto one scale — the apples-to-apples edge metric to rank pairs by.
      const rTrades = group.filter((t) => riskOf(t) > 0);
      const avgRMultiple = rTrades.length
        ? rTrades.reduce((s, t) => s + pnlOf(t) / riskOf(t), 0) / rTrades.length
        : 0;
      // Max drawdown of the cell's cumulative P&L (trades ordered by exit time).
      const ordered = [...group].sort(
        (a, b) =>
          new Date(a.exitTime || a.entryTime).getTime() -
          new Date(b.exitTime || b.entryTime).getTime(),
      );
      let cum = 0;
      let peak = 0;
      let maxDd = 0;
      for (const t of ordered) {
        cum += pnlOf(t);
        if (cum > peak) peak = cum;
        if (peak - cum > maxDd) maxDd = peak - cum;
      }
      const funded = group.filter((t) => t.fundingStatus === 'FUNDED').length;
      const confidence = trades >= 30 ? 'HIGH' : trades >= 10 ? 'MEDIUM' : 'LOW';
      return {
        trades,
        wins: grpWins.length,
        winRate: trades > 0 ? round2((grpWins.length / trades) * 100) : 0,
        totalPnl: round2(grpPnl),
        avgWin: round2(cellAvgWin),
        avgLoss: round2(cellAvgLoss),
        expectancy: trades > 0 ? round2(grpPnl / trades) : 0,
        avgRMultiple: round2(avgRMultiple),
        profitFactor: round2(grossLoss > 0 ? grossWin / grossLoss : 0),
        maxDrawdown: round2(maxDd),
        funded,
        shadow: trades - funded,
        confidence,
        reliable: trades >= MIN_TRADES_FOR_CONFIDENCE,
      };
    };

    const groupBy = (trades: AnyTrade[], keyFn: (t: AnyTrade) => string) => {
      const map = new Map<string, AnyTrade[]>();
      for (const t of trades) {
        const k = keyFn(t);
        (map.get(k) || map.set(k, []).get(k)!).push(t);
      }
      return map;
    };

    // ---- Research breakdowns (ALL closed: funded + shadow) --------------------
    const strategyBreakdown = Array.from(
      groupBy(closedTrades, (t) => t.strategyName).entries(),
    )
      .map(([strategy, group]) => ({ strategy, ...cellMetrics(group) }))
      .sort((a, b) => b.totalPnl - a.totalPnl);

    const bestStrategy = strategyBreakdown.length > 0 ? strategyBreakdown[0].strategy : 'N/A';

    const stockWiseStrategyBreakdown = Array.from(
      groupBy(closedTrades, (t) => `${t.symbol}|@|${t.strategyName}`).entries(),
    )
      .map(([key, group]) => {
        const [symbol, strategy] = key.split('|@|');
        return { symbol, strategy, ...cellMetrics(group) };
      })
      .sort((a, b) => b.totalPnl - a.totalPnl);

    // Hold duration breakdown (all closed)
    const holdDurationStats: Record<string, { trades: number; pnl: number }> = {};
    for (const t of closedTrades) {
      const hd = t.holdDuration || 'UNKNOWN';
      if (!holdDurationStats[hd]) holdDurationStats[hd] = { trades: 0, pnl: 0 };
      holdDurationStats[hd].trades++;
      holdDurationStats[hd].pnl = round2(holdDurationStats[hd].pnl + pnlOf(t));
    }

    return {
      totalTrades: allTrades.length,
      openTrades: openTrades.length,
      closedTrades: closedTrades.length,
      fundedClosedTrades: fundedClosed.length,
      shadowClosedTrades: closedTrades.length - fundedClosed.length,
      // Portfolio (FUNDED only):
      totalPnl: round2(totalPnl),
      roiPct: round2(roiPct),
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
    // Only FUNDED open positions consume real buying power. SHADOW positions are
    // research-only and are reported separately (count) but don't lock up capital.
    const open = (
      await this.prisma.trade.findMany({ where: { status: 'OPEN', fundingStatus: 'FUNDED' } })
    ).map((t) => normalizeTradeMoney(t)!);
    const shadowPositions = await this.prisma.trade.count({
      where: { status: 'OPEN', fundingStatus: 'SHADOW' },
    });

    const symbols = [...new Set(open.map((t) => t.symbol))];
    const sectorRows = symbols.length
      ? await this.prisma.nseStock.findMany({ where: { symbol: { in: symbols } } })
      : [];
    const sectorOf = new Map(sectorRows.map((r) => [r.symbol, r.sector || 'Unknown']));

    let exposure = 0; // total notional
    let marginUsed = 0; // cash locked up = Σ notional ÷ leverage
    let heat = 0;
    const bySector: Record<string, number> = {};
    const positions = open.map((t) => {
      const qty = t.remainingQty ?? t.quantity;
      const entry = toNum(t.entryPrice);
      const posExposure = qty * entry;
      const posMargin = posExposure / leverageFor(t.holdDuration);
      const posRisk = qty * Math.abs(entry - toNum(t.stopLoss));
      exposure += posExposure;
      marginUsed += posMargin;
      heat += posRisk;
      const sector = sectorOf.get(t.symbol) || 'Unknown';
      bySector[sector] = round2((bySector[sector] || 0) + posExposure);
      return {
        symbol: t.symbol,
        strategy: t.strategyName,
        sector,
        qty,
        exposure: round2(posExposure),
        margin: round2(posMargin),
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
    // Margin (not notional) is what the cash account funds, so measure usage against cash.
    const marginUsedPct = safePct(marginUsed, INITIAL_CAPITAL);
    const availableCash = round2(INITIAL_CAPITAL - marginUsed);
    const flags: string[] = [];
    if (heatPct > MAX_HEAT_PCT)
      flags.push(
        `Total heat ${heatPct.toFixed(1)}% exceeds the ${MAX_HEAT_PCT}% guideline (3× the 2% per-trade rule).`,
      );
    // With the entry-time funding cap, margin should never exceed cash — flag only if it does.
    if (marginUsed > INITIAL_CAPITAL)
      flags.push(
        `Margin used ₹${round2(marginUsed).toFixed(0)} exceeds cash ₹${INITIAL_CAPITAL.toFixed(0)} — funding guard breached.`,
      );
    const topSector = sectorConcentration[0];
    if (topSector && topSector.pctOfBook > 40)
      flags.push(`${topSector.pctOfBook.toFixed(0)}% of the book is in ${topSector.sector} — concentrated.`);

    return {
      openPositions: open.length,
      shadowPositions,
      notional: round2(exposure),
      marginUsed: round2(marginUsed),
      marginUsedPct: round2(marginUsedPct),
      availableCash,
      totalHeat: round2(heat),
      heatPct: round2(heatPct),
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
