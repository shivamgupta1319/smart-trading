import { Controller, Get, Post, Patch, Param, Body, ParseIntPipe, HttpCode } from '@nestjs/common';
import { SignalsService } from './signals.service';
import { SignalsGateway } from './signals.gateway';
import { CreateSignalDto } from './dto/create-signal.dto';

@Controller('api/signals')
export class SignalsController {
  constructor(
    private readonly signalsService: SignalsService,
    private readonly signalsGateway: SignalsGateway,
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
    const signal = await this.signalsService.create(dto);
    // Emit WebSocket event to all connected clients
    this.signalsGateway.emitNewAlert({
      ...signal,
      symbol: (signal as any).stock?.symbol,
    });
    return signal;
  }

  @Patch(':id/close')
  close(@Param('id', ParseIntPipe) id: number) {
    return this.signalsService.close(id);
  }
}
