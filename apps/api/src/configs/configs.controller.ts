import { Controller, Get, Post, Delete, Param, Body, ParseIntPipe } from '@nestjs/common';
import { ConfigsService } from './configs.service';
import { CreateConfigDto } from './dto/create-config.dto';

@Controller('api/configs')
export class ConfigsController {
  constructor(private readonly configsService: ConfigsService) {}

  @Get()
  findAll() {
    return this.configsService.findAll();
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
