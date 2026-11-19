import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { TelegramService } from '../telegram/telegram.service';
import { toNum } from '../common/money';
import {
  buildBooks,
  dueDigests,
  formatDigest,
  istClock,
  periodLabel,
  periodStart,
  STALE_OPEN_DAYS,
  type DigestData,
  type Period,
} from './digest';

/**
 * Sends the Telegram performance digests: daily at 15:45 IST on weekdays, and on Fridays
 * the week (15:50) and everything since the start (15:55).
 *
 * A 60-second tick checks the IST clock. Each digest is claimed in the `SentDigest` table
 * before it is sent, so a restart never sends a second copy.
 */
@Injectable()
export class ReportsService implements OnModuleInit {
  private readonly logger = new Logger(ReportsService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly telegram: TelegramService,
  ) {}

  onModuleInit() {
    setInterval(() => {
      this.tick().catch((e) => this.logger.error(`digest tick failed: ${e?.message || e}`));
    }, 60_000);
    this.logger.log('Digest scheduler started (daily 15:45, Friday 15:50 week, 15:55 since the start, IST)');
  }

  /** Atomically claim a (period, key) slot. False when it was already sent. */
  private async claim(period: Period, periodKey: string): Promise<boolean> {
    try {
      await this.prisma.sentDigest.create({ data: { period, periodKey } });
      return true;
    } catch (e: unknown) {
      if (typeof e === 'object' && e && (e as { code?: string }).code === 'P2002') return false;
      throw e;
    }
  }

  private async tick(now: Date = new Date()) {
    for (const { period, periodKey } of dueDigests(istClock(now))) {
      let claimed = false;
      try {
        claimed = await this.claim(period, periodKey);
      } catch (e: unknown) {
        this.logger.error(`digest claim failed (${period} ${periodKey}): ${e instanceof Error ? e.message : String(e)}`);
        continue;
      }
      if (claimed) await this.send(period, now);
    }
  }

  /** Gather the figures for one digest. Public so it can be previewed without sending. */
  async build(period: Period, now: Date = new Date()): Promise<DigestData> {
    const clock = istClock(now);
    const from = periodStart(period, clock);
    const exitWindow = from ? { exitTime: { gte: from, lte: now } } : {};

    const [closed, open, changed, cells] = await Promise.all([
      this.prisma.trade.findMany({
        where: { status: 'CLOSED', ...exitWindow },
        select: { strategyName: true, pnl: true, riskAmount: true, cellStatusAtEntry: true },
      }),
      this.prisma.trade.findMany({ where: { status: 'OPEN' }, select: { entryTime: true } }),
      this.prisma.activeConfiguration.findMany({
        where: from ? { statusChangedAt: { gte: from, lte: now } } : { statusChangedAt: { not: null } },
        include: { stock: true },
        orderBy: { statusChangedAt: 'desc' },
      }),
      this.prisma.activeConfiguration.groupBy({ by: ['status'], _count: { _all: true } }),
    ]);

    const count = (status: string) => cells.find((c) => c.status === status)?._count._all ?? 0;
    const staleBefore = now.getTime() - STALE_OPEN_DAYS * 86_400_000;
    return {
      period,
      label: periodLabel(period, clock),
      ...buildBooks(
        closed.map((t) => ({
          strategyName: t.strategyName,
          pnl: toNum(t.pnl),
          riskAmount: toNum(t.riskAmount),
          cellStatusAtEntry: t.cellStatusAtEntry,
        })),
      ),
      openTrades: open.length,
      staleOpens: open.filter((t) => t.entryTime.getTime() <= staleBefore).length,
      statusChanges: changed.map((c) => ({
        symbol: c.stock.symbol,
        strategyName: c.strategyName,
        status: c.status,
        reason: c.statusReason,
      })),
      cells: { testing: count('TESTING'), proven: count('PROVEN'), paused: count('PAUSED') },
    };
  }

  private async send(period: Period, now: Date) {
    try {
      const sent = await this.telegram.sendText(formatDigest(await this.build(period, now)));
      this.logger.log(sent ? `${period} digest sent` : `${period} digest not sent (Telegram is off)`);
    } catch (e: unknown) {
      this.logger.error(`${period} digest failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
}
