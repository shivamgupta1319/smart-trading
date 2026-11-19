import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { toNum } from '../common/money';
import { BASE_CELL_CAPITAL } from '../common/risk';
import {
  cellStats,
  evaluateCell,
  lifecycleRules,
  type CellStats,
  type CellStatus,
  type ClosedTrade,
} from '../common/lifecycle';

type TradeRow = { pnl: unknown; riskAmount: unknown; exitTime: Date | null; cellStatusAtEntry: string | null };

/** Applies the lifecycle rules (common/lifecycle.ts) to the cells in the database. */
@Injectable()
export class LifecycleService {
  private readonly logger = new Logger(LifecycleService.name);

  constructor(private prisma: PrismaService) {}

  private async closedTrades(stockId: number, strategyName: string): Promise<TradeRow[]> {
    return this.prisma.trade.findMany({
      where: { stockId, strategyName, status: 'CLOSED' },
      orderBy: [{ exitTime: 'asc' }, { id: 'asc' }],
      select: { pnl: true, riskAmount: true, exitTime: true, cellStatusAtEntry: true },
    });
  }

  private static toClosed(rows: TradeRow[]): ClosedTrade[] {
    return rows.map((r) => ({ pnl: toNum(r.pnl as never), riskAmount: toNum(r.riskAmount as never) }));
  }

  /**
   * Re-evaluate one cell and store a changed status. Safe to call after every close;
   * returns the status now in force (or null when the cell is not on the roster).
   */
  async evaluate(stockId: number, strategyName: string): Promise<CellStatus | null> {
    const config = await this.prisma.activeConfiguration.findUnique({
      where: { stockId_strategyName: { stockId, strategyName } },
      include: { stock: true },
    });
    if (!config) return null;

    const rows = await this.closedTrades(stockId, strategyName);
    const rules = lifecycleRules();
    const stats = cellStats(LifecycleService.toClosed(rows), rules.windowTrades);
    const changedAt = config.statusChangedAt;
    const sinceChange = changedAt
      ? rows.filter((r) => r.exitTime && r.exitTime > changedAt).length
      : rows.length;

    const current = config.status as CellStatus;
    const next = evaluateCell(current, stats, sinceChange, BASE_CELL_CAPITAL, rules);
    if (next.status !== current) {
      await this.prisma.activeConfiguration.update({
        where: { id: config.id },
        data: { status: next.status, statusReason: next.reason, statusChangedAt: new Date() },
      });
      this.logger.warn(
        `Cell ${config.stock.symbol} · ${strategyName}: ${current} → ${next.status}. ${next.reason}`,
      );
    }
    return next.status;
  }

  /** Re-evaluate every cell on the roster. Returns how many changed. */
  async evaluateAll(): Promise<{ cells: number; changed: number }> {
    const configs = await this.prisma.activeConfiguration.findMany({
      select: { stockId: true, strategyName: true, status: true },
    });
    let changed = 0;
    for (const c of configs) {
      const after = await this.evaluate(c.stockId, c.strategyName);
      if (after && after !== c.status) changed += 1;
    }
    return { cells: configs.length, changed };
  }

  /**
   * One row per cell on the roster: its status and reason, its live paper record
   * (after costs), and its latest backtest next to it. Trades taken while the cell
   * was PAUSED are counted separately (the test book).
   */
  async scorecard() {
    const configs = await this.prisma.activeConfiguration.findMany({
      include: { stock: true },
      orderBy: [{ strategyName: 'asc' }, { stockId: 'asc' }],
    });
    if (configs.length === 0) return [];
    const stockIds = [...new Set(configs.map((c) => c.stockId))];
    const [trades, reports] = await Promise.all([
      this.prisma.trade.findMany({
        where: { stockId: { in: stockIds }, status: 'CLOSED' },
        orderBy: [{ exitTime: 'asc' }, { id: 'asc' }],
        select: {
          stockId: true, strategyName: true, pnl: true, riskAmount: true,
          exitTime: true, cellStatusAtEntry: true,
        },
      }),
      this.prisma.backtestReport.findMany({ where: { stockId: { in: stockIds } } }),
    ]);
    const open = await this.prisma.trade.groupBy({
      by: ['stockId', 'strategyName'],
      where: { stockId: { in: stockIds }, status: 'OPEN' },
      _count: { _all: true },
    });

    const key = (stockId: number, strategyName: string) => `${stockId}|${strategyName}`;
    const byCell = new Map<string, typeof trades>();
    for (const tr of trades) {
      const k = key(tr.stockId, tr.strategyName);
      if (!byCell.has(k)) byCell.set(k, []);
      byCell.get(k)!.push(tr);
    }
    const reportByCell = new Map(reports.map((r) => [key(r.stockId, r.strategyName), r]));
    const openByCell = new Map(open.map((o) => [key(o.stockId, o.strategyName), o._count._all]));
    const rules = lifecycleRules();

    return configs.map((c) => {
      const k = key(c.stockId, c.strategyName);
      const rows = byCell.get(k) ?? [];
      const live: CellStats = cellStats(LifecycleService.toClosed(rows), rules.windowTrades);
      const main = rows.filter((r) => r.cellStatusAtEntry !== 'PAUSED');
      const test = rows.filter((r) => r.cellStatusAtEntry === 'PAUSED');
      const sum = (xs: typeof rows) => xs.reduce((s, r) => s + toNum(r.pnl as never), 0);
      const bt = reportByCell.get(k);
      return {
        id: c.id,
        symbol: c.stock.symbol,
        // Set by the engine when this stock's price history has a large move nobody has reviewed.
        dataFlag: c.stock.dataFlag,
        dataFlagDetail: c.stock.dataFlagDetail,
        strategyName: c.strategyName,
        timeframe: c.timeframe,
        status: c.status,
        statusReason: c.statusReason,
        statusChangedAt: c.statusChangedAt,
        openTrades: openByCell.get(k) ?? 0,
        live,
        mainBook: { trades: main.length, netPnl: sum(main) },
        testBook: { trades: test.length, netPnl: sum(test) },
        backtest: bt
          ? {
              trades: bt.totalTrades,
              winRate: bt.winRate,
              avgR: bt.avgRMultiple,
              profitFactor: bt.profitFactor,
              netProfit: bt.netProfit,
              engineVersion: bt.engineVersion,
              updatedAt: bt.updatedAt,
            }
          : null,
      };
    });
  }
}
