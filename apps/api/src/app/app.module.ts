import { Module } from '@nestjs/common';
import { APP_GUARD, APP_INTERCEPTOR } from '@nestjs/core';
import { ConfigModule } from '@nestjs/config';
import { ApiKeyGuard } from '../auth/api-key.guard';
import { ThrottleGuard } from '../auth/throttle.guard';
import { AuthController } from '../auth/auth.controller';
import { DecimalSerializerInterceptor } from '../common/decimal-serializer.interceptor';
import { PrismaModule } from '../prisma/prisma.module';
import { StocksModule } from '../stocks/stocks.module';
import { ConfigsModule } from '../configs/configs.module';
import { SignalsModule } from '../signals/signals.module';
import { EngineModule } from '../engine/engine.module';
import { NseStocksModule } from '../nse-stocks/nse-stocks.module';
import { TradesModule } from '../trades/trades.module';
import { TelegramModule } from '../telegram/telegram.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    PrismaModule,
    StocksModule,
    ConfigsModule,
    SignalsModule,
    EngineModule,
    NseStocksModule,
    TradesModule,
    TelegramModule,
  ],
  controllers: [AuthController],
  providers: [
    // Order matters: rate-limit first, then API-key auth.
    { provide: APP_GUARD, useClass: ThrottleGuard },
    { provide: APP_GUARD, useClass: ApiKeyGuard },
    // Coerce Prisma Decimal -> number in all JSON responses.
    { provide: APP_INTERCEPTOR, useClass: DecimalSerializerInterceptor },
  ],
})
export class AppModule {}
