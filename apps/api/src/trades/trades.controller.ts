import {
  Controller,
  Get,
  Patch,
  Param,
  Query,
  Body,
  ParseIntPipe,
  Delete,
} from '@nestjs/common';
import { TradesService } from './trades.service';

@Controller('api/trades')
export class TradesController {
  constructor(private readonly tradesService: TradesService) {}

  @Get()
  findAll(
    @Query('status') status?: string,
    @Query('strategy') strategyName?: string,
    @Query('holdDuration') holdDuration?: string,
    @Query('limit') limit?: string,
  ) {
    return this.tradesService.findAll({
      status,
      strategyName,
      holdDuration,
      limit: limit ? parseInt(limit) : undefined,
    });
  }

  @Get('stats')
  getStats() {
    return this.tradesService.getPortfolioStats();
  }

  @Get('risk')
  getRisk() {
    return this.tradesService.getRiskMetrics();
  }

  @Get(':id')
  findOne(@Param('id', ParseIntPipe) id: number) {
    return this.tradesService.findOne(id);
  }

  @Patch(':id/notes')
  updateNotes(
    @Param('id', ParseIntPipe) id: number,
    @Body('notes') notes: string,
  ) {
    return this.tradesService.updateNotes(id, notes);
  }

  @Patch(':id/close')
  manualClose(
    @Param('id', ParseIntPipe) id: number,
    @Body('exitPrice') exitPrice: number,
  ) {
    return this.tradesService.manualClose(id, exitPrice);
  }

  @Delete(':id')
  remove(@Param('id', ParseIntPipe) id: number) {
    return this.tradesService.remove(id);
  }
}
