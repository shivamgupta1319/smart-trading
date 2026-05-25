import { Controller, Get, Query, Patch, Body, Param } from '@nestjs/common';
import { NseStocksService } from './nse-stocks.service';

@Controller('api/nse-stocks')
export class NseStocksController {
  constructor(private readonly nseStocksService: NseStocksService) {}

  @Get()
  search(@Query('q') query: string) {
    return this.nseStocksService.search(query);
  }

  @Get('all')
  getAll() {
    return this.nseStocksService.getAll();
  }

  @Patch('update-sector')
  updateSector(@Body() body: { symbol: string; sector: string }) {
    return this.nseStocksService.updateSector(body.symbol, body.sector);
  }

  @Get('sectors/list')
  getSectors() {
    return this.nseStocksService.getSectors();
  }

  @Get('sectors/:sector')
  getBySector(@Param('sector') sector: string) {
    return this.nseStocksService.getBySector(sector);
  }
}
