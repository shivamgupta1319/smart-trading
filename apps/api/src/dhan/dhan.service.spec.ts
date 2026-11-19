import { describe, expect, it, vi } from 'vitest';
import { DhanService, TOKEN_MIN_INTERVAL_MS, totpCode } from './dhan.service';

/**
 * The real-money layer with the broker faked. Nothing here talks to Dhan.
 * What is being protected: no real order without both locks, an open position can always be
 * exited, the daily loss limit stops entries only, and a failed stop or login is announced.
 */

type Row = Record<string, any>;

function fakePrisma(cell: Row | null) {
  const positions: Row[] = [];
  const daily: Row[] = [];
  let token: Row | null = null;
  return {
    _positions: positions,
    _setToken: (t: Row | null) => (token = t),
    activeConfiguration: { findUnique: vi.fn(async () => cell) },
    dhanPosition: {
      findMany: vi.fn(async ({ where }: any) => positions.filter((p) => !where?.status || p.status === where.status)),
      findFirst: vi.fn(async ({ where }: any) =>
        positions.find((p) => p.signalId === where.signalId && p.status === where.status) ?? null,
      ),
      count: vi.fn(async () => positions.filter((p) => p.status === 'OPEN' && p.orderId).length),
      upsert: vi.fn(async ({ where, create, update }: any) => {
        const i = positions.findIndex((p) => p.signalId === where.signalId);
        if (i >= 0) positions[i] = { ...positions[i], ...update };
        else positions.push({ ...create });
      }),
      updateMany: vi.fn(async ({ where, data }: any) => {
        for (const p of positions) if (p.signalId === where.signalId && p.status === where.status) Object.assign(p, data);
      }),
    },
    dhanDailyState: {
      findUnique: vi.fn(async ({ where }: any) => daily.find((d) => d.dayKey === where.dayKey) ?? null),
      upsert: vi.fn(async ({ where, create, update }: any) => {
        const i = daily.findIndex((d) => d.dayKey === where.dayKey);
        if (i >= 0) daily[i] = { ...daily[i], ...update };
        else daily.push({ ...create });
      }),
    },
    dhanToken: {
      findUnique: vi.fn(async () => token),
      upsert: vi.fn(async ({ create }: any) => {
        token = { ...create };
      }),
      deleteMany: vi.fn(async () => {
        token = null;
      }),
    },
  };
}

/** A broker that fills market orders at `fill` and reports stop orders as `stopStatus`. */
function fakeBroker(opts: { fill?: number; stopStatus?: string } = {}) {
  const calls: Array<{ method: string; url: string; body?: any }> = [];
  const orders = new Map<string, Row>();
  let n = 0;
  return {
    calls,
    orders,
    post: vi.fn(async (url: string, body?: any) => {
      calls.push({ method: 'POST', url, body });
      if (url.includes('generateAccessToken')) throw new Error('auth endpoint not expected in this test');
      const id = `${body.orderType === 'STOP_LOSS' ? 'S' : 'M'}${++n}`;
      orders.set(
        id,
        body.orderType === 'STOP_LOSS'
          ? { orderStatus: opts.stopStatus ?? 'PENDING' }
          : { orderStatus: 'TRADED', averageTradedPrice: opts.fill ?? 100 },
      );
      return { data: { orderId: id } };
    }),
    get: vi.fn(async (url: string) => {
      calls.push({ method: 'GET', url });
      if (url.endsWith('/positions')) return { data: [] };
      return { data: orders.get(url.split('/').pop() as string) ?? {} };
    }),
    delete: vi.fn(async (url: string) => {
      calls.push({ method: 'DELETE', url });
      const id = url.split('/').pop() as string;
      orders.set(id, { orderStatus: 'CANCELLED' });
      return { data: {} };
    }),
  };
}

const PROVEN_ON = { liveEnabled: true, status: 'PROVEN', stock: { dhanSecurityId: '3812' } };

function build(env: Record<string, string>, cell: Row | null = PROVEN_ON, broker = fakeBroker()) {
  const config = { get: (k: string) => env[k] };
  const telegram = { sendAlert: vi.fn(async () => true) };
  const prisma = fakePrisma(cell);
  const svc = new DhanService(config as any, telegram as any, prisma as any);
  (svc as any).http = broker;
  (svc as any).sleep = async () => undefined;
  return { svc, telegram, prisma, broker };
}

const LIVE = { DHAN_TRADING_MODE: 'live', DHAN_CLIENT_ID: 'C1', DHAN_ACCESS_TOKEN: 'manual-token' };
const ENTRY = {
  signalId: 7,
  stockId: 1,
  symbol: 'ZEEL',
  signalType: 'BUY',
  strategyName: 'MACD_Zero',
  entryPrice: 100,
  stopLoss: 98,
  holdDuration: 'INTRADAY',
};
const orderPosts = (b: ReturnType<typeof fakeBroker>) => b.calls.filter((c) => c.method === 'POST' && c.url.endsWith('/orders'));

describe('sizing', () => {
  it('defaults to one cell: ₹10k × 5 notional and ₹200 risk, the smaller of the two', () => {
    const { svc } = build(LIVE);
    expect(svc.computeQty(100, 98, 'INTRADAY')).toBe(100); // ₹200 / ₹2 risk; notional would allow 500
    expect(svc.computeQty(100, 99.9, 'INTRADAY')).toBe(500); // tight stop: the notional cap binds, then maxQty 500
    expect(svc.computeQty(60000, 59000, 'INTRADAY')).toBe(0); // one share is more than the budget
    expect(svc.computeQty(0, 0, 'INTRADAY')).toBe(0);
  });

  it('takes limits from the settings when given, and ignores blank ones', () => {
    const { svc } = build({ ...LIVE, DHAN_MAX_RISK: '100', DHAN_MAX_QTY: '', DHAN_MAX_NOTIONAL: '5000' });
    expect(svc.computeQty(100, 98, 'INTRADAY')).toBe(50); // ₹100 risk
    expect(svc.computeQty(100, 99.99, 'INTRADAY')).toBe(250); // ₹5,000 × 5 / 100
  });
});

describe('the two locks', () => {
  it('places nothing when the cell is not switched on, not PROVEN, or has no broker id', async () => {
    for (const cell of [
      null,
      { ...PROVEN_ON, liveEnabled: false },
      { ...PROVEN_ON, status: 'TESTING' },
      { ...PROVEN_ON, status: 'PAUSED' },
      { ...PROVEN_ON, stock: { dhanSecurityId: null } },
    ]) {
      const { svc, broker, prisma } = build(LIVE, cell);
      await svc.placeEntry(ENTRY);
      expect(orderPosts(broker)).toHaveLength(0);
      expect(prisma._positions).toHaveLength(0);
    }
  });

  it('places the entry and a resting stop when both locks pass', async () => {
    const { svc, broker, prisma } = build(LIVE, PROVEN_ON, fakeBroker({ fill: 100.1 }));
    await svc.placeEntry(ENTRY);
    const [entry, stop] = orderPosts(broker).map((c) => c.body);
    expect(entry).toMatchObject({ transactionType: 'BUY', orderType: 'MARKET', securityId: '3812', quantity: '100', productType: 'INTRADAY' });
    expect(stop).toMatchObject({ transactionType: 'SELL', orderType: 'STOP_LOSS', securityId: '3812', triggerPrice: '98.00' });
    expect(Number(stop.price)).toBeLessThan(98); // limit just below the trigger for a sell stop
    expect(prisma._positions[0]).toMatchObject({ signalId: 7, status: 'OPEN', securityId: '3812', fillPrice: 100.1, slOrderId: 'S2' });
  });

  it('places nothing in mode off even when both locks pass', async () => {
    const { svc, broker } = build({ ...LIVE, DHAN_TRADING_MODE: 'off' });
    await svc.placeEntry(ENTRY);
    expect(broker.calls).toHaveLength(0);
  });

  it('does not trade swing signals with real money', async () => {
    const { svc, broker } = build(LIVE);
    await svc.placeEntry({ ...ENTRY, holdDuration: 'SHORT_SWING' });
    expect(orderPosts(broker)).toHaveLength(0);
  });

  it('only logs in mode log: no broker call, and the exit is logged too', async () => {
    const { svc, broker, prisma } = build({ ...LIVE, DHAN_TRADING_MODE: 'log' });
    await svc.placeEntry(ENTRY);
    await svc.placeExit({ signalId: 7, exitPrice: 101 });
    expect(broker.calls).toHaveLength(0);
    expect(prisma._positions).toHaveLength(0);
  });
});

describe('exits never depend on the entry switch', () => {
  it('cancels the stop and exits at market, booking the result', async () => {
    const { svc, broker, prisma } = build(LIVE, PROVEN_ON, fakeBroker({ fill: 100 }));
    await svc.placeEntry(ENTRY);
    await svc.placeExit({ signalId: 7, exitPrice: 101 });
    expect(broker.calls.some((c) => c.method === 'DELETE' && c.url.endsWith('/S2'))).toBe(true);
    const exit = orderPosts(broker).pop()!.body;
    expect(exit).toMatchObject({ transactionType: 'SELL', orderType: 'MARKET', quantity: '100', securityId: '3812' });
    expect(prisma._positions[0]).toMatchObject({ status: 'CLOSED', closeReason: 'market', realizedPnl: 0 });
  });

  it('still exits after the daily loss limit has halted entries', async () => {
    const { svc, broker, prisma, telegram } = build({ ...LIVE, DHAN_MAX_DAILY_LOSS: '150' }, PROVEN_ON, fakeBroker({ fill: 100 }));
    await svc.placeEntry(ENTRY);
    broker.post.mockImplementationOnce(async (url: string, body: any) => {
      broker.calls.push({ method: 'POST', url, body });
      broker.orders.set('X1', { orderStatus: 'TRADED', averageTradedPrice: 98 }); // exit 2 lower: −₹200
      return { data: { orderId: 'X1' } };
    });
    await svc.placeExit({ signalId: 7, exitPrice: 98 });
    expect(prisma._positions[0]).toMatchObject({ status: 'CLOSED', realizedPnl: -200 });
    expect((await svc.status()).entriesHaltedToday).toBe(true);
    expect(telegram.sendAlert).toHaveBeenCalledWith('DHAN: daily loss limit reached', expect.any(String));

    // Entries are now refused...
    const before = orderPosts(broker).length;
    await svc.placeEntry({ ...ENTRY, signalId: 8 });
    expect(orderPosts(broker).length).toBe(before);
    // ...but the configured mode is untouched, so exits keep working.
    expect((await svc.status()).mode).toBe('live');
  });

  it('with the mode switched off while a real position is open, keeps exits alive and says so', async () => {
    const { svc, broker, prisma, telegram } = build({ ...LIVE, DHAN_TRADING_MODE: 'off' }, PROVEN_ON, fakeBroker({ fill: 99 }));
    prisma._positions.push({
      signalId: 7, symbol: 'ZEEL', securityId: '3812', side: 'BUY', qty: 100, simEntryPrice: 100,
      orderId: 'M1', fillPrice: 100, stopPrice: 98, slOrderId: null, status: 'OPEN',
    });
    await (svc as any).detectExitOnly();
    expect((await svc.status()).exitOnly).toBe(true);
    expect(telegram.sendAlert).toHaveBeenCalledWith('DHAN: open position while entries are off', expect.any(String));

    await svc.placeExit({ signalId: 7, exitPrice: 99 }); // not in memory: reloaded from the stored row
    expect(orderPosts(broker).pop()!.body).toMatchObject({ transactionType: 'SELL', orderType: 'MARKET', securityId: '3812' });
    expect(prisma._positions[0].status).toBe('CLOSED');

    await svc.placeEntry({ ...ENTRY, signalId: 9 }); // and still no new entries
    expect(orderPosts(broker)).toHaveLength(1);
  });

  it('does not sell twice when the resting stop has already fired', async () => {
    const { svc, broker, prisma } = build(LIVE, PROVEN_ON, fakeBroker({ fill: 100 }));
    await svc.placeEntry(ENTRY);
    broker.orders.set('S2', { orderStatus: 'TRADED', averageTradedPrice: 97.9 });
    const before = orderPosts(broker).length;
    await svc.placeExit({ signalId: 7, exitPrice: 98 });
    expect(orderPosts(broker).length).toBe(before); // no market exit on top of the fired stop
    expect(prisma._positions[0]).toMatchObject({ status: 'CLOSED', closeReason: 'SL fired', exitFillPrice: 97.9 });
  });
});

describe('protective stop', () => {
  it('retries once with a wider limit, then announces an unprotected position', async () => {
    const { svc, broker, telegram, prisma } = build(LIVE, PROVEN_ON, fakeBroker({ fill: 100, stopStatus: 'REJECTED' }));
    await svc.placeEntry(ENTRY);
    const stops = orderPosts(broker).filter((c) => c.body.orderType === 'STOP_LOSS').map((c) => Number(c.body.price));
    expect(stops).toHaveLength(2);
    expect(stops[1]).toBeLessThan(stops[0]); // wider buffer on the retry
    expect(telegram.sendAlert).toHaveBeenCalledWith('DHAN: POSITION UNPROTECTED', expect.stringContaining('ZEEL'));
    expect(prisma._positions[0].slOrderId).toBeNull();
    expect(prisma._positions[0].status).toBe('OPEN'); // the entry is kept; only the protection failed
  });
});

describe('login token', () => {
  const TOTP_ENV = { ...LIVE, DHAN_ACCESS_TOKEN: '', DHAN_PIN: '1234', DHAN_TOTP_SECRET: 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ' };

  it('matches the RFC 6238 test vectors', () => {
    const secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'; // base32 of "12345678901234567890"
    expect(totpCode(secret, 59_000)).toBe('287082');
    expect(totpCode(secret, 1111111109_000)).toBe('081804');
    expect(totpCode(secret, 1234567890_000)).toBe('005924');
  });

  it('reuses a stored token after a restart instead of asking Dhan again', async () => {
    const { svc, broker, prisma } = build(TOTP_ENV);
    prisma._setToken({ id: 1, token: 'stored-token', expiresAt: new Date(Date.now() + 3600_000) });
    expect(await (svc as any).getToken()).toBe('stored-token');
    expect(broker.post).not.toHaveBeenCalled();
  });

  it('generates and stores a token, sending the PIN and code as query parameters', async () => {
    const { svc, broker, prisma } = build(TOTP_ENV);
    broker.post.mockImplementationOnce(async (url: string) => {
      broker.calls.push({ method: 'POST', url });
      return { data: { accessToken: 'fresh-token' } };
    });
    expect(await (svc as any).getToken()).toBe('fresh-token');
    expect(broker.calls[0].url).toMatch(/generateAccessToken\?dhanClientId=C1&pin=1234&totp=\d{6}$/);
    expect(prisma.dhanToken.upsert).toHaveBeenCalled();
  });

  it('waits out Dhan’s two-minute limit and alerts once when login fails', async () => {
    const { svc, broker, telegram } = build(TOTP_ENV);
    broker.post.mockImplementation(async () => {
      throw new Error('getaddrinfo ENOTFOUND auth.dhan.co');
    });
    await expect((svc as any).getToken()).rejects.toThrow('No Dhan access token available');
    await expect((svc as any).getToken()).rejects.toThrow(); // inside the 2-minute window
    expect(broker.post).toHaveBeenCalledTimes(1); // the second attempt never reached Dhan
    expect(telegram.sendAlert).toHaveBeenCalledTimes(1);
    expect(telegram.sendAlert).toHaveBeenCalledWith('DHAN: could not log in', expect.any(String));
    expect(TOKEN_MIN_INTERVAL_MS).toBeGreaterThanOrEqual(120_000);
  });
});

describe('status', () => {
  it('reports mode, limits and open positions, and no credentials', async () => {
    const { svc } = build(LIVE);
    await svc.placeEntry(ENTRY);
    const s = await svc.status();
    expect(s).toMatchObject({ mode: 'live', entriesAllowed: true, exitOnly: false, credentialsConfigured: true });
    expect(s.limits).toMatchObject({ notionalPerOrder: 50000, riskPerOrder: 200, maxDailyLoss: 600 });
    expect(s.openPositions).toHaveLength(1);
    expect(JSON.stringify(s)).not.toContain('manual-token');
  });
});
