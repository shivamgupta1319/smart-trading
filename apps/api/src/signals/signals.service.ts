import { Injectable, Logger } from "@nestjs/common";
import { PrismaService } from "../prisma/prisma.service";
import { CreateSignalDto } from "./dto/create-signal.dto";
import { DhanService } from "../dhan/dhan.service";

// Professional risk management constants
const INITIAL_CAPITAL = 100000; // ₹1,00,000
const RISK_PER_TRADE_PCT = 2; // 2% risk per trade (standard for professional traders)
const MAX_RISK_PER_TRADE = INITIAL_CAPITAL * (RISK_PER_TRADE_PCT / 100); // ₹2,000
// Per-trade notional cap depends on horizon: intraday runs on MIS ~5x leverage (₹5L on the ₹1L
// base), swing/positional is delivery (CNC) at 1x (₹1L). The 2% (₹2,000) risk cap still applies to
// both — quantity is the SMALLER of the risk-based and notional-based sizes.
const INTRADAY_NOTIONAL = INITIAL_CAPITAL * 5; // ₹5,00,000 (5x MIS intraday)
const SWING_NOTIONAL = INITIAL_CAPITAL; // ₹1,00,000 (1x delivery)
/** ₹5L for explicit INTRADAY; ₹1L for swing/positional and any unknown horizon (conservative). */
function notionalCapFor(holdDuration?: string | null): number {
  return holdDuration === "INTRADAY" ? INTRADAY_NOTIONAL : SWING_NOTIONAL;
}

@Injectable()
export class SignalsService {
  private readonly logger = new Logger(SignalsService.name);

  constructor(
    private prisma: PrismaService,
    private dhan: DhanService,
  ) {}

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

  async create(dto: CreateSignalDto) {
    // Avoid duplicate active signals for same stock+strategy
    const existing = await this.prisma.liveSignal.findFirst({
      where: {
        stockId: dto.stockId,
        strategyName: dto.strategyName,
        status: "ACTIVE",
      },
      include: { stock: true },
    });
    if (existing) return { signal: existing, isNew: false }; // idempotent

    const signal = await this.prisma.liveSignal.create({
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

    // Auto-create Trade record with professional position sizing
    try {
      const riskPerShare = Math.abs(dto.entryPrice - dto.stopLoss);
      // Position size is the SMALLER of two caps so both invariants always hold:
      //   • Risk-based cap: never risk more than 2% (₹2,000) of capital on a single trade.
      //   • Notional cap: never deploy more than the per-horizon notional (₹5L intraday / ₹1L swing).
      // Without the notional cap, a tight stop on a high-priced stock (e.g. HDFCBANK ~₹817,
      // stop ~₹1 away) would size ~1904 shares = ₹15.5L notional — a ~15x over-leverage.
      const notionalCap = notionalCapFor(dto.holdDuration);
      const riskBasedQty =
        riskPerShare > 0
          ? Math.floor(MAX_RISK_PER_TRADE / riskPerShare)
          : Number.MAX_SAFE_INTEGER;
      const notionalCapQty =
        dto.entryPrice > 0 ? Math.floor(notionalCap / dto.entryPrice) : 1;
      const quantity = Math.max(1, Math.min(riskBasedQty, notionalCapQty));
      const capitalUsed = quantity * dto.entryPrice;
      const riskAmount = quantity * riskPerShare;

      await this.prisma.trade.create({
        data: {
          signalId: signal.id,
          stockId: dto.stockId,
          symbol: signal.stock?.symbol || `STOCK_${dto.stockId}`,
          strategyName: dto.strategyName,
          signalType: dto.signalType,
          holdDuration: dto.holdDuration || "UNKNOWN",
          entryPrice: dto.entryPrice,
          stopLoss: dto.stopLoss,
          target: dto.target,
          quantity,
          capitalUsed,
          riskAmount,
          entryTime: signal.timestamp,
          status: "OPEN",
          originalStopLoss: dto.stopLoss,
          trailingState: "INITIAL",
          peakPrice: dto.entryPrice,
          remainingQty: quantity,
        },
      });
      this.logger.log(
        `Trade created: ${dto.signalType} ${signal.stock?.symbol} × ${quantity} shares (₹${capitalUsed.toFixed(0)} invested, ₹${riskAmount.toFixed(0)} at risk)`,
      );

      // Real-money execution adapter (no-op unless DHAN_TRADING_MODE set + whitelisted).
      // Quantity is computed independently inside DhanService — decoupled from the sim quantity above.
      await this.dhan.placeEntry({
        signalId: signal.id,
        symbol: signal.stock?.symbol,
        signalType: dto.signalType,
        strategyName: dto.strategyName,
        entryPrice: dto.entryPrice,
        stopLoss: dto.stopLoss,
        holdDuration: dto.holdDuration,
      });
    } catch (err: unknown) {
      if (err instanceof Error) {
        this.logger.error(
          `Failed to create trade for signal ${signal.id}: ${err.message}`,
        );
      } else {
        this.logger.error(
          `Failed to create trade for signal ${signal.id}: ${String(err)}`,
        );
      }
    }

    return { signal, isNew: true };
  }

  // NOTE: the old no-price `close(id)` was removed. It booked exit = entry (a fake ₹0 breakeven)
  // whenever a caller omitted the price, corrupting P&L. All closes now go through
  // `closeWithPrice(id, exitPrice)`; the controller rejects a priceless close with 400.

  async partialClose(id: number, percentToClose: number, exitPrice: number, reason: string) {
    const signal = await this.prisma.liveSignal.findUnique({
      where: { id },
      include: { trade: true, stock: true },
    });

    if (!signal || !signal.trade || signal.trade.status !== "OPEN") {
      this.logger.warn(`Cannot partial close signal ${id}: trade not found or already closed`);
      return null;
    }

    const trade = signal.trade;
    // Calculate how many shares to close based on the ORIGINAL quantity
    const sharesToClose = Math.max(1, Math.floor(trade.quantity * percentToClose));
    
    // Safety check: ensure we don't close more than remaining
    const actualSharesToClose = Math.min(sharesToClose, trade.remainingQty);
    
    if (actualSharesToClose <= 0) {
      return null;
    }

    if (actualSharesToClose === trade.remainingQty) {
      // It's a full close of the remaining shares!
      // Add the reason to notes first
      await this.prisma.trade.update({
        where: { id: trade.id },
        data: {
          notes: trade.notes 
            ? `${trade.notes} | ${reason}: Closing final ${actualSharesToClose} @ ₹${exitPrice}`
            : `${reason}: Closing final ${actualSharesToClose} @ ₹${exitPrice}`
        }
      });
      
      // Then fully close
      await this.closeWithPrice(id, exitPrice);
      this.logger.log(
        `Partial Close triggered FULL close: ${trade.signalType} ${signal.stock?.symbol} - Closed final ${actualSharesToClose} shares @ ₹${exitPrice}.`
      );
      return signal;
    }

    const isBuy = trade.signalType === "BUY";
    const pnlPerShare = isBuy
      ? exitPrice - trade.entryPrice
      : trade.entryPrice - exitPrice;
    
    const lotPnl = pnlPerShare * actualSharesToClose;
    
    const newRemainingQty = trade.remainingQty - actualSharesToClose;
    const newRealizedPnl = trade.realizedPnl + lotPnl;
    
    await this.prisma.trade.update({
      where: { id: trade.id },
      data: {
        remainingQty: newRemainingQty,
        realizedPnl: Math.round(newRealizedPnl * 100) / 100,
        notes: trade.notes 
          ? `${trade.notes} | ${reason}: Closed ${actualSharesToClose} @ ₹${exitPrice} (P&L: ₹${lotPnl.toFixed(2)})`
          : `${reason}: Closed ${actualSharesToClose} @ ₹${exitPrice} (P&L: ₹${lotPnl.toFixed(2)})`
      }
    });

    this.logger.log(
      `Partial Close: ${trade.signalType} ${signal.stock?.symbol} - Closed ${actualSharesToClose} shares @ ₹${exitPrice}. Lot P&L: ₹${lotPnl.toFixed(2)}. Remaining: ${newRemainingQty}`
    );

    return { id, actualSharesToClose, lotPnl, newRemainingQty, newRealizedPnl };
  }

  async closeWithPrice(id: number, exitPrice: number) {
    const signal = await this.prisma.liveSignal.update({
      where: { id },
      data: { status: "CLOSED" },
      include: { stock: true, trade: true },
    });

    if (signal.trade && signal.trade.status === "OPEN") {
      const trade = signal.trade;
      const isBuy = trade.signalType === "BUY";
      const pnlPerShare = isBuy
        ? exitPrice - trade.entryPrice
        : trade.entryPrice - exitPrice;
        
      // Final lot P&L based ONLY on remaining quantity
      const finalLotPnl = pnlPerShare * trade.remainingQty;
      
      // Total Trade P&L = Realized from partials + Final Lot P&L
      const totalPnl = trade.realizedPnl + finalLotPnl;
      const pnlPercent = (totalPnl / trade.capitalUsed) * 100;

      let outcome = "BREAKEVEN";
      if (totalPnl > 0) outcome = "WIN";
      else if (totalPnl < 0) outcome = "LOSS";

      await this.prisma.trade.update({
        where: { id: trade.id },
        data: {
          exitPrice,
          pnl: Math.round(totalPnl * 100) / 100,
          pnlPercent: Math.round(pnlPercent * 100) / 100,
          remainingQty: 0,
          outcome,
          exitTime: new Date(),
          status: "CLOSED",
        },
      });

      // Square off the real Dhan position (no-op unless this signal is Dhan-managed).
      await this.dhan.placeExit({
        signalId: id,
        symbol: signal.stock?.symbol,
        exitPrice,
      });
    }

    return this.prisma.liveSignal.findUnique({
      where: { id },
      include: { stock: true, trade: true },
    });
  }

  async updateStopLoss(
    id: number,
    newStopLoss: number,
    trailingState: string,
    peakPrice?: number,
  ) {
    const signal = await this.prisma.liveSignal.findUnique({
      where: { id },
      include: { trade: true },
    });

    if (!signal || signal.status !== 'ACTIVE') {
      this.logger.warn(`Cannot update SL for signal ${id}: not active`);
      return null;
    }

    // Update signal's stop loss
    await this.prisma.liveSignal.update({
      where: { id },
      data: { stopLoss: newStopLoss },
    });

    // Update associated trade's stop loss, trailing state, and peak price
    if (signal.trade && signal.trade.status === 'OPEN') {
      const updateData: Record<string, unknown> = {
        stopLoss: newStopLoss,
        trailingState,
      };
      if (peakPrice !== undefined) {
        updateData.peakPrice = peakPrice;
      }

      await this.prisma.trade.update({
        where: { id: signal.trade.id },
        data: updateData,
      });
    }

    this.logger.log(
      `Trailing SL updated: Signal #${id} → SL ₹${newStopLoss.toFixed(2)} (${trailingState})`,
    );

    return { id, newStopLoss, trailingState, peakPrice };
  }
}
