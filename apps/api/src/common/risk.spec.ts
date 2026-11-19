import { describe, expect, it } from 'vitest';
import { sizePosition } from './risk';

// Mirrors apps/engine/test/test_roadmap_fixes.py::test_per_trade_risk_cap_bounds_wide_stops.
// The two sizing functions MUST agree or the backtest stops predicting live.
describe('sizePosition', () => {
  it('takes the smaller of the notional and risk quantities', () => {
    // ₹10k fund at 1×, entry 78, stop 72.86: notional buys 128, the 2% cap allows 38.
    expect(sizePosition(10000, 200, 78, 78 - 72.86)).toBe(38);
  });

  it('falls back to the notional quantity when entry equals stop', () => {
    expect(sizePosition(10000, 200, 78, 0)).toBe(128);
  });

  it('returns 0 when one share breaks the risk budget', () => {
    expect(sizePosition(500, 10, 78, 38)).toBe(0);
  });

  it('returns 0 when one share costs more than the notional budget', () => {
    expect(sizePosition(10000, 200, 33980, 1980)).toBe(0);
  });

  it('returns 1 when exactly one share fits both bounds', () => {
    expect(sizePosition(10000, 200, 4000, 200)).toBe(1);
  });

  it('returns 0 for a non-positive or missing entry price', () => {
    expect(sizePosition(10000, 200, 0, 5)).toBe(0);
    expect(sizePosition(10000, 200, Number.NaN, 5)).toBe(0);
  });
});
