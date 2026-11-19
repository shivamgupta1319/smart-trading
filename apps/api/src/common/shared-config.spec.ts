import { afterEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';
import { MAX_COST_TO_RISK, costToRisk, roundTripCost, slippagePerShare } from './costs';
import { BASE_CELL_CAPITAL, LEVERAGE_DELIVERY, LEVERAGE_INTRADAY, RISK_PER_TRADE_PCT } from './risk';
import { riskPerTradeFraction, shared } from './shared-config';

// The Python twin is apps/engine/test/test_shared_config.py — it asserts the SAME
// golden numbers, which is what proves the two runtimes agree.
const file = JSON.parse(
  readFileSync(join(process.cwd(), 'config', 'trading.json'), 'utf8'),
) as { capital: Record<string, number> };

describe('shared trading config', () => {
  afterEach(() => {
    delete process.env.LEVERAGE_INTRADAY;
    delete process.env.RISK_PER_TRADE_PCT;
  });

  it('API constants come from the file', () => {
    expect(BASE_CELL_CAPITAL).toBe(file.capital.BASE_CELL_CAPITAL);
    expect(LEVERAGE_INTRADAY).toBe(file.capital.LEVERAGE_INTRADAY);
    expect(LEVERAGE_DELIVERY).toBe(file.capital.LEVERAGE_DELIVERY);
    expect(RISK_PER_TRADE_PCT).toBe(file.capital.RISK_PER_TRADE_PCT);
  });

  it('golden costs match the Python twin', () => {
    expect(roundTripCost(100000, 101000, 'INTRADAY')).toBeCloseTo(82.695246, 6);
    expect(roundTripCost(10000, 10300, 'SHORT_SWING')).toBeCloseTo(37.2817338, 6);
  });

  it('cost-to-risk matches the Python twin', () => {
    expect(MAX_COST_TO_RISK).toBe(file.capital.MAX_COST_TO_RISK);
    // A Rs 817.50 stock with a Rs 1.20 stop: the costs are 140% of the risk.
    expect(costToRisk(61, 817.5, 1.2, 'INTRADAY')).toBeCloseTo(1.403437675, 8);
    expect(costToRisk(30, 1600, 26, 'INTRADAY')).toBeCloseTo(0.1267748923, 8);
    // Rs 78 and Rs 60.54 shares: one tick is more than 5 basis points, so the tick applies.
    expect(costToRisk(38, 78, 5.14, 'SHORT_SWING')).toBeCloseTo(0.1286928153, 8);
    expect(costToRisk(350, 60.54, 0.57, 'INTRADAY')).toBeCloseTo(0.2880315258, 8);
    expect(slippagePerShare(60)).toBeCloseTo(0.05, 10);
    expect(slippagePerShare(4000)).toBeCloseTo(2, 10);
  });

  it('an environment variable overrides the file', () => {
    process.env.LEVERAGE_INTRADAY = '3';
    expect(shared('LEVERAGE_INTRADAY')).toBe(3);
  });

  it('an unknown key is an error, not a silent default', () => {
    expect(() => shared('NOT_A_REAL_SETTING')).toThrow();
  });

  it.each(['2', '0', '-0.02', '0.5'])('refuses a percent-style risk value (%s)', (bad) => {
    process.env.RISK_PER_TRADE_PCT = bad;
    expect(() => riskPerTradeFraction()).toThrow();
  });
});
