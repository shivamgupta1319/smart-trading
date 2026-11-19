import axios from 'axios';
import { API } from '../config';

type LivePrice = number | { price?: number } | null | undefined;

/** The exit price to book: the live quote, or one the owner types when there is none. */
async function exitPriceFor(symbol: string): Promise<number | null> {
  try {
    const res = await axios.post<Record<string, LivePrice>>(`${API}/api/engine/live-prices`, {
      symbols: [symbol],
    });
    const raw = res.data?.[symbol];
    const price = typeof raw === 'object' && raw !== null ? raw.price : raw;
    if (typeof price === 'number' && Number.isFinite(price) && price > 0) return price;
  } catch {
    // No live quote: fall through and ask.
  }
  const typed = window.prompt(
    `There is no live price for ${symbol} right now.\nEnter the price you exited at (₹) to close this trade:`,
  );
  if (typed === null) return null; // cancelled
  const price = Number(typed.replace(/[₹,\s]/g, ''));
  if (!Number.isFinite(price) || price <= 0) {
    window.alert('That is not a valid price. The trade was not closed.');
    return null;
  }
  return price;
}

/**
 * Close a trade by hand at a real price. A trade is never closed without a price:
 * that used to book the entry price and record an open position as ₹0.
 * Returns true when the trade was closed.
 */
export async function closeTradeAtRealPrice(signalId: number, symbol: string): Promise<boolean> {
  const exitPrice = await exitPriceFor(symbol);
  if (exitPrice === null) return false;
  try {
    await axios.patch(`${API}/api/signals/${signalId}/close`, { exitPrice });
    return true;
  } catch (err) {
    const message = axios.isAxiosError(err)
      ? (err.response?.data as { message?: string } | undefined)?.message
      : undefined;
    window.alert(`${symbol} was not closed. ${message ?? 'The server did not accept the request. Try again.'}`);
    return false;
  }
}
