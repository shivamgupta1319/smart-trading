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

  @Post()
  upsert(@Body() dto: CreateConfigDto) {
    return this.configsService.upsert(dto);
  }

  @Delete(':id')
  remove(@Param('id', ParseIntPipe) id: number) {
    return this.configsService.remove(id);
  }
}
