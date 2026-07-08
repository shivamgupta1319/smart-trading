import { Module } from '@nestjs/common';
import { ReportsService } from './reports.service';
import { TradesModule } from '../trades/trades.module';

@Module({
  imports: [TradesModule], // provides TradesService; TelegramService is @Global
  providers: [ReportsService],
})
export class ReportsModule {}
