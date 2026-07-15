import { Controller, Post, Body, BadRequestException } from '@nestjs/common';
import { AdminService } from './admin.service';

@Controller('api/admin')
export class AdminController {
  constructor(private readonly adminService: AdminService) {}

  /**
   * Destructive: clears all trades, signals and active configs. Requires an
   * explicit `{ confirm: "RESET" }` body so it can't be triggered by accident.
   * (The global ApiKeyGuard already gates the route when API_KEY is set.)
   */
  @Post('reset')
  reset(@Body() body: { confirm?: string }) {
    if (body?.confirm !== 'RESET') {
      throw new BadRequestException('Send { "confirm": "RESET" } to confirm this destructive action.');
    }
    return this.adminService.reset();
  }
}
