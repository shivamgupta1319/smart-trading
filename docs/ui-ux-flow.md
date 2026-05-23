# UI/UX Flow: Zero-Cost Algorithmic Trading Scanner

## Design Language

**Theme:** Dark trading terminal — inspired by Bloomberg Terminal and TradingView
- Background: `#0a0e1a` (deep navy black)
- Surface: `#111827` (dark card)
- Primary: `#22d3ee` (cyan — buy/long signals)
- Danger: `#f87171` (red — sell/short signals)
- Muted text: `#6b7280`
- Font: `JetBrains Mono` (monospace) for prices, `Inter` for UI labels

---

## Navigation

```
┌─────────────────────────────────────────────────────────┐
│  ⚡ SmartTrader        [Backtest Arena]  [Live Scanner]  │
└─────────────────────────────────────────────────────────┘
```

- Sticky top navbar with logo and two main nav links
- Active page highlighted with cyan underline
- Market status indicator (OPEN / CLOSED) with pulsing dot

---

## Screen 1: Backtest Arena

### Purpose
Allow the user to select any NSE stock and strategy, run a backtest, see results, and assign the winning strategy.

### Layout
```
┌─────────────────────────────────────────────────────────┐
│  BACKTEST ARENA                                         │
│                                                         │
│  Stock:    [RELIANCE.NS ▾]   → Fetch History [button]   │
│  Strategy: [15m ORB ▾     ]                             │
│  Timeframe: auto (from strategy)                        │
│                                         [Run Backtest]  │
│─────────────────────────────────────────────────────────│
│  Results:                                               │
│  ┌──────────┬────────────┬───────────┬────────────────┐ │
│  │ Strategy │  Win Rate  │  Trades   │  Expectancy    │ │
│  ├──────────┼────────────┼───────────┼────────────────┤ │
│  │ 15m ORB  │   54.2%    │    87     │    ₹1,240      │ │
│  │ VWAP ST  │   61.0%    │    142    │    ₹2,100  ★   │ │
│  └──────────┴────────────┴───────────┴────────────────┘ │
│                                                         │
│  [Set as Live Strategy] [Live (Click to Remove)]        │
└─────────────────────────────────────────────────────────┘
```

### User Flow
1. User selects a stock from the dropdown (pre-populated from DB, or type to search)
2. Clicks **Fetch History** → backend downloads 5y/60d data via yfinance and stores it
3. Selects a strategy from the dropdown (28 options grouped: Intraday / Swing)
4. Clicks **Run Backtest**
5. Loading spinner shows during computation (~5–15 seconds)
6. Results table populates with metrics, best strategy is starred (★)
7. User clicks **Set as Live Strategy** (can select multiple) → writes to `ActiveConfiguration` table
8. Toast confirms: *"✓ VWAP+Supertrend is now set for Live Signals!"*

### States
- **Empty**: Prompt to select a stock and strategy
- **Fetching History**: Progress indicator with message
- **Running Backtest**: Spinner overlay on results area
- **Results Loaded**: Sortable results table + Set Active button
- **Error**: Red banner with error message

---

## Screen 2: Live Scanner (Alert Feed)

### Purpose
Real-time dashboard showing live trade alerts pushed via WebSocket.

### Layout
```
┌─────────────────────────────────────────────────────────┐
│  LIVE SCANNER                    🟢 MARKET OPEN 09:15   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Active Configurations (3 stocks monitored)     │    │
│  │  RELIANCE.NS → VWAP+Supertrend (15m)            │    │
│  │  TCS.NS      → 9/15 EMA+RSI (5m)               │    │
│  │  HDFC.NS     → 44 SMA Pullback (1D)             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  ACTIVE SIGNALS                                 │    │
│  │                                                 │    │
│  │  🟢 BUY  RELIANCE.NS  ₹2,847.50  [VWAP+ST 15m] │    │
│  │     SL: ₹2,821.30  Target: ₹2,899.70  14:23    │    │
│  │                                                 │    │
│  │  🔴 SELL TCS.NS      ₹3,412.00  [EMA+RSI 5m]   │    │
│  │     SL: ₹3,438.00  Target: ₹3,360.00  11:45    │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Alert Toast (appears top-right on new signal)
```
┌──────────────────────────────────┐
│  🔔 NEW TRADE ALERT              │
│  ────────────────────────────    │
│  🟢 BUY  RELIANCE.NS             │
│  Entry:  ₹2,847.50              │
│  SL:     ₹2,821.30              │
│  Target: ₹2,899.70              │
│  Strategy: VWAP+Supertrend      │
└──────────────────────────────────┘
```
- Slides in from top-right with animation
- Plays audio chime (HTML5 Audio API — short "ding" sound)
- Auto-dismisses after 8 seconds
- Multiple toasts stack vertically

### User Flow
1. User navigates to Live Scanner
2. Page connects to NestJS Socket.io on mount
3. Connection status indicator shows (🟢 Connected / 🔴 Disconnected)
4. Active configurations table shows which stocks are being monitored
5. On `NEW_TRADE_ALERT` event:
   - Toast slides in from top-right
   - Audio chime plays
   - Signal row added to Active Signals table (newest on top)
6. User can click a signal row to expand details (mark as closed/expired)
7. Market status banner updates (OPEN/CLOSED based on IST time)

### States
- **Connected + Market Open**: Normal operation
- **Connected + Market Closed**: Shows "Scanner paused until 09:15 IST"
- **Disconnected**: Yellow warning banner "Reconnecting to server..."
- **No active configs**: Prompt to go to Backtest Arena and set one

---

## Micro-Animations

| Element | Animation |
|---|---|
| Toast notification | Slide in from right (300ms ease-out) |
| Signal row | Fade in + yellow flash highlight |
| Market status dot | Slow pulse (2s ease-in-out infinite) |
| Backtest running | Spinning cyan circle on button |
| Set Active button | Scale up on hover + green glow |
| Navbar active link | Cyan underline slide from left |
| Price values | Monospace font, cyan color for BUY, red for SELL |

---

## Responsive Considerations

- All tables scroll horizontally on smaller screens
- Toast notifications reduce to 90% width on mobile
- Navbar collapses to hamburger below 768px (future enhancement)
