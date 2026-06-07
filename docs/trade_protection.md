## Trade protection framework

**Stocks / Equity · 1:2 RR · ₹1L capital · 2% risk per trade**

---

## 3-phase exit strategy — never let a winner become a full loser

### Phase 1 · Entry zone (0–49%)

- Hold position.
- Keep original SL.
- No action yet — let the trade breathe.

> Original SL active

---

### Phase 2 · Protection zone ⚡ (50–74%)

- **Move SL to breakeven immediately.**
- You now have a free trade — worst case is 0.
- Exit 30–40% of position here (partial book).

> SL → Breakeven

---

### Phase 3 · Harvest zone (75–99%)

- Trail SL aggressively (below last swing low / 5-min candle low).
- Book another 30–40%.
- Let the final lot ride.

> Trailing SL active

---

# Rules hardwired into your system

## Rule 1 — 50% progress → SL to breakeven + Partial Exit

The moment price crosses the 50% point (Phase 2), the system auto-triggers a SL move to the entry price. 
- **Partial Exit**: It automatically books 35% of the position.
- **Quantity Check**: Partial exits are skipped if the original quantity is less than 3 shares.

---

## Rule 2 — 75% progress → Aggressive Trailing + Partial Exit

When price reaches 75% of the target (Phase 3):
- **Trailing SL**: The SL is moved to the lowest low (for BUY) or highest high (for SELL) of the last 3 candles.
- **Partial Exit**: It automatically books another 40% of the position.
- **Quantity Check**: Skipped if original quantity is less than 3 shares.

---

## Rule 3 — 80% progress → Reversal Detection (Layer 3)

If the trade reaches 80% progress, the system actively monitors for reversal patterns to prevent giving back profits. It forces a **Full Close** if it detects:
1. **Engulfing Patterns** against the trade direction.
2. **Pin Bars** (long wicks indicating rejection).
3. **RSI Divergence** (price makes a new high/low, but RSI fails to follow).
4. **Volume Exhaustion** (price spikes on low volume near the target).

---

## Rule 4 — Market Time Gates

To avoid fake moves and after-hours slippage, the scanner enforces strict time boundaries:
- **Morning Block**: No setups are evaluated before **9:30 AM IST**.
- **Afternoon Intraday Block**: No new INTRADAY setups are generated after **3:00 PM IST**.
- **Global Block & Square-Off**: No signals are processed after **3:15 PM IST**. Any open INTRADAY positions are forcefully closed at market price at 3:15 PM.

---

## Rule 5 — Zombie Trade Prevention

When partial exits occur, the system safely tracks `remainingQty` and `realizedPnl`. If a partial exit consumes the final remaining shares of a trade, it automatically delegates to a **Full Trade Close**. This ensures P&L math is exact and trades don't remain stuck in an "OPEN" state with 0 shares.

---

# Why price reverses near your target — common causes

## Cause 1 — Your target sits at a key resistance

If your fixed target is exactly at a round number (₹500, ₹1000), prior high, or daily R1/R2 — large sellers exist there.

Check if your target aligns with these levels before entering.

---

## Cause 2 — Institutional profit booking before target

Big money often unloads into retail momentum.

When you see strong candles close to target followed by sudden reversal on high volume — that's distribution, not weakness.

Exit into strength.

---

## Cause 3 — Target too far for current volatility

In intraday, if your SL is ₹20 your target is ₹40.

But if ATR for that stock is ₹15/day, a ₹40 move rarely happens in one session.

Consider dynamic targets based on ATR × 1.5.

---

## Cause 4 — News / broad market reversal

Nifty/Sensex reversals drag individual stocks.

Track the index direction — if market starts reversing near your target time, partial exit regardless of your specific setup.

---

# Upgraded structure vs your current structure

## Before (current)

- Entry → wait → SL or full target
- All-or-nothing outcome
- No partial booking
- No SL trail
- Win full or lose full

---

## After (3-phase)

- Entry → 50% → Breakeven SL + book 35% (if qty >= 3)
- → 75% → Trail SL + book 40% (if qty >= 3)
- → 80%+ → Reversal Detection (Full Exit if detected)
- → 100% → Exit final 25%
- Even on reversal from 75%: profitable
- Loss only possible in phase 1

---

> ⚠ Backtest these partial-exit rules on your historical data before going live. (apps/engine/scanner/simulate_trailing.py)

Perfect. Now I have a clear picture. Let me build you a complete **position management framework** like a pro trader.Now let me build you a comprehensive visual framework.Here's the core thinking behind all of this:

**Your root problem** isn't the strategy — it's the exit structure. A single fixed target with a single SL means you're running a binary trade: full win or full loss. That's fine when the setup is perfect, but markets punish it near resistance zones.

**The fix is simple in principle:** you need to convert your trade from binary to asymmetric. Once you're at 50% progress, price has already proven your direction right. At that point, moving SL to breakeven costs you nothing and eliminates all downside. There is no rational reason not to do this — it's a free insurance policy.

**On the partial booking** — this is the psychological key. Once you've booked 35% at the 50% mark, your brain changes. You've already "won" something real. The anxiety that causes premature exits near the target disappears because you're not fighting to protect zero anymore.

**On the backtesting flag** — since you have a system, this is your biggest edge. Filter your last 4 days of data for trades that reversed from 50%+ progress and look at two things: was there a known resistance level within 5–10% of your target, and what did volume do 1–2 candles before the reversal? That pattern, once identified, becomes a dynamic exit trigger in your system.
