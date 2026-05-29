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
      `${emoji} *${signal.signalType} SIGNAL*`,
      ``,
      `📈 *Stock:* ${signal.symbol || 'Unknown'}`,
      `🎯 *Strategy:* ${signal.strategyName}`,
      `${holdLabel}`,
      ``,
      `💰 *Entry:* ₹${signal.entryPrice.toFixed(2)}`,
      `🛑 *Stop Loss:* ₹${signal.stopLoss.toFixed(2)}`,
      `✅ *Target:* ₹${signal.target.toFixed(2)}`,
      `📊 *Risk:Reward:* 1:${rr}`,
      ``,
      `⏰ ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`,
    ].join('\n');

    try {
      await axios.post(
        `https://api.telegram.org/bot${this.botToken}/sendMessage`,
        {
          chat_id: this.chatId,
          text: message,
          parse_mode: 'Markdown',
          disable_web_page_preview: true,
        },
        { timeout: 10000 },
      );
      this.logger.log(
        `Telegram alert sent: ${signal.signalType} ${signal.symbol}`,
      );
    } catch (err: unknown) {
      if (err instanceof Error) {
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
      `${emoji} *TRADE CLOSED — ${trade.outcome}*`,
      ``,
      `📈 *Stock:* ${trade.symbol}`,
      `🎯 *Strategy:* ${trade.strategyName}`,
      ``,
      `💰 *Entry:* ₹${trade.entryPrice.toFixed(2)}`,
      `💰 *Exit:* ₹${trade.exitPrice.toFixed(2)}`,
      `${pnlEmoji} *P&L:* ₹${trade.pnl.toFixed(2)} (${trade.pnlPercent.toFixed(2)}%)`,
      ``,
      `⏰ ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}`,
    ].join('\n');

    try {
      await axios.post(
        `https://api.telegram.org/bot${this.botToken}/sendMessage`,
        {
          chat_id: this.chatId,
          text: message,
          parse_mode: 'Markdown',
          disable_web_page_preview: true,
        },
        { timeout: 10000 },
      );
    } catch (err: unknown) {
      if (err instanceof Error) {
        this.logger.error(`Failed to send Telegram close alert: ${err.message}`);
      } else {
        this.logger.error(`Failed to send Telegram close alert: ${String(err)}`);
      }
    }
  }
}
