import { Controller, Get } from '@nestjs/common';
import { DhanService } from './dhan.service';

@Controller('api/dhan')
export class DhanController {
  constructor(private readonly dhan: DhanService) {}

  /** Real-money mode, limits, today's counters and open real positions. No secrets. */
  @Get('status')
  status() {
    return this.dhan.status();
  }
}
