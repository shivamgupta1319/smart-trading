import { Injectable, Logger } from "@nestjs/common";
import axios from "axios";
import { PrismaService } from "../prisma/prisma.service";
import { CreateSignalDto } from "./dto/create-signal.dto";
import { MAX_RISK_PER_TRADE } from "../common/risk";
import { toNum, round2, safePct, normalizeTradeMoney } from "../common/money";

@Injectable()
export class SignalsService {
  private readonly logger = new Logger(SignalsService.name);
  private readonly engineUrl = process.env.ENGINE_URL || "http://localhost:8000";

  constructor(private prisma: PrismaService) {}

  async findAll() {
    return this.prisma.liveSignal.findMany({
      include: { stock: true },
      orderBy: { timestamp: "desc" },
    });
  }

  async findActive() {
    return this.prisma.liveSignal.findMany({
      where: { status: "ACTIVE" },
      include: { stock: true, trade: true },
      orderBy: { timestamp: "desc" },
    });
  }

  /** Best-effort current market price from the engine; null if unavailable. */
  private async fetchLivePrice(symbol?: string): Promise<number | null> {
    if (!symbol) return null;
    try {
      const res = await axios.post(
        `${this.engineUrl}/api/engine/live-prices`,
        { symbols: [symbol] },
        {
          timeout: 8000,
          headers: process.env.API_KEY ? { "x-api-key": process.env.API_KEY } : {},
        },
      );
      const entry = res.data?.[symbol];
      const price = typeof entry === "object" ? entry?.price : entry;
      return typeof price === "number" && Number.isFinite(price) ? price : null;
    } catch {
      return null;
    }
  }

  async create(dto: CreateSignalDto) {
    // Fast-path idempotency check (the DB partial-unique index is the real guard).
    const existing = await this.prisma.liveSignal.findFirst({
      where: { stockId: dto.stockId, strategyName: dto.strategyName, status: "ACTIVE" },
      include: { stock: true },
    });
    if (existing) return { signal: existing, isNew: false };

    const riskPerShare = Math.abs(dto.entryPrice - dto.stopLoss);
    const quantity = riskPerShare > 0 ? Math.max(1, Math.floor(MAX_RISK_PER_TRADE / riskPerShare)) : 1;
    const capitalUsed = round2(quantity * dto.entryPrice);
    const riskAmount = round2(quantity * riskPerShare);

    try {
      // Signal + Trade are created atomically: a failure in either rolls back both.
      const signal = await this.prisma.$transaction(async (tx) => {
        const sig = await tx.liveSignal.create({
          data: {
            stockId: dto.stockId,
            strategyName: dto.strategyName,
            signalType: dto.signalType,
            entryPrice: dto.entryPrice,
            stopLoss: dto.stopLoss,
            target: dto.target,
            holdDuration: dto.holdDuration || null,
          },
          include: { stock: true },
        });

        await tx.trade.create({
          data: {
            signalId: sig.id,
            stockId: dto.stockId,
            symbol: sig.stock?.symbol || `STOCK_${dto.stockId}`,
            strategyName: dto.strategyName,
            signalType: dto.signalType,
            holdDuration: dto.holdDuration || "UNKNOWN",
            entryPrice: dto.entryPrice,
            stopLoss: dto.stopLoss,
            target: dto.target,
            quantity,
            capitalUsed,
            riskAmount,
            entryTime: sig.timestamp,
            status: "OPEN",
            originalStopLoss: dto.stopLoss,
            trailingState: "INITIAL",
            peakPrice: dto.entryPrice,
            remainingQty: quantity,
          },
        });
        return sig;
      });

      this.logger.log(
        `Trade created: ${dto.signalType} ${signal.stock?.symbol} × ${quantity} shares (₹${capitalUsed.toFixed(0)} invested, ₹${riskAmount.toFixed(0)} at risk)`,
      );
      return { signal, isNew: true };
    } catch (err: unknown) {
      // P2002 = the partial-unique index rejected a concurrent duplicate active signal.
      if (typeof err === "object" && err && (err as { code?: string }).code === "P2002") {
        const dup = await this.prisma.liveSignal.findFirst({
          where: { stockId: dto.stockId, strategyName: dto.strategyName, status: "ACTIVE" },
          include: { stock: true },
        });
        if (dup) return { signal: dup, isNew: false };
      }
      this.logger.error(
        `Failed to create signal/trade: ${err instanceof Error ? err.message : String(err)}`,
      );
      throw err;
    }
  }

  /**
   * Close at the current market price. Previously this booked breakeven (exit =
   * entry) whenever no price was supplied — silently corrupting P&L. Now it
   * fetches the live price; only if that genuinely fails does it fall back to
   * entry, and it says so loudly + records a note.
   */
  async close(id: number) {
    const sig = await this.prisma.liveSignal.findUnique({
      where: { id },
      include: { stock: true, trade: true },
    });
    if (!sig) return null;

    const livePrice = await this.fetchLivePrice(sig.stock?.symbol);
    if (livePrice != null) {
      return this.closeWithPrice(id, livePrice);
    }

    // Fallback: cannot price the exit. Mark it, but do NOT pretend it's breakeven.
    this.logger.warn(
      `close(${id}): no live price for ${sig.stock?.symbol} — falling back to entry price; verify manually.`,
    );
    const entryFallback = toNum(sig.trade?.entryPrice ?? sig.entryPrice);
    return this.closeWithPrice(id, entryFallback, "Closed without live price (fallback to entry)");
  }

  async partialClose(id: number, percentToClose: number, exitPrice: number, reason: string) {
    const signal = await this.prisma.liveSignal.findUnique({
      where: { id },
      include: { trade: true, stock: true },
    });
    if (!signal || !signal.trade || signal.trade.status !== "OPEN") {
      this.logger.warn(`Cannot partial close signal ${id}: trade not found or already closed`);
      return null;
    }

    const trade = normalizeTradeMoney(signal.trade)!;
    // Clamp percent to (0, 1].
    const pct = Math.min(1, Math.max(0, percentToClose));
    const sharesToClose = Math.max(1, Math.floor(trade.quantity * pct));
    const actualSharesToClose = Math.min(sharesToClose, trade.remainingQty);
    if (actualSharesToClose <= 0) return null;

    if (actualSharesToClose === trade.remainingQty) {
      // Full close of the remaining lot.
      await this.prisma.trade.update({
        where: { id: trade.id },
        data: {
          notes: trade.notes
            ? `${trade.notes} | ${reason}: Closing final ${actualSharesToClose} @ ₹${exitPrice}`
            : `${reason}: Closing final ${actualSharesToClose} @ ₹${exitPrice}`,
        },
      });
      await this.closeWithPrice(id, exitPrice);
      this.logger.log(
        `Partial Close → FULL close: ${trade.signalType} ${signal.stock?.symbol} — final ${actualSharesToClose} @ ₹${exitPrice}.`,
      );
      return signal;
    }

    const isBuy = trade.signalType === "BUY";
    const pnlPerShare = isBuy ? exitPrice - trade.entryPrice : trade.entryPrice - exitPrice;
    const lotPnl = pnlPerShare * actualSharesToClose;
    const newRemainingQty = trade.remainingQty - actualSharesToClose;
    const newRealizedPnl = round2(trade.realizedPnl + lotPnl);

    await this.prisma.trade.update({
      where: { id: trade.id },
      data: {
        remainingQty: newRemainingQty,
        realizedPnl: newRealizedPnl,
        notes: trade.notes
          ? `${trade.notes} | ${reason}: Closed ${actualSharesToClose} @ ₹${exitPrice} (P&L: ₹${lotPnl.toFixed(2)})`
          : `${reason}: Closed ${actualSharesToClose} @ ₹${exitPrice} (P&L: ₹${lotPnl.toFixed(2)})`,
      },
    });

    this.logger.log(
      `Partial Close: ${trade.signalType} ${signal.stock?.symbol} — ${actualSharesToClose} @ ₹${exitPrice}. Lot P&L: ₹${lotPnl.toFixed(2)}. Remaining: ${newRemainingQty}`,
    );
    return { id, actualSharesToClose, lotPnl: round2(lotPnl), newRemainingQty, newRealizedPnl };
  }

  async closeWithPrice(id: number, exitPrice: number, extraNote?: string) {
    return this.prisma.$transaction(async (tx) => {
      const signal = await tx.liveSignal.update({
        where: { id },
        data: { status: "CLOSED" },
        include: { stock: true, trade: true },
      });

      if (signal.trade && signal.trade.status === "OPEN") {
        const trade = normalizeTradeMoney(signal.trade)!;
        const isBuy = trade.signalType === "BUY";
        const pnlPerShare = isBuy ? exitPrice - trade.entryPrice : trade.entryPrice - exitPrice;
        const finalLotPnl = pnlPerShare * trade.remainingQty;
        const totalPnl = trade.realizedPnl + finalLotPnl;
        // Consistent semantics everywhere: P&L as a % of capital deployed.
        const pnlPercent = safePct(totalPnl, trade.capitalUsed);

        const outcome = totalPnl > 0 ? "WIN" : totalPnl < 0 ? "LOSS" : "BREAKEVEN";

        await tx.trade.update({
          where: { id: trade.id },
          data: {
            exitPrice,
            pnl: round2(totalPnl),
            pnlPercent: round2(pnlPercent),
            remainingQty: 0,
            outcome,
            exitTime: new Date(),
            status: "CLOSED",
            notes: extraNote
              ? trade.notes
                ? `${trade.notes} | ${extraNote}`
                : extraNote
              : trade.notes,
          },
        });
      }

      return tx.liveSignal.findUnique({
        where: { id },
        include: { stock: true, trade: true },
      });
    });
  }

  async updateStopLoss(id: number, newStopLoss: number, trailingState: string, peakPrice?: number) {
    const signal = await this.prisma.liveSignal.findUnique({
      where: { id },
      include: { trade: true },
    });
    if (!signal || signal.status !== "ACTIVE") {
      this.logger.warn(`Cannot update SL for signal ${id}: not active`);
      return null;
    }

    await this.prisma.$transaction(async (tx) => {
      await tx.liveSignal.update({ where: { id }, data: { stopLoss: newStopLoss } });
      if (signal.trade && signal.trade.status === "OPEN") {
        const updateData: Record<string, unknown> = { stopLoss: newStopLoss, trailingState };
        if (peakPrice !== undefined) updateData.peakPrice = peakPrice;
        await tx.trade.update({ where: { id: signal.trade.id }, data: updateData });
      }
    });

    this.logger.log(
      `Trailing SL updated: Signal #${id} → SL ₹${newStopLoss.toFixed(2)} (${trailingState})`,
    );
    return { id, newStopLoss, trailingState, peakPrice };
  }
}
