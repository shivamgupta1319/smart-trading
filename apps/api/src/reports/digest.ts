/**
 * Telegram performance digests — the parts that are pure logic (no clock, no database),
 * so they can be tested: when a digest is due, what period it covers, how trades are
 * summarised and how the message reads.
 *
 * Numbers are AFTER costs (Trade.pnl is booked net). Trades opened while their cell was
 * PAUSED belong to the test book and are reported separately, never mixed into the main
 * figures.
 */

export type Period = 'DAILY' | 'WEEKLY' | 'OVERALL';

export const DAILY_AT = 15 * 60 + 45; // 15:45 IST, weekdays: today
export const WEEKLY_AT = 15 * 60 + 50; // 15:50 IST, Friday: this week
export const OVERALL_AT = 15 * 60 + 55; // 15:55 IST, Friday: since the start
export const STALE_OPEN_DAYS = 5;

export interface IstClock {
  dateKey: string; // YYYY-MM-DD in IST
  weekday: number; // 0 = Sunday … 6 = Saturday
  minutes: number; // minutes since IST midnight
}

const WEEKDAYS: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

/** The IST wall clock for an instant. IST is a fixed UTC+05:30 with no daylight saving. */
export function istClock(at: Date): IstClock {
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
  }).formatToParts(at)) {
    parts[p.type] = p.value;
  }
  const hour = parts.hour === '24' ? 0 : parseInt(parts.hour, 10);
  return {
    dateKey: `${parts.year}-${parts.month}-${parts.day}`,
    weekday: WEEKDAYS[parts.weekday] ?? -1,
    minutes: hour * 60 + parseInt(parts.minute, 10),
  };
}

export const startOfIstDay = (dateKey: string): Date => new Date(`${dateKey}T00:00:00+05:30`);

/** Monday 00:00 IST of the week containing this clock's day. */
export function startOfIstWeek(clock: IstClock): Date {
  const daysSinceMonday = (clock.weekday + 6) % 7; // Mon→0 … Sun→6
  return new Date(startOfIstDay(clock.dateKey).getTime() - daysSinceMonday * 86_400_000);
}

/**
 * Which digests are due at this clock, each with the key that makes it once-only.
 * A digest stays due for the rest of its day, so a restart after 15:45 still sends it;
 * the stored key is what stops a second copy.
 */
export function dueDigests(clock: IstClock): Array<{ period: Period; periodKey: string }> {
  const due: Array<{ period: Period; periodKey: string }> = [];
  const isWeekday = clock.weekday >= 1 && clock.weekday <= 5;
  if (isWeekday && clock.minutes >= DAILY_AT) due.push({ period: 'DAILY', periodKey: clock.dateKey });
  if (clock.weekday === 5 && clock.minutes >= WEEKLY_AT) {
    due.push({ period: 'WEEKLY', periodKey: istClock(startOfIstWeek(clock)).dateKey });
  }
  if (clock.weekday === 5 && clock.minutes >= OVERALL_AT) {
    due.push({ period: 'OVERALL', periodKey: clock.dateKey });
  }
  return due;
}

/** Start of the period a digest covers; undefined means "since the start". */
export function periodStart(period: Period, clock: IstClock): Date | undefined {
  if (period === 'DAILY') return startOfIstDay(clock.dateKey);
  if (period === 'WEEKLY') return startOfIstWeek(clock);
  return undefined;
}

const fmtDate = (d: Date): string =>
  new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric' }).format(d);

export function periodLabel(period: Period, clock: IstClock): string {
  if (period === 'DAILY') return fmtDate(startOfIstDay(clock.dateKey));
  if (period === 'WEEKLY') return `${fmtDate(startOfIstWeek(clock))} to ${fmtDate(startOfIstDay(clock.dateKey))}`;
  return 'Since the start';
}

export interface DigestTrade {
  strategyName: string;
  pnl: number; // net of costs
  riskAmount: number;
  cellStatusAtEntry: string | null;
}

export interface BookSummary {
  trades: number;
  wins: number;
  winRate: number | null;
  netPnl: number;
  avgR: number | null;
}

export function summariseBook(trades: DigestTrade[]): BookSummary {
  const wins = trades.filter((t) => t.pnl > 0).length;
  const rs = trades.filter((t) => t.riskAmount > 0).map((t) => t.pnl / t.riskAmount);
  return {
    trades: trades.length,
    wins,
    winRate: trades.length ? (100 * wins) / trades.length : null,
    netPnl: trades.reduce((s, t) => s + t.pnl, 0),
    avgR: rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : null,
  };
}

export interface DigestData {
  period: Period;
  label: string;
  main: BookSummary;
  test: BookSummary;
  byStrategy: Array<{ strategyName: string; trades: number; netPnl: number }>; // main book
  openTrades: number;
  staleOpens: number;
  statusChanges: Array<{ symbol: string; strategyName: string; status: string; reason: string | null }>;
  cells: { testing: number; proven: number; paused: number };
}

/** Split closed trades into the two books and rank strategies by main-book result. */
export function buildBooks(trades: DigestTrade[]): Pick<DigestData, 'main' | 'test' | 'byStrategy'> {
  const main = trades.filter((t) => t.cellStatusAtEntry !== 'PAUSED');
  const test = trades.filter((t) => t.cellStatusAtEntry === 'PAUSED');
  const per = new Map<string, { trades: number; netPnl: number }>();
  for (const t of main) {
    const row = per.get(t.strategyName) ?? { trades: 0, netPnl: 0 };
    row.trades += 1;
    row.netPnl += t.pnl;
    per.set(t.strategyName, row);
  }
  const byStrategy = [...per.entries()]
    .map(([strategyName, v]) => ({ strategyName, ...v }))
    .sort((a, b) => b.netPnl - a.netPnl);
  return { main: summariseBook(main), test: summariseBook(test), byStrategy };
}

const rupees = (n: number): string => `${n < 0 ? '−' : n > 0 ? '+' : ''}₹${Math.abs(Math.round(n)).toLocaleString('en-IN')}`;
const signedR = (r: number | null): string => (r === null ? 'n/a' : `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r).toFixed(2)}R`);
const esc = (s: string): string => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const nice = (name: string): string => esc(name.replace(/_/g, ' '));

const TITLE: Record<Period, string> = {
  DAILY: 'Today',
  WEEKLY: 'This week',
  OVERALL: 'Since the start',
};

/** The Telegram message (HTML parse mode). Plain words, figures after costs. */
export function formatDigest(d: DigestData): string {
  const lines: string[] = [`<b>Smart Trading: ${TITLE[d.period]}</b>`, esc(d.label), ''];

  if (d.main.trades === 0 && d.test.trades === 0) {
    lines.push('No paper trades closed in this period.');
  } else {
    lines.push(
      `<b>Main book:</b> ${rupees(d.main.netPnl)} after costs`,
      d.main.trades === 0
        ? 'No trades closed.'
        : `${d.main.trades} closed, ${d.main.wins} won (${(d.main.winRate ?? 0).toFixed(0)}%), average ${signedR(d.main.avgR)}`,
    );
    if (d.byStrategy.length > 0) {
      const best = d.byStrategy[0];
      const worst = d.byStrategy[d.byStrategy.length - 1];
      lines.push(`Best: ${nice(best.strategyName)} ${rupees(best.netPnl)} (${best.trades})`);
      if (d.byStrategy.length > 1) {
        lines.push(`Worst: ${nice(worst.strategyName)} ${rupees(worst.netPnl)} (${worst.trades})`);
      }
    }
    if (d.test.trades > 0) {
      lines.push(
        '',
        `<b>Test book</b> (paused cells, not counted above): ${rupees(d.test.netPnl)} over ${d.test.trades} ${d.test.trades === 1 ? 'trade' : 'trades'}`,
      );
    }
  }

  if (d.statusChanges.length > 0) {
    lines.push('', '<b>Status changes</b>');
    for (const c of d.statusChanges.slice(0, 8)) {
      lines.push(`${esc(c.symbol)} ${nice(c.strategyName)}: ${c.status.toLowerCase()}${c.reason ? `. ${esc(c.reason)}` : ''}`);
    }
    if (d.statusChanges.length > 8) lines.push(`and ${d.statusChanges.length - 8} more`);
  }

  lines.push(
    '',
    `Open now: ${d.openTrades}${d.staleOpens > 0 ? ` (${d.staleOpens} open ${STALE_OPEN_DAYS}+ days)` : ''}`,
    `Cells: ${d.cells.proven} proven, ${d.cells.testing} testing, ${d.cells.paused} paused`,
  );
  return lines.join('\n');
}
