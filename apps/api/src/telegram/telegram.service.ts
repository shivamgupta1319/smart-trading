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
}
