import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { TelegramService } from '../telegram/telegram.service';
import axios, { AxiosInstance } from 'axios';
import { HttpsProxyAgent } from 'https-proxy-agent';
import * as crypto from 'crypto';

/**
 * DhanService — real-money execution adapter for the EMA_RSI validation test.
 *
 * SAFETY MODEL (see docs/dhan-live-execution.md):
 *  - Global default mode = "off": nothing here places or logs an order (pure sim, current behaviour).
 *  - "log":     logs the INTENDED order only. No Dhan API call. Zero risk. (Stage 1)
 *  - "sandbox": posts to Dhan's sandbox (real API, no capital).            (Stage 2)
 *  - "live":    posts real orders.                                         (Stage 3)
 *
 * The adapter computes its OWN order quantity (notional-capped) — it is deliberately
 * DECOUPLED from the simulated Trade.quantity, so the paper track record is untouched.
 * Only whitelisted (strategy, symbol) pairs are ever actionable.
 */

type Mode = 'off' | 'log' | 'sandbox' | 'live';
type Side = 'BUY' | 'SELL';

interface OpenPosition {
  symbol: string;
  side: Side;
  qty: number;
  simEntryPrice: number;
  orderId?: string;
  fillPrice?: number;
  stopPrice?: number; // original stop the resting broker SL is pegged to
  slOrderId?: string; // resting STOP_LOSS (limit) order id (catastrophic backstop)
}

// Hard whitelist: symbol -> Dhan NSE_EQ securityId (confirmed from Dhan scrip master).
const SECURITY_IDS: Record<string, string> = {
  HDFCBANK: '1333',
  ADANIENT: '25',
};
const ALLOWED_STRATEGY = 'EMA_RSI';

@Injectable()
export class DhanService {
  private readonly logger = new Logger(DhanService.name);

  private mode: Mode;
  private readonly clientId?: string;
  private readonly pin?: string;
  private readonly totpSecret?: string;
  private readonly manualToken?: string;
  private readonly baseUrl: string;

  // sizing / guardrails (all configurable via env)
  private readonly maxNotional: number; // per-order rupee cap → drives qty
  private readonly maxQty: number; // absolute per-order share cap
  private readonly maxOrdersPerDay: number;
  private readonly maxDailyLoss: number; // rupees; trips kill-switch
  private readonly slLimitBufferPct: number; // limit offset past the SL trigger (keeps it inside LPP)

  // Shared HTTP client for ALL Dhan calls. When DHAN_HTTP_PROXY is set, every request
  // (token generation AND order placement) egresses through the static-IP proxy — Dhan
  // requires the session/token to originate from the same whitelisted IP as the order.
  private readonly http: AxiosInstance;

  // runtime state
  private readonly openPositions = new Map<number, OpenPosition>(); // key = signalId
  private cachedToken?: { token: string; expiresAtMs: number };
  private dayKey = '';
  private ordersToday = 0;
  private realizedLossToday = 0;

  constructor(
    private readonly config: ConfigService,
    private readonly telegram: TelegramService,
  ) {
    this.mode = (this.config.get<string>('DHAN_TRADING_MODE') || 'off') as Mode;
    this.clientId = this.config.get<string>('DHAN_CLIENT_ID');
    this.pin = this.config.get<string>('DHAN_PIN');
    this.totpSecret = this.config.get<string>('DHAN_TOTP_SECRET');
    this.manualToken = this.config.get<string>('DHAN_ACCESS_TOKEN');
    this.baseUrl =
      this.config.get<string>('DHAN_API_BASE') || 'https://api.dhan.co/v2';

    this.maxNotional = Number(this.config.get('DHAN_MAX_NOTIONAL') ?? 12500);
    this.maxQty = Number(this.config.get('DHAN_MAX_QTY') ?? 20);
    this.maxOrdersPerDay = Number(this.config.get('DHAN_MAX_ORDERS_PER_DAY') ?? 20);
    this.maxDailyLoss = Number(this.config.get('DHAN_MAX_DAILY_LOSS') ?? 1000);
    this.slLimitBufferPct = Number(this.config.get('DHAN_SL_LIMIT_BUFFER_PCT') ?? 0.0015);

    // Static-IP egress: route every Dhan request through the proxy when configured.
    const proxyUrl = this.config.get<string>('DHAN_HTTP_PROXY');
    if (proxyUrl) {
      this.http = axios.create({ httpsAgent: new HttpsProxyAgent(proxyUrl), proxy: false });
      const masked = proxyUrl.replace(/\/\/[^@]*@/, '//***@'); // never log credentials
      this.logger.log(`[dhan] egress via static-IP proxy → ${masked}`);
    } else {
      this.http = axios.create();
    }

    this.logger.log(
      `DhanService mode=${this.mode} | whitelist=${ALLOWED_STRATEGY}:{${Object.keys(
        SECURITY_IDS,
      ).join(',')}} | maxNotional=₹${this.maxNotional} maxQty=${this.maxQty} ` +
        `maxOrders/day=${this.maxOrdersPerDay} killLoss=₹${this.maxDailyLoss}`,
    );
    if (this.mode !== 'off' && this.mode !== 'log' && !this.clientId) {
      this.logger.warn('DHAN_CLIENT_ID missing — sandbox/live orders will fail.');
    }
  }

  // ── public API ────────────────────────────────────────────────────────────

  /** Place (or log) the entry order for a newly created trade. No-op unless whitelisted. */
  async placeEntry(input: {
    signalId: number;
    symbol?: string;
    signalType: string;
    strategyName: string;
    entryPrice: number;
    stopLoss?: number;
  }): Promise<void> {
    if (this.mode === 'off') return;
    const symbol = input.symbol || '';
    if (!this.isWhitelisted(input.strategyName, symbol)) return;

    const side = input.signalType === 'BUY' ? 'BUY' : 'SELL';
    const qty = this.computeQty(input.entryPrice);
    if (qty < 1) {
      this.logger.warn(
        `[dhan] skip entry ${symbol}: computed qty=0 (price ₹${input.entryPrice} > notional cap ₹${this.maxNotional})`,
      );
      return;
    }

    this.rolloverDay();
    if (this.ordersToday >= this.maxOrdersPerDay) {
      this.logger.warn(`[dhan] skip entry ${symbol}: daily order cap (${this.maxOrdersPerDay}) reached`);
      return;
    }

    const exitSide: Side = side === 'BUY' ? 'SELL' : 'BUY';
    const stopPrice = input.stopLoss && input.stopLoss > 0 ? this.roundTick(input.stopLoss) : undefined;
    const tag = `${side} ${symbol} ×${qty} MIS MARKET (signal #${input.signalId})`;

    if (this.mode === 'log') {
      this.logger.log(`[dhan:LOG] INTENDED ENTRY → ${tag} | securityId=${SECURITY_IDS[symbol]}`);
      if (stopPrice) {
        this.logger.log(
          `[dhan:LOG] INTENDED PROTECTIVE STOP → ${exitSide} ${symbol} ×${qty} SL trigger ₹${stopPrice}`,
        );
      }
      this.openPositions.set(input.signalId, { symbol, side, qty, simEntryPrice: input.entryPrice, stopPrice });
      this.ordersToday++;
      return;
    }

    // sandbox / live
    try {
      const res = await this.postOrder({ transactionType: side, symbol, qty });
      const orderId = res?.orderId as string | undefined;
      const fillPrice = orderId ? await this.getFillPrice(orderId) : undefined;
      this.openPositions.set(input.signalId, {
        symbol,
        side,
        qty,
        simEntryPrice: input.entryPrice,
        orderId,
        fillPrice,
        stopPrice,
      });
      this.ordersToday++;
      this.logger.log(
        `[dhan:${this.mode}] ENTRY placed → ${tag} | orderId=${orderId} fill=₹${fillPrice ?? '?'} (sim ₹${input.entryPrice})`,
      );

      // Catastrophic backstop: rest a broker-side STOP_LOSS (limit) at the ORIGINAL stop.
      // Fail-open — the entry already exists; never undo it, just alert loudly if unprotected.
      if (stopPrice) {
        try {
          const sl = await this.postProtectiveStop({ transactionType: exitSide, symbol, qty, triggerPrice: stopPrice });
          const slOrderId = sl?.orderId as string | undefined;
          const pos = this.openPositions.get(input.signalId);
          if (pos) pos.slOrderId = slOrderId;
          this.logger.log(
            `[dhan:${this.mode}] protective SL placed → ${exitSide} ${symbol} ×${qty} trigger ₹${stopPrice} | slOrderId=${slOrderId}`,
          );
        } catch (slErr: any) {
          this.logger.error(
            `[dhan:${this.mode}] PROTECTIVE STOP FAILED for ${symbol} (signal #${input.signalId}): ${this.errMsg(slErr)}`,
          );
          void this.telegram
            .sendAlert(
              'DHAN: POSITION UNPROTECTED',
              `Entry filled but the broker stop-loss was REJECTED for <b>${symbol}</b> ×${qty} (signal #${input.signalId}). ` +
                `No resting SL at the broker — protected only by the soft engine stop and MIS EOD square-off. ` +
                `Error: ${this.errMsg(slErr)}`,
            )
            .catch(() => undefined);
        }
      } else {
        this.logger.warn(
          `[dhan:${this.mode}] no stopLoss provided for ${symbol} (signal #${input.signalId}) — NO broker stop placed`,
        );
      }
    } catch (err: any) {
      this.logger.error(`[dhan:${this.mode}] ENTRY FAILED ${tag}: ${this.errMsg(err)}`);
    }
  }

  /** Place (or log) the exit order that squares off a Dhan-managed position. No-op if not managed. */
  async placeExit(input: { signalId: number; symbol?: string; exitPrice: number }): Promise<void> {
    if (this.mode === 'off') return;
    const pos = this.openPositions.get(input.signalId);
    if (!pos) return; // not a Dhan-managed position

    const exitSide: Side = pos.side === 'BUY' ? 'SELL' : 'BUY';
    const tag = `${exitSide} ${pos.symbol} ×${pos.qty} MIS MARKET (signal #${input.signalId})`;

    if (this.mode === 'log') {
      const perShare = pos.side === 'BUY' ? input.exitPrice - pos.simEntryPrice : pos.simEntryPrice - input.exitPrice;
      if (pos.slOrderId || pos.stopPrice) {
        this.logger.log(`[dhan:LOG] INTENDED CANCEL protective SL (signal #${input.signalId})`);
      }
      this.logger.log(
        `[dhan:LOG] INTENDED EXIT → ${tag} | sim exit ₹${input.exitPrice} (sim P&L ≈ ₹${(perShare * pos.qty).toFixed(2)})`,
      );
      this.openPositions.delete(input.signalId);
      return;
    }

    // Coordinate with the resting broker stop BEFORE placing our own market exit.
    if (pos.slOrderId) {
      const status = await this.getOrderStatus(pos.slOrderId).catch(() => undefined);
      if (status?.orderStatus === 'TRADED') {
        // Broker stop already fired — position is flat. Reconcile from the SL fill; do NOT sell again.
        this.reconcileExit(pos, status.averageTradedPrice, tag, `SL fired orderId=${pos.slOrderId}`);
        this.openPositions.delete(input.signalId);
        return;
      }
      const cancelled = await this.cancelOrder(pos.slOrderId).then(() => true).catch(() => false);
      if (!cancelled) {
        // Cancel failed — it may have just triggered. Re-check once.
        const recheck = await this.getOrderStatus(pos.slOrderId).catch(() => undefined);
        if (recheck?.orderStatus === 'TRADED') {
          this.reconcileExit(pos, recheck.averageTradedPrice, tag, `SL fired mid-cancel orderId=${pos.slOrderId}`);
          this.openPositions.delete(input.signalId);
          return;
        }
        // Cannot confirm the SL is cancelled or filled — do NOT place a market exit (double-sell → net short).
        this.logger.error(
          `[dhan:${this.mode}] EXIT ABORTED ${tag}: could not cancel resting SL ${pos.slOrderId}. Leaving broker stop / MIS EOD to flatten.`,
        );
        void this.telegram
          .sendAlert(
            'DHAN: EXIT ABORTED (stop cancel failed)',
            `Could not cancel the resting stop for <b>${pos.symbol}</b> ×${pos.qty} (signal #${input.signalId}); ` +
              `skipped the market exit to avoid a double-sell. The position will be closed by the resting SL or MIS EOD square-off. Verify manually.`,
          )
          .catch(() => undefined);
        this.openPositions.delete(input.signalId);
        return;
      }
      this.logger.log(`[dhan:${this.mode}] cancelled protective SL ${pos.slOrderId} (signal #${input.signalId})`);
    }

    try {
      const res = await this.postOrder({ transactionType: exitSide, symbol: pos.symbol, qty: pos.qty });
      const orderId = res?.orderId as string | undefined;
      const exitFill = orderId ? await this.getFillPrice(orderId) : undefined;
      this.reconcileExit(pos, exitFill, tag, `market orderId=${orderId}`);
    } catch (err: any) {
      this.logger.error(`[dhan:${this.mode}] EXIT FAILED ${tag}: ${this.errMsg(err)}`);
    } finally {
      this.openPositions.delete(input.signalId);
    }
  }

  /** Log + book realized P&L for a completed exit (our market exit or a fired SL). Trips kill-switch on loss. */
  private reconcileExit(pos: OpenPosition, exitFill: number | undefined, tag: string, source: string): void {
    if (pos.fillPrice !== undefined && exitFill !== undefined) {
      const perShare = pos.side === 'BUY' ? exitFill - pos.fillPrice : pos.fillPrice - exitFill;
      const realPnl = perShare * pos.qty;
      if (realPnl < 0) this.realizedLossToday += -realPnl;
      this.logger.log(
        `[dhan:${this.mode}] EXIT → ${tag} | ${source} fill=₹${exitFill} realP&L=₹${realPnl.toFixed(2)}`,
      );
      this.checkKillSwitch();
    } else {
      this.logger.log(`[dhan:${this.mode}] EXIT → ${tag} | ${source} fill=₹${exitFill ?? '?'}`);
    }
  }

  // ── sizing & guards ─────────────────────────────────────────────────────────

  private isWhitelisted(strategyName: string, symbol: string): boolean {
    return strategyName === ALLOWED_STRATEGY && !!SECURITY_IDS[symbol];
  }

  /** qty = min(floor(maxNotional / price), maxQty). Notional cap keeps it ~1x (no leverage). */
  private computeQty(price: number): number {
    if (!price || price <= 0) return 0;
    return Math.min(Math.floor(this.maxNotional / price), this.maxQty);
  }

  private rolloverDay(): void {
    const key = new Date().toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' });
    if (key !== this.dayKey) {
      this.dayKey = key;
      this.ordersToday = 0;
      this.realizedLossToday = 0;
    }
  }

  private checkKillSwitch(): void {
    if (this.realizedLossToday >= this.maxDailyLoss && this.mode === 'live') {
      this.logger.error(
        `[dhan] KILL-SWITCH: daily loss ₹${this.realizedLossToday.toFixed(0)} ≥ ₹${this.maxDailyLoss}. Reverting mode → off.`,
      );
      this.mode = 'off';
      void this.telegram
        .sendReversalAlert({
          symbol: 'DHAN',
          exitPrice: 0,
          reason: `KILL-SWITCH tripped — daily loss ₹${this.realizedLossToday.toFixed(0)}. Live trading disabled.`,
        })
        .catch(() => undefined);
    }
  }

  // ── Dhan HTTP ───────────────────────────────────────────────────────────────

  private async postOrder(o: { transactionType: Side; symbol: string; qty: number }) {
    const body = {
      dhanClientId: this.clientId,
      transactionType: o.transactionType,
      exchangeSegment: 'NSE_EQ',
      productType: 'INTRADAY',
      orderType: 'MARKET',
      validity: 'DAY',
      securityId: SECURITY_IDS[o.symbol],
      quantity: String(o.qty),
    };
    return this.authed((token) =>
      this.http
        .post(`${this.baseUrl}/orders`, body, {
          headers: { 'access-token': token, 'Content-Type': 'application/json' },
          timeout: 10000,
        })
        .then((r) => r.data),
    );
  }

  /**
   * Rest a STOP_LOSS (limit) order — the catastrophic broker-side backstop (opposite side of the entry).
   * Dhan REJECTS a below-LTP SELL STOP_LOSS_MARKET ("Trigger Price should be greater than Price"), so we
   * use a limit SL and place the limit just past the trigger to fill like a market order in the common case:
   *   - SELL stop (protect a long):  limit < triggerPrice < LTP   (limit a hair BELOW the trigger)
   *   - BUY stop  (protect a short): LTP < triggerPrice < limit    (limit a hair ABOVE the trigger)
   * The limit buffer is kept small (default 0.15%) so it stays inside Dhan's Limit-Price-Protection band.
   * Worst case (a violent gap through the limit) the SL rests unfilled and MIS EOD square-off is the final net.
   */
  private async postProtectiveStop(o: {
    transactionType: Side;
    symbol: string;
    qty: number;
    triggerPrice: number;
  }) {
    const buf = this.slLimitBufferPct;
    const limit =
      o.transactionType === 'SELL'
        ? this.roundTick(o.triggerPrice * (1 - buf))
        : this.roundTick(o.triggerPrice * (1 + buf));
    const body = {
      dhanClientId: this.clientId,
      transactionType: o.transactionType,
      exchangeSegment: 'NSE_EQ',
      productType: 'INTRADAY',
      orderType: 'STOP_LOSS',
      validity: 'DAY',
      securityId: SECURITY_IDS[o.symbol],
      quantity: String(o.qty),
      price: limit.toFixed(2),
      triggerPrice: o.triggerPrice.toFixed(2),
    };
    return this.authed((token) =>
      this.http
        .post(`${this.baseUrl}/orders`, body, {
          headers: { 'access-token': token, 'Content-Type': 'application/json' },
          timeout: 10000,
        })
        .then((r) => r.data),
    );
  }

  /** Cancel a resting order by id. Throws on failure so the caller can react (e.g. re-check status). */
  private async cancelOrder(orderId: string): Promise<void> {
    await this.authed((token) =>
      this.http.delete(`${this.baseUrl}/orders/${orderId}`, {
        headers: { 'access-token': token },
        timeout: 10000,
      }),
    );
  }

  /** Read an order's status + average traded price. Throws on transport/auth failure. */
  private async getOrderStatus(
    orderId: string,
  ): Promise<{ orderStatus?: string; averageTradedPrice?: number }> {
    const data = await this.authed((token) =>
      this.http
        .get(`${this.baseUrl}/orders/${orderId}`, { headers: { 'access-token': token }, timeout: 10000 })
        .then((r) => r.data),
    );
    const d = Array.isArray(data) ? data[0] : data;
    const price = Number(d?.averageTradedPrice ?? d?.price);
    return {
      orderStatus: d?.orderStatus,
      averageTradedPrice: Number.isFinite(price) && price > 0 ? price : undefined,
    };
  }

  /** Fetch the average executed price for an order (best-effort; returns undefined if unavailable). */
  private async getFillPrice(orderId: string): Promise<number | undefined> {
    try {
      return (await this.getOrderStatus(orderId)).averageTradedPrice;
    } catch (err: any) {
      this.logger.warn(`[dhan] could not fetch fill for order ${orderId}: ${this.errMsg(err)}`);
      return undefined;
    }
  }

  /**
   * Run an authed Dhan request; on an auth error (a token invalidated out from under us by another
   * Dhan session — app login, concurrent token-gen, etc.) refresh the token once and retry.
   * Auth errors are pre-execution rejections, so a single retry cannot double-place an order.
   */
  private async authed<T>(fn: (token: string) => Promise<T>): Promise<T> {
    let token = await this.getToken();
    try {
      return await fn(token);
    } catch (err: any) {
      if (!this.isAuthError(err)) throw err;
      this.logger.warn('[dhan] auth error → refreshing token and retrying once');
      this.invalidateToken();
      token = await this.getToken();
      return await fn(token);
    }
  }

  private invalidateToken(): void {
    this.cachedToken = undefined;
  }

  private isAuthError(err: any): boolean {
    const status = err?.response?.status;
    const code = err?.response?.data?.errorCode;
    return status === 401 || code === 'DH-901' || code === 'DH-906';
  }

  /** Round to the NSE ₹0.05 tick — Dhan rejects off-tick trigger prices. */
  private roundTick(price: number): number {
    return Math.round(price / 0.05) * 0.05;
  }

  // ── token manager (TOTP auto-refresh) ────────────────────────────────────────

  private async getToken(): Promise<string> {
    if (this.cachedToken && this.cachedToken.expiresAtMs - Date.now() > 60_000) {
      return this.cachedToken.token;
    }
    // Preferred: self-generate a fresh 24h token via TOTP.
    if (this.clientId && this.pin && this.totpSecret) {
      const token = await this.generateAccessToken();
      if (token) return token;
    }
    // Fallback: manually-pasted 24h token from .env (used in early sandbox testing).
    if (this.manualToken) return this.manualToken;
    throw new Error('No Dhan access token available (set DHAN_TOTP_SECRET+PIN or DHAN_ACCESS_TOKEN)');
  }

  private async generateAccessToken(): Promise<string | undefined> {
    // Dhan expects dhanClientId/pin/totp as QUERY PARAMETERS (not a JSON body).
    try {
      const totp = totpCode(this.totpSecret as string);
      const qs =
        `dhanClientId=${encodeURIComponent(this.clientId as string)}` +
        `&pin=${encodeURIComponent(this.pin as string)}` +
        `&totp=${encodeURIComponent(totp)}`;
      const res = await this.http.post(
        `https://auth.dhan.co/app/generateAccessToken?${qs}`,
        null,
        { timeout: 10000 },
      );
      const token = res.data?.accessToken as string | undefined;
      const expiry = res.data?.expiryTime ? new Date(res.data.expiryTime).getTime() : Date.now() + 23 * 3600_000;
      if (token) {
        this.cachedToken = { token, expiresAtMs: expiry };
        this.logger.log('[dhan] access token refreshed via TOTP');
      }
      return token;
    } catch (err: any) {
      this.logger.error(`[dhan] TOTP token generation failed: ${this.errMsg(err)}`);
      return undefined;
    }
  }

  private errMsg(err: any): string {
    if (err?.response?.data) return JSON.stringify(err.response.data);
    if (err instanceof Error) return err.message;
    return String(err);
  }
}

// ── TOTP (RFC 6238, 6-digit / 30s / SHA1) using only Node crypto — no extra deps ──
function base32Decode(input: string): Buffer {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const clean = input.replace(/=+$/, '').toUpperCase().replace(/\s/g, '');
  let bits = '';
  for (const ch of clean) {
    const idx = alphabet.indexOf(ch);
    if (idx === -1) continue;
    bits += idx.toString(2).padStart(5, '0');
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(parseInt(bits.slice(i, i + 8), 2));
  }
  return Buffer.from(bytes);
}

function totpCode(secret: string, step = 30, digits = 6): string {
  const key = base32Decode(secret);
  const counter = Math.floor(Date.now() / 1000 / step);
  const buf = Buffer.alloc(8);
  buf.writeBigInt64BE(BigInt(counter));
  const hmac = crypto.createHmac('sha1', key).update(buf).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  const bin =
    ((hmac[offset] & 0x7f) << 24) |
    ((hmac[offset + 1] & 0xff) << 16) |
    ((hmac[offset + 2] & 0xff) << 8) |
    (hmac[offset + 3] & 0xff);
  return (bin % 10 ** digits).toString().padStart(digits, '0');
}
