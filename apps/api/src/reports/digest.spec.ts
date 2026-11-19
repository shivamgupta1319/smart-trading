import { describe, expect, it } from 'vitest';
import {
  buildBooks,
  dueDigests,
  formatDigest,
  istClock,
  periodLabel,
  periodStart,
  startOfIstWeek,
  summariseBook,
  type DigestData,
  type DigestTrade,
} from './digest';

// 2026-11-19 is a Thursday, 2026-11-20 a Friday. Times below are UTC; IST = UTC + 5:30.
const at = (iso: string) => istClock(new Date(iso));

describe('IST clock', () => {
  it('converts an instant to the IST date, weekday and minute of day', () => {
    expect(at('2026-11-19T10:15:00Z')).toEqual({ dateKey: '2026-11-19', weekday: 4, minutes: 15 * 60 + 45 });
    // 20:00 UTC is already the next day in India.
    expect(at('2026-11-19T20:00:00Z')).toEqual({ dateKey: '2026-11-20', weekday: 5, minutes: 90 });
  });

  it('finds the Monday that starts the week', () => {
    expect(startOfIstWeek(at('2026-11-20T10:00:00Z')).toISOString()).toBe('2026-11-15T18:30:00.000Z'); // Mon 16 Nov 00:00 IST
    expect(startOfIstWeek(at('2026-11-22T10:00:00Z')).toISOString()).toBe('2026-11-15T18:30:00.000Z'); // Sunday belongs to that week
  });
});

describe('when a digest is due', () => {
  it('sends nothing before 15:45 and the daily digest from 15:45 on a weekday', () => {
    expect(dueDigests(at('2026-11-19T10:14:00Z'))).toEqual([]); // 15:44 Thu
    expect(dueDigests(at('2026-11-19T10:15:00Z'))).toEqual([{ period: 'DAILY', periodKey: '2026-11-19' }]);
    // Still due late in the evening, so a restart after 15:45 does not lose it.
    expect(dueDigests(at('2026-11-19T17:00:00Z'))).toEqual([{ period: 'DAILY', periodKey: '2026-11-19' }]);
  });

  it('adds the weekly and since-the-start digests on Friday, keyed so each is sent once', () => {
    expect(dueDigests(at('2026-11-20T10:26:00Z'))).toEqual([
      { period: 'DAILY', periodKey: '2026-11-20' },
      { period: 'WEEKLY', periodKey: '2026-11-16' }, // keyed by that week's Monday
      { period: 'OVERALL', periodKey: '2026-11-20' },
    ]);
    expect(dueDigests(at('2026-11-20T10:21:00Z')).map((d) => d.period)).toEqual(['DAILY', 'WEEKLY']); // 15:51
  });

  it('sends nothing at the weekend', () => {
    expect(dueDigests(at('2026-11-21T11:00:00Z'))).toEqual([]);
    expect(dueDigests(at('2026-11-22T11:00:00Z'))).toEqual([]);
  });
});

describe('period covered', () => {
  const fri = at('2026-11-20T10:26:00Z');
  it('starts at IST midnight today, Monday for the week, and has no start for everything', () => {
    expect(periodStart('DAILY', fri)?.toISOString()).toBe('2026-11-19T18:30:00.000Z');
    expect(periodStart('WEEKLY', fri)?.toISOString()).toBe('2026-11-15T18:30:00.000Z');
    expect(periodStart('OVERALL', fri)).toBeUndefined();
  });
  it('is labelled in plain dates', () => {
    expect(periodLabel('DAILY', fri)).toBe('20 Nov 2026');
    expect(periodLabel('WEEKLY', fri)).toBe('16 Nov 2026 to 20 Nov 2026');
  });
});

const t = (strategyName: string, pnl: number, status: string | null = 'TESTING', riskAmount = 200): DigestTrade => ({
  strategyName,
  pnl,
  riskAmount,
  cellStatusAtEntry: status,
});

describe('books', () => {
  it('keeps trades taken while a cell was paused out of the main book', () => {
    const b = buildBooks([t('RVOL_ORB', 400), t('RVOL_ORB', -200), t('EMA_RSI', -210, 'PAUSED'), t('MACD_Zero', 100, null)]);
    expect(b.main).toMatchObject({ trades: 3, wins: 2, netPnl: 300 });
    expect(b.main.avgR).toBeCloseTo((2 - 1 + 0.5) / 3);
    expect(b.test).toMatchObject({ trades: 1, wins: 0, netPnl: -210 });
    expect(b.byStrategy.map((s) => s.strategyName)).toEqual(['RVOL_ORB', 'MACD_Zero']); // best first, test book excluded
  });

  it('is empty-safe', () => {
    expect(summariseBook([])).toEqual({ trades: 0, wins: 0, winRate: null, netPnl: 0, avgR: null });
  });
});

describe('message', () => {
  const base: DigestData = {
    period: 'DAILY',
    label: '20 Nov 2026',
    ...buildBooks([t('RVOL_ORB', 400), t('RVOL_ORB', -200), t('EMA_RSI', -210, 'PAUSED')]),
    openTrades: 6,
    staleOpens: 1,
    statusChanges: [{ symbol: 'M&M', strategyName: 'EMA_RSI', status: 'PAUSED', reason: 'Paused: last 20 trades average -0.40R' }],
    cells: { testing: 380, proven: 2, paused: 5 },
  };

  it('states the main book after costs, the test book apart, and status changes', () => {
    const m = formatDigest(base);
    expect(m).toContain('<b>Smart Trading: Today</b>');
    expect(m).toContain('<b>Main book:</b> +₹200 after costs');
    expect(m).toContain('2 closed, 1 won (50%), average +0.50R');
    expect(m).toContain('(paused cells, not counted above): −₹210 over 1 trade');
    expect(m).toContain('M&amp;M EMA RSI: paused. Paused: last 20 trades average -0.40R'); // HTML-escaped
    expect(m).toContain('Open now: 6 (1 open 5+ days)');
    expect(m).toContain('Cells: 2 proven, 380 testing, 5 paused');
  });

  it('says so plainly when nothing closed', () => {
    const m = formatDigest({ ...base, ...buildBooks([]), statusChanges: [] });
    expect(m).toContain('No paper trades closed in this period.');
    expect(m).not.toContain('Main book');
  });
});
