import { Controller, Get, Query } from '@nestjs/common';
import { NseStocksService } from './nse-stocks.service';

@Controller('api/nse-stocks')
export class NseStocksController {
  constructor(private readonly nseStocksService: NseStocksService) {}

  @Get()
  search(@Query('q') query: string) {
    return this.nseStocksService.search(query);
  }
}
