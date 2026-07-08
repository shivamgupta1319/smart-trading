import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { TradesService } from '../trades/trades.service';
import { TelegramService } from '../telegram/telegram.service';

const STALE_OPEN_DAYS = 5;
const DAILY_AT = 15 * 60 + 45; // 15:45 IST
const WEEKLY_AT = 15 * 60 + 50; // 15:50 IST Friday

/**
 * Scheduled Telegram performance digests. Dependency-free scheduler: a 60s tick
 * checks the IST clock and fires once/day (daily on weekdays, weekly on Friday).
 * In-memory day-guards prevent duplicate sends within the same day.
 */
@Injectable()
export class ReportsService implements OnModuleInit {
  private readonly logger = new Logger(ReportsService.name);
  private lastDaily = '';
  private lastWeekly = '';

  constructor(
    private readonly trades: TradesService,
    private readonly telegram: TelegramService,
  ) {}

  onModuleInit() {
    setInterval(() => {
      this.tick().catch((e) =>
        this.logger.error(`digest tick failed: ${e?.message || e}`),
      );
    }, 60_000);
    this.logger.log(
      'Reports scheduler started (daily 15:45 IST weekdays, weekly Fri 15:50 IST)',
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

  private async tick() {
    const { dateKey, weekday, minutes } = this.istNow();
    const isWeekday = weekday >= 1 && weekday <= 5;

    if (isWeekday && minutes >= DAILY_AT && this.lastDaily !== dateKey) {
      this.lastDaily = dateKey;
      await this.send('DAILY');
    }
    if (weekday === 5 && minutes >= WEEKLY_AT && this.lastWeekly !== dateKey) {
      this.lastWeekly = dateKey;
      await this.send('WEEKLY');
    }
  }

  private async send(period: 'DAILY' | 'WEEKLY') {
    try {
      const stats = await this.trades.getPortfolioStats();
      const open = await this.trades.findAll({ status: 'OPEN', limit: 500 });
      const now = Date.now();
      const staleOpens = open.filter(
        (t) =>
          (now - new Date(t.entryTime).getTime()) / 86_400_000 >=
          STALE_OPEN_DAYS,
      ).length;
      await this.telegram.sendPerformanceDigest({ period, stats, staleOpens });
      this.logger.log(`${period} performance digest sent`);
    } catch (e: any) {
      this.logger.error(`${period} digest failed: ${e?.message || e}`);
    }
  }
}
