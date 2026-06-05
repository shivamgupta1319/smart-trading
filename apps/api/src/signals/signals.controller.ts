import { Controller, Get, Post, Patch, Param, Body, ParseIntPipe, HttpCode } from '@nestjs/common';
import { SignalsService } from './signals.service';
import { SignalsGateway } from './signals.gateway';
import { TelegramService } from '../telegram/telegram.service';
import { CreateSignalDto } from './dto/create-signal.dto';

@Controller('api/signals')
export class SignalsController {
  constructor(
    private readonly signalsService: SignalsService,
    private readonly signalsGateway: SignalsGateway,
    private readonly telegramService: TelegramService,
  ) {}

  @Get()
  findAll() {
    return this.signalsService.findAll();
  }

  @Get('active')
  findActive() {
    return this.signalsService.findActive();
  }

  @Post('new')
  @HttpCode(201)
  async create(@Body() dto: CreateSignalDto) {
    const { signal, isNew } = await this.signalsService.create(dto);
    // Emit WebSocket event to all connected clients only if the signal is new
    if (isNew) {
      const payload = {
        ...signal,
        symbol: signal.stock?.symbol,
      };
      this.signalsGateway.emitNewAlert(payload);

      // Send Telegram notification
      this.telegramService.sendSignalAlert({
        signalType: dto.signalType,
        symbol: signal.stock?.symbol,
        strategyName: dto.strategyName,
        entryPrice: dto.entryPrice,
        stopLoss: dto.stopLoss,
        target: dto.target,
        holdDuration: dto.holdDuration,
      });
    }
    return signal;
  }

  @Patch(':id/close')
  close(@Param('id', ParseIntPipe) id: number, @Body() body: any) {
    if (body && body.exitPrice !== undefined) {
      return this.signalsService.closeWithPrice(id, Number(body.exitPrice));
    }
    return this.signalsService.close(id);
  }

  @Patch(':id/update-sl')
  async updateStopLoss(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: { newStopLoss: number; trailingState: string; peakPrice?: number },
  ) {
    const result = await this.signalsService.updateStopLoss(
      id,
      body.newStopLoss,
      body.trailingState,
      body.peakPrice,
    );

    // Send Telegram notification for trailing SL events
    if (result) {
      const signal = await this.signalsService.findAll();
      const sig = signal.find((s) => s.id === id);
      const symbol = sig?.stock?.symbol || 'Unknown';

      if (body.trailingState === 'BREAKEVEN') {
        this.telegramService.sendTrailingAlert({
          symbol,
          event: 'BREAKEVEN',
          newStopLoss: body.newStopLoss,
        });
      } else if (body.trailingState === 'PROFIT_LOCK') {
        this.telegramService.sendTrailingAlert({
          symbol,
          event: 'PROFIT_LOCK',
          newStopLoss: body.newStopLoss,
        });
      }
    }

    return result;
  }

  @Patch(':id/partial-close')
  async partialClose(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: { percent: number; exitPrice: number; reason: string },
  ) {
    const result = await this.signalsService.partialClose(
      id,
      body.percent,
      body.exitPrice,
      body.reason,
    );

    if (result) {
      const signal = await this.signalsService.findAll();
      const sig = signal.find((s) => s.id === id);
      const symbol = sig?.stock?.symbol || 'Unknown';
      
      this.telegramService.sendPartialCloseAlert({
        symbol,
        percent: body.percent,
        exitPrice: body.exitPrice,
        reason: body.reason,
        lotPnl: result.lotPnl,
        remainingQty: result.newRemainingQty,
      });
    }

    return result;
  }
}
