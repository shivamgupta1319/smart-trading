import { BadRequestException, Controller, Get, Query } from '@nestjs/common';
import { ReportsService } from './reports.service';
import { formatDigest, type Period } from './digest';

const PERIODS: Period[] = ['DAILY', 'WEEKLY', 'OVERALL'];

@Controller('api/reports')
export class ReportsController {
  constructor(private readonly reports: ReportsService) {}

  /** The digest that WOULD be sent now, as figures and as message text. Sends nothing. */
  @Get('digest-preview')
  async preview(@Query('period') period = 'DAILY') {
    const p = period.toUpperCase() as Period;
    if (!PERIODS.includes(p)) throw new BadRequestException(`period must be one of ${PERIODS.join(', ')}`);
    const data = await this.reports.build(p);
    return { data, text: formatDigest(data) };
  }
}
