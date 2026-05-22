import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { PrismaModule } from '../prisma/prisma.module';
import { StocksModule } from '../stocks/stocks.module';
import { ConfigsModule } from '../configs/configs.module';
import { SignalsModule } from '../signals/signals.module';
import { EngineModule } from '../engine/engine.module';
import { NseStocksModule } from '../nse-stocks/nse-stocks.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    PrismaModule,
    StocksModule,
    ConfigsModule,
    SignalsModule,
    EngineModule,
    NseStocksModule,
  ],
})
export class AppModule {}
