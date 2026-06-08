import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

@Injectable()
export class AdminService {
  private readonly logger = new Logger(AdminService.name);

  constructor(private prisma: PrismaService) {}

  /**
   * Wipe the paper-trading state: all trades, all live signals, and all active
   * (stock × strategy) configurations. PRESERVES the stock universe, NSE master
   * list, historical OHLCV, and stored backtest reports.
   *
   * Order matters only as defence-in-depth — deleting a LiveSignal cascades to
   * its Trade — but we delete Trade first so the count is accurate and the call
   * is safe regardless of cascade configuration.
   */
  async reset() {
    const result = await this.prisma.$transaction(async (tx) => {
      const trades = await tx.trade.deleteMany({});
      const signals = await tx.liveSignal.deleteMany({});
      const configs = await tx.activeConfiguration.deleteMany({});
      return {
        tradesDeleted: trades.count,
        signalsDeleted: signals.count,
        activeConfigsDeleted: configs.count,
      };
    });

    this.logger.warn(
      `Paper-trading RESET: ${result.tradesDeleted} trades, ${result.signalsDeleted} signals, ` +
        `${result.activeConfigsDeleted} active configs deleted. Stocks/history/backtests preserved.`,
    );
    return {
      ok: true,
      ...result,
      preserved: ['Stock', 'NseStock', 'HistoricalData', 'BacktestReport'],
    };
  }
}
