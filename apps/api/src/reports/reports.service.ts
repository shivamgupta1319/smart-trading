import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { TradesService } from '../trades/trades.service';
import { TelegramService } from '../telegram/telegram.service';
import { PrismaService } from '../prisma/prisma.service';

const STALE_OPEN_DAYS = 5;
const DAILY_AT = 15 * 60 + 45; // 15:45 IST (weekdays) — today's performance
const WEEKLY_AT = 15 * 60 + 50; // 15:50 IST (Friday) — this week's performance
const OVERALL_AT = 15 * 60 + 55; // 15:55 IST (Friday) — all-time performance

type Period = 'DAILY' | 'WEEKLY' | 'OVERALL';

/**
 * Scheduled Telegram performance digests. A dependency-free 60s tick checks the
 * IST clock and fires: DAILY on weekdays (today), WEEKLY on Fridays (Mon→now),
 * and OVERALL on Fridays (all-time). Duplicate sends are prevented by a persisted
 * `SentDigest` claim (survives container restarts — in-memory guards did not).
 */
@Injectable()
export class ReportsService implements OnModuleInit {
  private readonly logger = new Logger(ReportsService.name);

  constructor(
    private readonly trades: TradesService,
    private readonly telegram: TelegramService,
    private readonly prisma: PrismaService,
  ) {}

  onModuleInit() {
    setInterval(() => {
      this.tick().catch((e) =>
        this.logger.error(`digest tick failed: ${e?.message || e}`),
      );
    }, 60_000);
    this.logger.log(
      'Reports scheduler started (daily 15:45, weekly Fri 15:50, overall Fri 15:55 IST)',
    );
  }

  private istNow(): { dateKey: string; weekday: number; minutes: number } {
    const parts: Record<string, string> = {};
    for (const p of new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      weekday: 'short',
      hour12: false,
    }).formatToParts(new Date())) {
      parts[p.type] = p.value;
    }
    const wd: Record<string, number> = {
      Sun: 0,
      Mon: 1,
      Tue: 2,
      Wed: 3,
      Thu: 4,
      Fri: 5,
      Sat: 6,
    };
    const hour = parts.hour === '24' ? 0 : parseInt(parts.hour, 10);
    return {
      dateKey: `${parts.year}-${parts.month}-${parts.day}`,
      weekday: wd[parts.weekday] ?? -1,
      minutes: hour * 60 + parseInt(parts.minute, 10),
    };
  }

  // ── IST date boundaries (IST is a fixed UTC+05:30, no DST) ─────────────────
  private startOfTodayUtc(dateKey: string): Date {
    return new Date(`${dateKey}T00:00:00+05:30`);
  }

  private startOfWeekUtc(dateKey: string, weekday: number): Date {
    const daysSinceMonday = (weekday + 6) % 7; // Mon→0, Fri→4, Sun→6, Sat→5
    return new Date(
      this.startOfTodayUtc(dateKey).getTime() - daysSinceMonday * 86_400_000,
    );
  }

  private istRange(
    period: Period,
    now: { dateKey: string; weekday: number },
  ): { from: Date; to: Date } | undefined {
    if (period === 'DAILY') return { from: this.startOfTodayUtc(now.dateKey), to: new Date() };
    if (period === 'WEEKLY')
      return { from: this.startOfWeekUtc(now.dateKey, now.weekday), to: new Date() };
    return undefined; // OVERALL = all-time
  }

  private istDateKeyOf(d: Date): string {
    const p: Record<string, string> = {};
    for (const part of new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(d)) {
      p[part.type] = part.value;
    }
    return `${p.year}-${p.month}-${p.day}`;
  }

  private fmtIstDate(d: Date): string {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(d);
  }

  private weekKey(now: { dateKey: string; weekday: number }): string {
    return this.istDateKeyOf(this.startOfWeekUtc(now.dateKey, now.weekday));
  }

  private rangeLabel(
    period: Period,
    now: { dateKey: string; weekday: number },
  ): string {
    if (period === 'DAILY') return this.fmtIstDate(this.startOfTodayUtc(now.dateKey));
    if (period === 'WEEKLY')
      return `${this.fmtIstDate(this.startOfWeekUtc(now.dateKey, now.weekday))} – ${this.fmtIstDate(this.startOfTodayUtc(now.dateKey))}`;
    return 'All-time';
  }

  // ── scheduling / idempotency ──────────────────────────────────────────────
  /** Atomically claim a (period, periodKey) slot. Returns false if already sent. */
  private async claim(period: Period, periodKey: string): Promise<boolean> {
    try {
      await this.prisma.sentDigest.create({ data: { period, periodKey } });
      return true;
    } catch (e: any) {
      if (e?.code === 'P2002') return false; // unique violation → already sent
      throw e; // e.g. table missing before migration — caught by caller, digest skipped
    }
  }

  private async maybeSend(period: Period, periodKey: string) {
    let claimed = false;
    try {
      claimed = await this.claim(period, periodKey);
    } catch (e: any) {
      this.logger.error(`digest claim failed (${period} ${periodKey}): ${e?.message || e}`);
      return;
    }
    if (!claimed) return;
    await this.send(period);
  }

  private async tick() {
    const now = this.istNow();
    const isWeekday = now.weekday >= 1 && now.weekday <= 5;

    if (isWeekday && now.minutes >= DAILY_AT) {
      await this.maybeSend('DAILY', now.dateKey);
    }
    if (now.weekday === 5 && now.minutes >= WEEKLY_AT) {
      await this.maybeSend('WEEKLY', this.weekKey(now));
    }
    if (now.weekday === 5 && now.minutes >= OVERALL_AT) {
      await this.maybeSend('OVERALL', now.dateKey);
    }
  }

  private async send(period: Period) {
    try {
      const now = this.istNow();
      const range = this.istRange(period, now);
      const stats = await this.trades.getPortfolioStats(range);
      const open = await this.trades.findAll({ status: 'OPEN', limit: 500 });
      const nowMs = Date.now();
      const staleOpens = open.filter(
        (t) =>
          (nowMs - new Date(t.entryTime).getTime()) / 86_400_000 >=
          STALE_OPEN_DAYS,
      ).length;
      await this.telegram.sendPerformanceDigest({
        period,
        stats,
        staleOpens,
        tradeCount: stats.periodTradeCount,
        rangeLabel: this.rangeLabel(period, now),
      });
      this.logger.log(`${period} performance digest sent`);
    } catch (e: any) {
      this.logger.error(`${period} digest failed: ${e?.message || e}`);
    }
  }
}
