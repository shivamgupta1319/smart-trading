import { Controller, Post, Get, Body, HttpCode, UnauthorizedException } from '@nestjs/common';
import { Public } from './public.decorator';

/**
 * Single-user PIN gate. The browser never bakes the API key; it obtains the key
 * only after presenting the correct app PIN. (Real multi-user auth is out of
 * scope by design — this is a personal app.)
 *
 *   GET  /api/auth/config  -> { pinRequired, authRequired }
 *   POST /api/auth/login   -> { apiKey }   (401 on wrong PIN)
 */
@Controller('api/auth')
export class AuthController {
  @Public()
  @Get('config')
  config() {
    return {
      pinRequired: !!process.env.APP_PIN,
      authRequired: !!process.env.API_KEY,
    };
  }

  @Public()
  @Post('login')
  @HttpCode(200)
  login(@Body() body: { pin?: string }) {
    const required = process.env.APP_PIN;
    if (required && String(body?.pin ?? '') !== required) {
      throw new UnauthorizedException('Invalid PIN');
    }
    // Correct PIN (or no PIN configured): hand back the shared API key.
    return { apiKey: process.env.API_KEY || '' };
  }
}
