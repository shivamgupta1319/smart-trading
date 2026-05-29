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
}
