import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import {
  BASE_CELL_CAPITAL,
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
    // No funding gate anymore — every trade is real, so portfolio metrics AND the
    // per-cell edge breakdowns are computed over ALL closed trades.

    const pnlOf = (t: { pnl: unknown }) => toNum(t.pnl as never);
    const riskOf = (t: { riskAmount: unknown }) => toNum(t.riskAmount as never);
    const notionalOf = (t: { remainingQty: number | null; quantity: number; entryPrice: unknown }) =>
      (t.remainingQty ?? t.quantity) * toNum(t.entryPrice as never);

    // ---- Portfolio metrics (all closed) ---------------------------------------
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

    // Dynamic "invested now" = Σ notional of currently-open positions. Deployed base =
    // ₹10k × number of distinct active cells (each open position is one cell). ROI% is
    // net realized P&L over that deployed base.
    const investedNow = openTrades.reduce((sum, t) => sum + notionalOf(t), 0);
    const activeCells = new Set(openTrades.map((t) => `${t.stockId}|${t.strategyName}`)).size;
    const totalDeployedBase = activeCells * BASE_CELL_CAPITAL;
    const roiPct = safePct(totalPnl, totalDeployedBase);

    // Equity curve: cumulative realized P&L over time (all closed)
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
      // Cell fund = ₹10k seed compounded by the cell's realized P&L; cellRoiPct is how
      // much its own ₹10k grew — the headline "which stock+strategy earns" number.
      const cellCapital = round2(BASE_CELL_CAPITAL + grpPnl);
      const cellRoiPct = round2((grpPnl / BASE_CELL_CAPITAL) * 100);
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
        cellCapital,
        cellRoiPct,
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
      // Portfolio (all trades — no funding gate):
      totalPnl: round2(totalPnl),
      netPnl: round2(totalPnl),
      investedNow: round2(investedNow),
      openPositions: openTrades.length,
      activeCells,
      totalDeployedBase,
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
    };
  }

  /**
   * Portfolio-level risk engine. Aggregates OPEN positions into total exposure,
   * "heat" (sum of money at risk if every open stop is hit), and per-sector
   * concentration — none of which the app tracked before. Raises flags when the
   * book is over-exposed or too concentrated.
   */
  async getRiskMetrics() {
    // Every open position is a real trade (one per active cell). Deployed base backing the
    // open book = ₹10k × number of open positions; margin/heat are measured against it.
    const open = (
      await this.prisma.trade.findMany({ where: { status: 'OPEN' } })
    ).map((t) => normalizeTradeMoney(t)!);
    const deployedBase = open.length * BASE_CELL_CAPITAL;

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

    const heatPct = safePct(heat, deployedBase);
    // Margin (not notional) is the cash a position locks up; measure against deployed base.
    const marginUsedPct = safePct(marginUsed, deployedBase);
    const flags: string[] = [];
    if (heatPct > MAX_HEAT_PCT)
      flags.push(
        `Total heat ${heatPct.toFixed(1)}% exceeds the ${MAX_HEAT_PCT}% guideline of deployed base.`,
      );
    const topSector = sectorConcentration[0];
    if (topSector && topSector.sector !== 'Unknown' && topSector.pctOfBook > 40)
      flags.push(`${topSector.pctOfBook.toFixed(0)}% of the book is in ${topSector.sector} — concentrated.`);

    return {
      openPositions: open.length,
      deployedBase: round2(deployedBase),
      notional: round2(exposure),
      marginUsed: round2(marginUsed),
      marginUsedPct: round2(marginUsedPct),
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
