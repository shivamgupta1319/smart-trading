import { describe, expect, it } from 'vitest';
import { cellStats, evaluateCell, lifecycleRules, type ClosedTrade, type LifecycleRules } from './lifecycle';

const rules: LifecycleRules = {
  windowTrades: 20,
  pauseAvgR: -0.15,
  pauseLossPct: 0.15,
  resumeAvgR: 0.05,
  provenMinTrades: 40,
  provenAvgR: 0.1,
  provenProfitFactor: 1.3,
};
const BASE = 10000;
const t = (r: number, risk = 200): ClosedTrade => ({ pnl: r * risk, riskAmount: risk });
const many = (n: number, r: number): ClosedTrade[] => Array.from({ length: n }, () => t(r));
const stats = (trades: ClosedTrade[]) => cellStats(trades, rules.windowTrades);

describe('cellStats', () => {
  it('summarises a cell and splits it into halves', () => {
    const s = stats([...many(10, 1), ...many(10, -1)]);
    expect(s.trades).toBe(20);
    expect(s.winRate).toBe(50);
    expect(s.avgR).toBeCloseTo(0);
    expect(s.firstHalfR).toBeCloseTo(1);
    expect(s.secondHalfR).toBeCloseTo(-1);
    expect(s.profitFactor).toBeCloseTo(1);
  });

  it('ignores trades with no recorded risk when averaging R', () => {
    expect(stats([t(1), { pnl: 500, riskAmount: 0 }]).avgR).toBeCloseTo(1);
  });

  it('is empty-safe', () => {
    const s = stats([]);
    expect(s.trades).toBe(0);
    expect(s.avgR).toBeNull();
    expect(s.winRate).toBeNull();
  });
});

describe('evaluateCell', () => {
  it('reads its thresholds from config/trading.json', () => {
    expect(lifecycleRules()).toEqual(rules);
  });

  it('keeps a young cell in TESTING however bad it looks', () => {
    expect(evaluateCell('TESTING', stats(many(19, -1)), 19, BASE, rules).status).toBe('TESTING');
  });

  it('pauses a cell whose last 20 trades average below the limit', () => {
    const r = evaluateCell('TESTING', stats(many(20, -0.2)), 20, BASE, rules);
    expect(r.status).toBe('PAUSED');
    expect(r.reason).toContain('-0.20R');
  });

  it('pauses on the rupee loss limit even when the average R looks tolerable', () => {
    // 20 trades averaging -0.1R (above the -0.15R limit) but risking Rs 1,000 each: -Rs 2,000.
    const r = evaluateCell('TESTING', stats(Array.from({ length: 20 }, () => t(-0.1, 1000))), 20, BASE, rules);
    expect(r.status).toBe('PAUSED');
    expect(r.reason).toContain('lost');
  });

  it('judges the RECENT window, so an old good run does not hide a bad one', () => {
    const r = evaluateCell('TESTING', stats([...many(60, 0.5), ...many(20, -0.5)]), 80, BASE, rules);
    expect(r.status).toBe('PAUSED');
  });

  it('does not resume a paused cell on the same trades that paused it', () => {
    const r = evaluateCell('PAUSED', stats(many(20, 0.5)), 5, BASE, rules);
    expect(r.status).toBe('PAUSED');
  });

  it('resumes a paused cell after a full window of good new trades', () => {
    const r = evaluateCell('PAUSED', stats([...many(20, -0.3), ...many(20, 0.2)]), 20, BASE, rules);
    expect(r.status).toBe('TESTING');
    expect(r.reason).toContain('Resumed');
  });

  it('keeps a paused cell paused while its new trades are still poor', () => {
    expect(evaluateCell('PAUSED', stats([...many(20, -0.3), ...many(20, 0.0)]), 20, BASE, rules).status).toBe('PAUSED');
  });

  it('marks a cell PROVEN only with enough trades, an edge, and both halves positive', () => {
    const good = [...many(12, 1), ...many(8, -0.6), ...many(12, 1), ...many(8, -0.6)]; // 40 trades
    expect(evaluateCell('TESTING', stats(good), 40, BASE, rules).status).toBe('PROVEN');
    // Same quality but only 30 trades: not yet.
    expect(evaluateCell('TESTING', stats(good.slice(0, 30)), 30, BASE, rules).status).toBe('TESTING');
    // Great first half, flat-to-negative second half: not proven.
    const lopsided = [...many(20, 1), ...many(10, 0.3), ...many(10, -0.4)];
    expect(evaluateCell('TESTING', stats(lopsided), 40, BASE, rules).status).toBe('TESTING');
  });

  it('demotes a PROVEN cell that no longer qualifies, with a reason', () => {
    const r = evaluateCell('PROVEN', stats(many(40, 0.02)), 40, BASE, rules);
    expect(r.status).toBe('TESTING');
    expect(r.reason).toContain('No longer');
  });
});
