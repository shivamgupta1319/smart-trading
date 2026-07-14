import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { TelegramService } from '../telegram/telegram.service';
import { PrismaService } from '../prisma/prisma.service';
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

// EOD square-off backstop window (IST minutes-of-day). We force-flatten any still-open real
// position starting 15:12 — 2 min after the scanner's primary 15:10 close, and before Dhan's
// ~15:18–15:20 MIS auto-square (which charges a penalty). We stop trying at 15:20.
const EOD_SQUAREOFF_MIN = 15 * 60 + 12; // 15:12 IST
const EOD_SQUAREOFF_END_MIN = 15 * 60 + 20; // 15:20 IST

@Injectable()
export class DhanService implements OnModuleInit {
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
  private killedToday = false; // daily-loss kill-switch tripped (persisted so a restart can't undo it)

  constructor(
    private readonly config: ConfigService,
    private readonly telegram: TelegramService,
    private readonly prisma: PrismaService,
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

  // ── boot: rehydrate + reconcile durable state (survives api restart) ─────────

  /**
   * On startup, reload persisted positions and the daily kill-switch state so an api
   * restart never orphans an open position or silently re-enables live trading. Fully
   * defensive: any error (incl. a missing table before the migration is applied) is
   * logged and skipped — the api must never crash-loop on boot.
   */
  async onModuleInit(): Promise<void> {
    try {
      await this.restoreDailyState();
    } catch (err: any) {
      this.logger.error(`[dhan:boot] daily-state restore skipped: ${this.errMsg(err)}`);
    }
    // Always run the EOD square-off timer — it self-checks mode + IST window each tick, so it is
    // a no-op in off/log mode and survives a mid-day mode flip (e.g. kill-switch → off).
    this.startEodSquareOffTimer();
    if (this.mode === 'off' || this.mode === 'log') return;
    try {
      await this.reconcileOpenPositions();
    } catch (err: any) {
      this.logger.error(`[dhan:boot] position reconcile skipped: ${this.errMsg(err)}`);
    }
  }

  // ── EOD square-off backstop ──────────────────────────────────────────────────

  /** IST minutes-of-day + weekday (0=Sun..6=Sat), mirroring ReportsService.istNow(). */
  private istClock(): { weekday: number; minutes: number } {
    const parts: Record<string, string> = {};
    for (const p of new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      weekday: 'short',
      hour12: false,
    }).formatToParts(new Date())) {
      parts[p.type] = p.value;
    }
    const wd: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
    const hour = parts.hour === '24' ? 0 : parseInt(parts.hour, 10);
    return { weekday: wd[parts.weekday] ?? -1, minutes: hour * 60 + parseInt(parts.minute, 10) };
  }

  /**
   * A dependency-free 60s tick (same pattern as ReportsService) that force-flattens any open real
   * position inside the 15:12–15:20 IST window. squareOffAllOpen is idempotent, so firing several
   * times in the window automatically retries a transient failure before Dhan's auto-square.
   */
  private startEodSquareOffTimer(): void {
    setInterval(() => {
      try {
        if (this.mode !== 'live' && this.mode !== 'sandbox') return;
        const { weekday, minutes } = this.istClock();
        const inWindow =
          weekday >= 1 && weekday <= 5 && minutes >= EOD_SQUAREOFF_MIN && minutes < EOD_SQUAREOFF_END_MIN;
        if (!inWindow) return;
        void this.squareOffAllOpen('EOD 15:12 square-off').catch((e: any) =>
          this.logger.error(`[dhan] EOD square-off failed: ${this.errMsg(e)}`),
        );
      } catch (e: any) {
        this.logger.error(`[dhan] EOD square-off tick error: ${this.errMsg(e)}`);
      }
    }, 60_000);
    this.logger.log('[dhan] EOD square-off timer started (force-flatten open positions 15:12–15:20 IST).');
  }

  /**
   * Force every still-open whitelisted position flat, driven by BROKER TRUTH (Dhan netQty) rather
   * than the in-memory map — so it catches orphans left by restarts, aborted exits, or missed
   * scanner closes. Cancels any resting SL, places a MARKET exit for the actual net qty, books P&L,
   * and closes the durable row. Idempotent: once the broker is flat there is nothing to do.
   */
  async squareOffAllOpen(reason: string): Promise<void> {
    if (this.mode === 'off' || this.mode === 'log') return;
    this.rolloverDay();

    const openRows = await this.prisma.dhanPosition.findMany({ where: { status: 'OPEN' } });
    if (openRows.length === 0) return;

    const broker = await this.getPositions();
    if (broker === null) {
      this.logger.error(`[dhan] ${reason}: could not read broker positions — will retry next tick.`);
      return;
    }
    const netQtyFor = (symbol: string): number =>
      broker
        .filter((p) => p.tradingSymbol === symbol)
        .reduce((sum, p) => sum + Number(p.netQty || 0), 0);

    for (const row of openRows) {
      if (!SECURITY_IDS[row.symbol]) continue; // can only trade whitelisted symbols
      const net = netQtyFor(row.symbol);

      if (net === 0) {
        // Broker already flat (SL fired / manual / prior sweep) — just close the durable row.
        this.logger.log(`[dhan] ${reason}: ${row.symbol} (signal #${row.signalId}) already flat at broker — marking CLOSED.`);
        await this.closePosition(row.signalId, { closeReason: `${reason}: already flat` });
        this.openPositions.delete(row.signalId);
        continue;
      }

      const posSide: Side = net > 0 ? 'BUY' : 'SELL'; // long if net>0
      const exitSide: Side = net > 0 ? 'SELL' : 'BUY';
      const qty = Math.abs(net);

      // Cancel the resting SL first so it can't fire during our market exit (→ double-sell).
      if (row.slOrderId) {
        const cancelled = await this.cancelOrder(row.slOrderId).then(() => true).catch(() => false);
        if (!cancelled) {
          const st = await this.getOrderStatus(row.slOrderId).catch(() => undefined);
          if (st?.orderStatus === 'TRADED') {
            this.logger.log(`[dhan] ${reason}: ${row.symbol} SL already fired — marking CLOSED.`);
            await this.closePosition(row.signalId, {
              exitOrderId: row.slOrderId,
              exitFillPrice: st.averageTradedPrice,
              closeReason: `${reason}: SL fired`,
            });
            this.openPositions.delete(row.signalId);
            continue;
          }
          this.logger.error(
            `[dhan] ${reason}: could not cancel SL ${row.slOrderId} for ${row.symbol} (not TRADED) — skipping market exit this tick to avoid a double-sell.`,
          );
          continue; // next tick retries
        }
      }

      const tag = `${exitSide} ${row.symbol} ×${qty} MIS MARKET (signal #${row.signalId})`;
      try {
        const res = await this.postOrder({ transactionType: exitSide, symbol: row.symbol, qty });
        const orderId = res?.orderId as string | undefined;
        const fill = orderId ? await this.pollFill(orderId) : undefined;
        // Reconcile P&L from the in-memory position if present, else from the durable row.
        const pos: OpenPosition = this.openPositions.get(row.signalId) ?? {
          symbol: row.symbol,
          side: posSide,
          qty,
          simEntryPrice: row.simEntryPrice,
          orderId: row.orderId ?? undefined,
          fillPrice: row.fillPrice ?? undefined,
          stopPrice: row.stopPrice ?? undefined,
          slOrderId: row.slOrderId ?? undefined,
        };
        const pnl = this.reconcileExit(pos, fill, tag, `${reason} orderId=${orderId}`);
        await this.closePosition(row.signalId, {
          exitOrderId: orderId,
          exitFillPrice: fill,
          realizedPnl: pnl,
          closeReason: reason,
        });
        this.openPositions.delete(row.signalId);
        this.logger.log(`[dhan] ${reason}: flattened ${tag} | orderId=${orderId} fill=₹${fill ?? '?'}`);
      } catch (err: any) {
        this.logger.error(`[dhan] ${reason}: EXIT FAILED ${tag}: ${this.errMsg(err)} — will retry next tick.`);
      }
    }
  }

  /** Reload today's guardrail counters; re-arm the kill-switch if it had tripped. */
  private async restoreDailyState(): Promise<void> {
    this.rolloverDay(); // sets this.dayKey (and persists a fresh row for a new day)
    const row = await this.prisma.dhanDailyState.findUnique({ where: { dayKey: this.dayKey } });
    if (!row) return;
    this.realizedLossToday = row.realizedLossToday;
    this.ordersToday = row.ordersToday;
    this.killedToday = row.killed;
    if (row.killed && this.mode === 'live') {
      this.mode = 'off';
      this.logger.error(
        `[dhan:boot] kill-switch was tripped today (loss ₹${row.realizedLossToday.toFixed(0)}) — forcing mode=off (NOT re-enabling live).`,
      );
    } else if (this.ordersToday || this.realizedLossToday) {
      this.logger.log(
        `[dhan:boot] restored daily state: orders=${this.ordersToday} realizedLoss=₹${this.realizedLossToday.toFixed(0)}`,
      );
    }
  }

  /**
   * Reload OPEN positions and reconcile each against Dhan's ACTUAL positions/orders.
   * NEVER places an order here — it only rehydrates the in-memory map (so the normal
   * scanner-driven exit can act) or marks a row CLOSED if the broker is already flat.
   */
  private async reconcileOpenPositions(): Promise<void> {
    const rows = await this.prisma.dhanPosition.findMany({ where: { status: 'OPEN' } });
    if (rows.length === 0) {
      this.logger.log('[dhan:boot] no open positions to reconcile.');
      return;
    }
    const brokerPositions = await this.getPositions();
    const brokerReadOk = brokerPositions !== null; // null = couldn't reach broker (never treat as flat)
    const netQtyFor = (symbol: string): number =>
      (brokerPositions ?? [])
        .filter((p) => p.tradingSymbol === symbol)
        .reduce((sum, p) => sum + Number(p.netQty || 0), 0);

    for (const row of rows) {
      const pos: OpenPosition = {
        symbol: row.symbol,
        side: row.side as Side,
        qty: row.qty,
        simEntryPrice: row.simEntryPrice,
        orderId: row.orderId ?? undefined,
        fillPrice: row.fillPrice ?? undefined,
        stopPrice: row.stopPrice ?? undefined,
        slOrderId: row.slOrderId ?? undefined,
      };
      const brokerNet = netQtyFor(row.symbol);

      // If the resting stop already fired while we were down, the position is flat.
      // (Runs regardless of the positions read — getOrderStatus is an independent call.)
      if (pos.slOrderId) {
        const slStatus = await this.getOrderStatus(pos.slOrderId).catch(() => undefined);
        if (slStatus?.orderStatus === 'TRADED') {
          this.reconcileExit(pos, slStatus.averageTradedPrice, `reconcile #${row.signalId}`, `SL fired (boot)`);
          await this.closePosition(row.signalId, {
            exitOrderId: pos.slOrderId,
            exitFillPrice: slStatus.averageTradedPrice,
            closeReason: 'SL fired (reconciled on boot)',
          });
          continue;
        }
        if (slStatus && slStatus.orderStatus !== 'PENDING' && slStatus.orderStatus !== 'TRANSIT') {
          this.logger.warn(
            `[dhan:boot] signal #${row.signalId} resting SL is ${slStatus.orderStatus} — position now UNPROTECTED.`,
          );
          pos.slOrderId = undefined;
        }
      }

      if (brokerReadOk && brokerNet === 0) {
        // Broker DEFINITIVELY flat — exited while we were down (MIS square / manual / SL). Close the row.
        this.logger.log(`[dhan:boot] signal #${row.signalId} (${row.symbol}) flat at broker — marking CLOSED.`);
        await this.closePosition(row.signalId, { closeReason: 'reconciled-flat-on-boot' });
        continue;
      }

      // Broker still holds it, OR we couldn't read the broker (brokerReadOk=false) → keep the row
      // OPEN and rehydrate the in-memory map so the normal exit path + EOD sweep can close it later.
      // We never mark flat on an unknown read — that was the bug that orphaned positions to MIS EOD.
      this.openPositions.set(row.signalId, pos);
      this.logger.log(
        `[dhan:boot] rehydrated signal #${row.signalId}: ${pos.side} ${pos.symbol} ×${pos.qty} ` +
          `(brokerNet=${brokerReadOk ? brokerNet : 'unknown'}, sl=${pos.slOrderId ?? 'none'}).`,
      );
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
      const fillPrice = orderId ? await this.pollFill(orderId) : undefined;
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
      await this.persistPosition(input.signalId); // durable BEFORE the SL step, in case it fails
      await this.persistDailyState();
      this.logger.log(
        `[dhan:${this.mode}] ENTRY placed → ${tag} | orderId=${orderId} fill=₹${fillPrice ?? '?'} (sim ₹${input.entryPrice})`,
      );

      // Catastrophic backstop: rest a broker-side STOP_LOSS (limit) at the ORIGINAL stop.
      // Fail-open — the entry already exists; never undo it, just alert loudly if unprotected.
      if (stopPrice) {
        await this.armProtectiveStop(input.signalId, exitSide, symbol, qty, stopPrice);
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
        const pnl = this.reconcileExit(pos, status.averageTradedPrice, tag, `SL fired orderId=${pos.slOrderId}`);
        await this.closePosition(input.signalId, {
          exitOrderId: pos.slOrderId,
          exitFillPrice: status.averageTradedPrice,
          realizedPnl: pnl,
          closeReason: 'SL fired',
        });
        this.openPositions.delete(input.signalId);
        return;
      }
      const cancelled = await this.cancelOrder(pos.slOrderId).then(() => true).catch(() => false);
      if (!cancelled) {
        // Cancel failed — it may have just triggered. Re-check once.
        const recheck = await this.getOrderStatus(pos.slOrderId).catch(() => undefined);
        if (recheck?.orderStatus === 'TRADED') {
          const pnl = this.reconcileExit(pos, recheck.averageTradedPrice, tag, `SL fired mid-cancel orderId=${pos.slOrderId}`);
          await this.closePosition(input.signalId, {
            exitOrderId: pos.slOrderId,
            exitFillPrice: recheck.averageTradedPrice,
            realizedPnl: pnl,
            closeReason: 'SL fired mid-cancel',
          });
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
      const exitFill = orderId ? await this.pollFill(orderId) : undefined;
      const pnl = this.reconcileExit(pos, exitFill, tag, `market orderId=${orderId}`);
      await this.closePosition(input.signalId, {
        exitOrderId: orderId,
        exitFillPrice: exitFill,
        realizedPnl: pnl,
        closeReason: 'market',
      });
    } catch (err: any) {
      // Exit didn't happen — DB row stays OPEN so a later boot-reconcile can catch it.
      this.logger.error(`[dhan:${this.mode}] EXIT FAILED ${tag}: ${this.errMsg(err)} — position left OPEN for reconcile.`);
    } finally {
      this.openPositions.delete(input.signalId);
    }
  }

  /**
   * Place the resting protective STOP_LOSS and CONFIRM the broker accepted it. Dhan can flip an
   * order to REJECTED asynchronously after returning an orderId (off-tick / LPP band), so we poll:
   *   - accepted  → store slOrderId, done.
   *   - REJECTED  → retry ONCE with a wider limit buffer (the first order is dead, so no double-SL
   *                 risk). If the retry is also rejected → clear slOrderId + "UNPROTECTED" alert.
   *   - unknown   → keep the orderId (it may be resting) and warn; never retry on unknown (would
   *                 risk two live stops → an oversell when one fires).
   * Always fail-open: the entry stays; this only governs the broker-side protection.
   */
  private async armProtectiveStop(
    signalId: number,
    exitSide: Side,
    symbol: string,
    qty: number,
    triggerPrice: number,
  ): Promise<void> {
    const setSl = async (slOrderId: string | undefined) => {
      const pos = this.openPositions.get(signalId);
      if (pos) pos.slOrderId = slOrderId;
      await this.persistPosition(signalId);
    };

    try {
      const sl = await this.postProtectiveStop({ transactionType: exitSide, symbol, qty, triggerPrice });
      const slOrderId = sl?.orderId as string | undefined;
      await setSl(slOrderId);
      const accepted = slOrderId ? await this.pollAccepted(slOrderId) : false;

      if (accepted === true) {
        this.logger.log(
          `[dhan:${this.mode}] protective SL accepted → ${exitSide} ${symbol} ×${qty} trigger ₹${triggerPrice} | slOrderId=${slOrderId}`,
        );
        return;
      }
      if (accepted === undefined) {
        this.logger.warn(
          `[dhan:${this.mode}] protective SL status UNKNOWN for ${symbol} (signal #${signalId}) slOrderId=${slOrderId} — assuming resting; verify manually.`,
        );
        return;
      }

      // Definitively rejected → the first order is dead. Retry once with a wider limit buffer.
      this.logger.error(
        `[dhan:${this.mode}] protective SL REJECTED for ${symbol} (signal #${signalId}) — retrying once with a wider buffer.`,
      );
      const retry = await this.postProtectiveStop({
        transactionType: exitSide,
        symbol,
        qty,
        triggerPrice,
        bufferPct: this.slLimitBufferPct * 2,
      });
      const retryId = retry?.orderId as string | undefined;
      await setSl(retryId);
      const retryAccepted = retryId ? await this.pollAccepted(retryId) : false;

      if (retryAccepted === true) {
        this.logger.log(
          `[dhan:${this.mode}] protective SL accepted on retry → ${exitSide} ${symbol} ×${qty} | slOrderId=${retryId}`,
        );
        return;
      }
      if (retryAccepted === undefined) {
        this.logger.warn(
          `[dhan:${this.mode}] protective SL status UNKNOWN after retry for ${symbol} (signal #${signalId}) slOrderId=${retryId} — verify manually.`,
        );
        return;
      }

      // Both attempts rejected — position is genuinely unprotected at the broker.
      await setSl(undefined);
      await this.alertUnprotected(symbol, qty, signalId, 'stop-loss REJECTED twice (original + wider-buffer retry)');
    } catch (slErr: any) {
      // Transport/auth error placing the SL — treat as unprotected (fail-open, entry kept).
      this.logger.error(
        `[dhan:${this.mode}] PROTECTIVE STOP FAILED for ${symbol} (signal #${signalId}): ${this.errMsg(slErr)}`,
      );
      await this.alertUnprotected(symbol, qty, signalId, this.errMsg(slErr));
    }
  }

  /** Fire the "position unprotected" Telegram alert (best-effort). */
  private async alertUnprotected(symbol: string, qty: number, signalId: number, reason: string): Promise<void> {
    await this.telegram
      .sendAlert(
        'DHAN: POSITION UNPROTECTED',
        `Entry filled but the broker stop-loss could not be placed for <b>${symbol}</b> ×${qty} (signal #${signalId}). ` +
          `No resting SL at the broker — protected only by the soft engine stop and the 15:12 EOD square-off. ` +
          `Reason: ${reason}`,
      )
      .catch(() => undefined);
  }

  /**
   * Log + book realized P&L for a completed exit (our market exit or a fired SL). Trips the
   * kill-switch on loss. Returns the realized P&L (rupees) when both fills are known, else undefined.
   */
  private reconcileExit(pos: OpenPosition, exitFill: number | undefined, tag: string, source: string): number | undefined {
    if (pos.fillPrice !== undefined && exitFill !== undefined) {
      const perShare = pos.side === 'BUY' ? exitFill - pos.fillPrice : pos.fillPrice - exitFill;
      const realPnl = perShare * pos.qty;
      if (realPnl < 0) {
        this.realizedLossToday += -realPnl;
        void this.persistDailyState();
      }
      this.logger.log(
        `[dhan:${this.mode}] EXIT → ${tag} | ${source} fill=₹${exitFill} realP&L=₹${realPnl.toFixed(2)}`,
      );
      this.checkKillSwitch();
      return realPnl;
    }
    this.logger.log(`[dhan:${this.mode}] EXIT → ${tag} | ${source} fill=₹${exitFill ?? '?'}`);
    return undefined;
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
    // In-memory reset only (no DB write) — the persisted row is authoritative and is
    // re-read on boot, so writing here would risk zeroing today's row during startup.
    const key = new Date().toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' });
    if (key !== this.dayKey) {
      this.dayKey = key;
      this.ordersToday = 0;
      this.realizedLossToday = 0;
      this.killedToday = false;
    }
  }

  private checkKillSwitch(): void {
    if (this.realizedLossToday >= this.maxDailyLoss && this.mode === 'live') {
      this.logger.error(
        `[dhan] KILL-SWITCH: daily loss ₹${this.realizedLossToday.toFixed(0)} ≥ ₹${this.maxDailyLoss}. Reverting mode → off.`,
      );
      this.mode = 'off';
      this.killedToday = true;
      void this.persistDailyState(); // durable — a restart must NOT re-enable live today
      void this.telegram
        .sendReversalAlert({
          symbol: 'DHAN',
          exitPrice: 0,
          reason: `KILL-SWITCH tripped — daily loss ₹${this.realizedLossToday.toFixed(0)}. Live trading disabled.`,
        })
        .catch(() => undefined);
    }
  }

  // ── durable state (DB mirror) ────────────────────────────────────────────────
  // All best-effort: a DB failure logs but never throws — the real order already
  // happened, so losing the mirror must not break live execution.

  /** Upsert the DhanPosition row from the current in-memory position (by signalId). */
  private async persistPosition(signalId: number): Promise<void> {
    const pos = this.openPositions.get(signalId);
    if (!pos) return;
    const data = {
      symbol: pos.symbol,
      side: pos.side,
      qty: pos.qty,
      simEntryPrice: pos.simEntryPrice,
      orderId: pos.orderId ?? null,
      fillPrice: pos.fillPrice ?? null,
      stopPrice: pos.stopPrice ?? null,
      slOrderId: pos.slOrderId ?? null,
      status: 'OPEN',
    };
    try {
      await this.prisma.dhanPosition.upsert({
        where: { signalId },
        create: { signalId, ...data },
        update: data,
      });
    } catch (err: any) {
      this.logger.error(`[dhan] persistPosition #${signalId} failed: ${this.errMsg(err)}`);
    }
  }

  /** Mark a DhanPosition CLOSED with the reconciled exit details (kept for audit). */
  private async closePosition(
    signalId: number,
    exit: { exitOrderId?: string; exitFillPrice?: number; realizedPnl?: number; closeReason: string },
  ): Promise<void> {
    try {
      await this.prisma.dhanPosition.updateMany({
        where: { signalId, status: 'OPEN' },
        data: {
          status: 'CLOSED',
          exitOrderId: exit.exitOrderId ?? null,
          exitFillPrice: exit.exitFillPrice ?? null,
          realizedPnl: exit.realizedPnl ?? null,
          closeReason: exit.closeReason,
        },
      });
    } catch (err: any) {
      this.logger.error(`[dhan] closePosition #${signalId} failed: ${this.errMsg(err)}`);
    }
  }

  /** Upsert today's guardrail counters + kill-switch flag (by dayKey). */
  private async persistDailyState(): Promise<void> {
    if (!this.dayKey) return;
    const data = {
      realizedLossToday: this.realizedLossToday,
      ordersToday: this.ordersToday,
      killed: this.killedToday,
    };
    try {
      await this.prisma.dhanDailyState.upsert({
        where: { dayKey: this.dayKey },
        create: { dayKey: this.dayKey, ...data },
        update: data,
      });
    } catch (err: any) {
      this.logger.error(`[dhan] persistDailyState failed: ${this.errMsg(err)}`);
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
    bufferPct?: number; // override the limit-offset (used to widen on a retry after rejection)
  }) {
    const buf = o.bufferPct ?? this.slLimitBufferPct;
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

  /**
   * Poll an order until it fills, returning the average traded price. A MARKET fill can lag
   * its placement response, so a single read may miss it. Best-effort: undefined if not TRADED
   * within the budget (the order still went through; we just couldn't capture the exact fill).
   */
  private async pollFill(orderId: string, tries = 5, delayMs = 400): Promise<number | undefined> {
    for (let i = 0; i < tries; i++) {
      try {
        const s = await this.getOrderStatus(orderId);
        if (s.orderStatus === 'TRADED') return s.averageTradedPrice;
        if (s.orderStatus === 'REJECTED' || s.orderStatus === 'CANCELLED') return undefined;
      } catch (err: any) {
        this.logger.warn(`[dhan] fill poll for order ${orderId} errored: ${this.errMsg(err)}`);
      }
      if (i < tries - 1) await this.sleep(delayMs);
    }
    return undefined;
  }

  /**
   * Read Dhan's current positions (for boot reconciliation + EOD square-off).
   * Returns `null` on any error (could NOT reach the broker) — this is deliberately distinct
   * from `[]` (broker reached, genuinely flat), so callers never treat a read failure as "flat"
   * and orphan a still-open position.
   */
  private async getPositions(): Promise<Array<{ tradingSymbol: string; netQty: number; productType?: string }> | null> {
    try {
      const data = await this.authed((token) =>
        this.http
          .get(`${this.baseUrl}/positions`, { headers: { 'access-token': token }, timeout: 10000 })
          .then((r) => r.data),
      );
      const rows = Array.isArray(data) ? data : [];
      return rows.map((p: any) => ({
        tradingSymbol: p.tradingSymbol,
        netQty: Number(p.netQty ?? 0),
        productType: p.productType,
      }));
    } catch (err: any) {
      this.logger.error(`[dhan] getPositions failed: ${this.errMsg(err)}`);
      return null;
    }
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Poll a just-placed order until we know whether the broker ACCEPTED it. A protective
   * STOP_LOSS rests as PENDING/TRANSIT (not TRADED) — those, and TRADED, count as accepted.
   * REJECTED/CANCELLED = not accepted. Dhan can flip an order to REJECTED asynchronously
   * (e.g. off-tick / LPP-band) after returning an orderId, so a single read isn't enough.
   * Returns true if accepted, false if rejected/cancelled, undefined if still unknown.
   */
  private async pollAccepted(orderId: string, tries = 4, delayMs = 500): Promise<boolean | undefined> {
    for (let i = 0; i < tries; i++) {
      try {
        const s = await this.getOrderStatus(orderId);
        if (s.orderStatus === 'REJECTED' || s.orderStatus === 'CANCELLED') return false;
        if (s.orderStatus === 'PENDING' || s.orderStatus === 'TRANSIT' || s.orderStatus === 'TRADED') {
          return true;
        }
      } catch (err: any) {
        this.logger.warn(`[dhan] accept poll for order ${orderId} errored: ${this.errMsg(err)}`);
      }
      if (i < tries - 1) await this.sleep(delayMs);
    }
    return undefined;
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

  /**
   * Round to the NSE ₹0.05 tick — Dhan rejects off-tick trigger prices. The `.toFixed(2)`
   * collapses binary-float artifacts (e.g. 3152.7000000000003 → 3152.70) so both the stored
   * value and the wire value are a clean 2-decimal tick.
   */
  private roundTick(price: number): number {
    return Number((Math.round(price / 0.05) * 0.05).toFixed(2));
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
