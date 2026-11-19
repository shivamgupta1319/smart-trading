# What real-money trading can and cannot do

Written 2026-11-19. Real-money trading is switched off. This page is the honest list of what
the Dhan layer does, so nobody assumes more than is there. The runbook is
[real-money-trading.md](real-money-trading.md).

**Do not treat it as a proven autonomous system.** It ran for a few days in July 2026 on
about ₹10,000 with two cells, before the merge. It has not placed a real order since it was
brought into this product; its behaviour here is covered by tests with the broker faked.

## It does

- Place an intraday market entry for a cell that is PROVEN and switched on by the owner.
- Size the order itself: the smallest of the risk limit, the position-value limit and the
  share limit.
- Leave a stop order resting at the broker at the planned stop, confirm the broker accepted
  it, retry once if rejected, and alert if the position ends up unprotected.
- Exit at market when the paper trade closes, without selling twice if the stop already fired.
- Close anything still open between 15:12 and 15:20 IST, using the broker's record.
- Survive a restart: open positions and the daily loss counter are in the database.
- Stop new entries for the day when the daily loss limit is reached.
- Keep exiting open positions when entries are switched off.
- Log in by itself (time-based code), reuse the token across restarts, respect Dhan's
  two-minute limit and alert when login fails.

## It does not

- **Trade swing signals.** Intraday only. Delivery orders are not built.
- **Take partial profits on the real position.** The paper trade books 35% at half-way and
  35% at three-quarters; the real position is held whole until the paper trade fully closes.
  So a real trade's result differs from its paper twin.
- **Trail the broker stop.** The resting stop stays at the original level. The paper stop
  moves to break-even and trails; the real position only benefits when the paper trade then
  closes and the app sends the market exit.
- **React between scans.** Exits are decided when the scanner checks prices, roughly every
  two to three minutes. Between checks only the resting stop protects the position.
- **Trade futures or options.**
- **Know about your manual trades.** If you trade the same stock by hand in the same
  account, the end-of-day close works from the net position and may close yours too.

## Known differences between paper and real

| | Paper | Real |
|---|---|---|
| Quantity | Sized from the cell's fund as it grows or shrinks | Sized from fixed limits |
| Entry price | Live quote when the signal is found | Market fill, a moment later |
| Partial exits | Yes | No |
| Stop | Trails | Fixed at the original level until the app exits |
| Costs | Estimated | Actual |

These differences are why a cell needs a long, clean paper record before real money, and why
real results should be compared with paper results from the first day.
