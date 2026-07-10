import { Module } from '@nestjs/common';
import { ReportsService } from './reports.service';
import { TradesModule } from '../trades/trades.module';
import { PrismaModule } from '../prisma/prisma.module';

@Module({
  imports: [TradesModule, PrismaModule], // TradesService + PrismaService; TelegramService is @Global
  providers: [ReportsService],
})
export class ReportsModule {}
