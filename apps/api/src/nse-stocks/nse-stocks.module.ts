import { Module } from '@nestjs/common';
import { NseStocksService } from './nse-stocks.service';
import { NseStocksController } from './nse-stocks.controller';
import { PrismaModule } from '../prisma/prisma.module';

@Module({
  imports: [PrismaModule],
  controllers: [NseStocksController],
  providers: [NseStocksService],
})
export class NseStocksModule {}
