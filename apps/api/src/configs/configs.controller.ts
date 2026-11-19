import { Controller, Get, Post, Delete, Param, Body, ParseIntPipe } from '@nestjs/common';
import { ConfigsService } from './configs.service';
import { CreateConfigDto } from './dto/create-config.dto';
import { LifecycleService } from './lifecycle.service';

@Controller('api/configs')
export class ConfigsController {
  constructor(
    private readonly configsService: ConfigsService,
    private readonly lifecycle: LifecycleService,
  ) {}

  @Get()
  findAll() {
    return this.configsService.findAll();
  }

  // Declared before ':symbol' so "scorecard" is not read as a stock symbol.
  @Get('scorecard')
  scorecard() {
    return this.lifecycle.scorecard();
  }

  /** Re-apply the lifecycle rules to every cell (also runs after each trade closes). */
  @Post('evaluate')
  evaluate() {
    return this.lifecycle.evaluateAll();
  }

  @Get(':symbol')
  findBySymbol(@Param('symbol') symbol: string) {
    return this.configsService.findBySymbol(symbol);
  }

  @Post('toggle')
  toggle(@Body() dto: CreateConfigDto) {
    return this.configsService.toggle(dto);
  }

  @Delete(':id')
  remove(@Param('id', ParseIntPipe) id: number) {
    return this.configsService.remove(id);
  }
}
