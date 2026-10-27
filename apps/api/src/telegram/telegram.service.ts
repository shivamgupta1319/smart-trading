import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import axios from 'axios';

const HOLD_DURATION_LABELS: Record<string, string> = {
  INTRADAY: '⏱ Intraday (exit by 15:15)',
  SHORT_SWING: '📅 Short Swing (2-5 days)',
  MID_SWING: '📆 Mid Swing (1-4 weeks)',
  LONG_POSITIONAL: '🗓 Long Positional (1-6 months)',
};

@Injectable()
export class TelegramService {
  private readonly logger = new Logger(TelegramService.name);
  private readonly botToken: string | undefined;
  private readonly chatId: string | undefined;
  private readonly enabled: boolean;

  constructor(private configService: ConfigService) {
    this.botToken = this.configService.get<string>('TELEGRAM_BOT_TOKEN');
    this.chatId = this.configService.get<string>('TELEGRAM_CHAT_ID');
    this.enabled = !!(this.botToken && this.chatId);

    if (this.enabled) {
      this.logger.log('Telegram notifications ENABLED');
    } else {
      this.logger.warn(
        'Telegram notifications DISABLED — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env',
      );
    }
  }

  async sendSignalAlert(signal: {
    signalType: string;
    symbol?: string;
    strategyName: string;
    entryPrice: number;
    stopLoss: number;
    target: number;
    holdDuration?: string;
  }) {
    if (!this.enabled) return;

    const isBuy = signal.signalType === 'BUY';
    const emoji = isBuy ? '🟢' : '🔴';
    const rr = Math.abs(
      (signal.target - signal.entryPrice) /
        (signal.entryPrice - signal.stopLoss),
    ).toFixed(1);

    const holdLabel =
      HOLD_DURATION_LABELS[signal.holdDuration || ''] ||
      signal.holdDuration ||
      'Unknown';

    const message = [
      `${emoji} <b>${signal.signalType} SIGNAL</b>`,
      ``,
      `📈 <b>Stock:</b> ${signal.symbol || 'Unknown'}`,
      `🎯 <b>Strategy:</b> ${signal.strategyName}`,
      `${holdLabel}`,
      ``,
      `💰 <b>Entry:</b> ₹${signal.entryPrice.toFixed(2)}`,
      `🛑 <b>Stop Loss:</b> ₹${signal.stopLoss.toFixed(2)}`,
      `✅ <b>Target:</b> ₹${signal.target.toFixed(2)}`,
      `📊 <b>Risk:Reward:</b> 1:${rr}`,
      ``,
      `⏰ ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`,
    ].join('\n');

    try {
      await axios.post(
        `https://api.telegram.org/bot${this.botToken}/sendMessage`,
        {
          chat_id: this.chatId,
          text: message,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        },
        { timeout: 10000, family: 4 },
      );
      this.logger.log(
        `Telegram alert sent: ${signal.signalType} ${signal.symbol}`,
      );
    } catch (err: any) {
      if (err.response && err.response.data) {
        this.logger.error(`Failed to send Telegram alert: ${JSON.stringify(err.response.data)}`);
      } else if (err instanceof Error) {
        this.logger.error(`Failed to send Telegram alert: ${err.message}`);
      } else {
        this.logger.error(`Failed to send Telegram alert: ${String(err)}`);
      }
    }
  }

  async sendTradeCloseAlert(trade: {
    symbol: string;
    signalType: string;
    strategyName: string;
    entryPrice: number;
    exitPrice: number;
    pnl: number;
    pnlPercent: number;
    outcome: string;
  }) {
    if (!this.enabled) return;

    const emoji =
      trade.outcome === 'WIN' ? '✅' : trade.outcome === 'LOSS' ? '❌' : '➖';
    const pnlEmoji = trade.pnl >= 0 ? '📈' : '📉';

    const message = [
      `${emoji} <b>TRADE CLOSED — ${trade.outcome}</b>`,
      ``,
      `📈 <b>Stock:</b> ${trade.symbol}`,
      `🎯 <b>Strategy:</b> ${trade.strategyName}`,
      ``,
      `💰 <b>Entry:</b> ₹${trade.entryPrice.toFixed(2)}`,
      `💰 <b>Exit:</b> ₹${trade.exitPrice.toFixed(2)}`,
      `${pnlEmoji} <b>P&L:</b> ₹${trade.pnl.toFixed(2)} (${trade.pnlPercent.toFixed(2)}%)`,
      ``,
      `⏰ ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`,
    ].join('\n');

    try {
      await axios.post(
        `https://api.telegram.org/bot${this.botToken}/sendMessage`,
        {
          chat_id: this.chatId,
          text: message,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        },
        { timeout: 10000, family: 4 },
      );
    } catch (err: any) {
      if (err.response && err.response.data) {
        this.logger.error(`Failed to send Telegram close alert: ${JSON.stringify(err.response.data)}`);
      } else if (err instanceof Error) {
        this.logger.error(`Failed to send Telegram close alert: ${err.message}`);
      } else {
        this.logger.error(`Failed to send Telegram close alert: ${String(err)}`);
      }
    }
  }

  async sendTrailingAlert(data: {
    symbol: string;
    event: 'BREAKEVEN' | 'PROFIT_LOCK';
    newStopLoss: number;
  }) {
    if (!this.enabled) return;

    const emoji = data.event === 'BREAKEVEN' ? '🔒' : '💰';
    const label =
      data.event === 'BREAKEVEN'
        ? 'SL moved to BREAKEVEN'
        : 'Profit LOCKED';

    const message = [
      `${emoji} <b>TRAILING SL — ${label}</b>`,
      ``,
      `📈 <b>Stock:</b> ${data.symbol}`,
      `🛑 <b>New SL:</b> ₹${data.newStopLoss.toFixed(2)}`,
      ``,
      `⏰ ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`,
    ].join('\n');

    try {
      await axios.post(
        `https://api.telegram.org/bot${this.botToken}/sendMessage`,
        {
          chat_id: this.chatId,
          text: message,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        },
        { timeout: 10000, family: 4 },
      );
      this.logger.log(`Telegram trailing alert sent: ${data.symbol} ${data.event}`);
    } catch (err: any) {
      this.logger.error(`Failed to send trailing alert: ${err?.message || err}`);
    }
  }

  async sendReversalAlert(data: {
    symbol: string;
    exitPrice: number;
    reason: string;
  }) {
    if (!this.enabled) return;

    const message = [
      `⚠️ <b>REVERSAL DETECTED — Profit Booked</b>`,
      ``,
      `📈 <b>Stock:</b> ${data.symbol}`,
      `💰 <b>Exit Price:</b> ₹${data.exitPrice.toFixed(2)}`,
      `📊 <b>Reason:</b> ${data.reason}`,
      ``,
      `⏰ ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`,
    ].join('\n');

    try {
      await axios.post(
        `https://api.telegram.org/bot${this.botToken}/sendMessage`,
        {
          chat_id: this.chatId,
          text: message,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        },
        { timeout: 10000, family: 4 },
      );
      this.logger.log(`Telegram reversal alert sent: ${data.symbol}`);
    } catch (err: any) {
      this.logger.error(`Failed to send reversal alert: ${err?.message || err}`);
    }
  }

  /** Generic operational alert (e.g. Dhan live-execution warnings). Title + free-text body. */
  async sendAlert(title: string, body: string) {
    if (!this.enabled) return;

    const message = [
      `🚨 <b>${title}</b>`,
      ``,
      body,
      ``,
      `⏰ ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`,
    ].join('\n');

    try {
      await axios.post(
        `https://api.telegram.org/bot${this.botToken}/sendMessage`,
        {
          chat_id: this.chatId,
          text: message,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        },
        { timeout: 10000, family: 4 },
      );
      this.logger.log(`Telegram alert sent: ${title}`);
    } catch (err: any) {
      this.logger.error(`Failed to send alert: ${err?.message || err}`);
    }
  }

  async sendPartialCloseAlert(data: {
    symbol: string;
    percent: number;
    exitPrice: number;
    reason: string;
    lotPnl: number;
    remainingQty: number;
  }) {
    if (!this.enabled) return;

    const emoji = data.lotPnl >= 0 ? '🤑' : '💸';
    const percentStr = Math.round(data.percent * 100);

    const message = [
      `${emoji} <b>PARTIAL CLOSE (${percentStr}%)</b>`,
      ``,
      `📈 <b>Stock:</b> ${data.symbol}`,
      `💰 <b>Exit Price:</b> ₹${data.exitPrice.toFixed(2)}`,
      `💵 <b>Lot P&L:</b> ₹${data.lotPnl.toFixed(2)}`,
      `📦 <b>Remaining Qty:</b> ${data.remainingQty}`,
      `📊 <b>Reason:</b> ${data.reason}`,
      ``,
      `⏰ ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`,
    ].join('\n');

    try {
      await axios.post(
        `https://api.telegram.org/bot${this.botToken}/sendMessage`,
        {
          chat_id: this.chatId,
          text: message,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        },
        { timeout: 10000, family: 4 },
      );
      this.logger.log(`Telegram partial close alert sent: ${data.symbol}`);
    } catch (err: any) {
      this.logger.error(`Failed to send partial close alert: ${err?.message || err}`);
    }
  }

  async sendPerformanceDigest(data: {
    period: 'DAILY' | 'WEEKLY' | 'OVERALL';
    stats: {
      totalPnl: number;
      winRate: number;
      wins: number;
      losses: number;
      profitFactor: number;
      openTrades: number;
      currentCapital: number;
      initialCapital: number;
      bestStrategy: string;
      strategyBreakdown: {
        strategy: string;
        totalPnl: number;
        winRate: number;
        trades: number;
      }[];
    };
    staleOpens: number;
    tradeCount?: number; // # closed trades in the period; 0 → no-activity message
    rangeLabel?: string; // e.g. "10 Jul 2026" or "06 Jul 2026 – 10 Jul 2026"
  }) {
    if (!this.enabled) return;

    const s = data.stats;
    const pnlEmoji = s.totalPnl >= 0 ? '📈' : '📉';
    const top = (s.strategyBreakdown || [])
      .slice(0, 3)
      .map(
        (x, i) =>
          `${i + 1}. ${x.strategy}: ₹${x.totalPnl.toFixed(0)} (${x.winRate}% · ${x.trades}t)`,
      )
      .join('\n');

    const headers: Record<string, string> = {
      DAILY: '📊 <b>DAILY DIGEST — Today</b>',
      WEEKLY: '📊 <b>WEEKLY DIGEST — This Week</b>',
      OVERALL: '📊 <b>OVERALL DIGEST — All-Time</b>',
    };
    // Period performance block (or a friendly note on a flat period).
    const noActivity = data.tradeCount === 0;
    const perfBlock = noActivity
      ? [
          `😴 <b>No closed trades ${
            data.period === 'WEEKLY'
              ? 'this week'
              : data.period === 'DAILY'
                ? 'today'
                : 'yet'
          }.</b>`,
        ]
      : [
          `${pnlEmoji} <b>Net P&L:</b> ₹${s.totalPnl.toFixed(0)}`,
          `🎯 <b>Win Rate:</b> ${s.winRate}% (${s.wins}W / ${s.losses}L)`,
          `📊 <b>Profit Factor:</b> ${s.profitFactor}`,
          ``,
          `🏆 <b>Top strategies:</b>`,
          top || '—',
        ];

    const message = [
      headers[data.period] || `📊 <b>${data.period} PERFORMANCE DIGEST</b>`,
      data.rangeLabel ? `🗓 <i>${data.rangeLabel}</i>` : null,
      ``,
      ...perfBlock,
      ``,
      // Account snapshot — always current/all-time regardless of period.
      `💼 <b>Capital:</b> ₹${s.currentCapital.toFixed(0)} / ₹${s.initialCapital.toFixed(0)}`,
      `📦 <b>Open Positions:</b> ${s.openTrades}`,
      data.staleOpens > 0
        ? `⚠️ <b>Stale opens (≥5d):</b> ${data.staleOpens}`
        : null,
      ``,
      `⏰ ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`,
    ]
      .filter((l) => l !== null)
      .join('\n');

    try {
      await axios.post(
        `https://api.telegram.org/bot${this.botToken}/sendMessage`,
        {
          chat_id: this.chatId,
          text: message,
          parse_mode: 'HTML',
          disable_web_page_preview: true,
        },
        { timeout: 10000, family: 4 },
      );
      this.logger.log(`Telegram ${data.period} digest sent`);
    } catch (err: any) {
      if (err.response && err.response.data) {
        this.logger.error(
          `Failed to send ${data.period} digest: ${JSON.stringify(err.response.data)}`,
        );
      } else {
        this.logger.error(
          `Failed to send ${data.period} digest: ${err?.message || err}`,
        );
      }
    }
  }
}
