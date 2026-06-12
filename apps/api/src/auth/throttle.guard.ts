import {
  CanActivate,
  ExecutionContext,
  Injectable,
  HttpException,
  HttpStatus,
} from '@nestjs/common';

/**
 * Lightweight in-memory fixed-window rate limiter (no external deps).
 * Limits each client IP to RATE_LIMIT requests per 60s window.
 * Good enough for a single-node deployment; swap for @nestjs/throttler + Redis
 * if this ever runs multi-instance.
 */
@Injectable()
export class ThrottleGuard implements CanActivate {
  private readonly hits = new Map<string, { count: number; reset: number }>();
  private readonly limit = Number(process.env.RATE_LIMIT || 240);
  private readonly windowMs = 60_000;

  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest();
    const ip =
      (req.headers['x-forwarded-for'] as string)?.split(',')[0]?.trim() ||
      req.ip ||
      req.socket?.remoteAddress ||
      'unknown';
    const now = Date.now();
    const entry = this.hits.get(ip);

    if (!entry || now > entry.reset) {
      this.hits.set(ip, { count: 1, reset: now + this.windowMs });
      // opportunistic cleanup to bound memory
      if (this.hits.size > 10_000) {
        for (const [k, v] of this.hits) if (now > v.reset) this.hits.delete(k);
      }
      return true;
    }

    entry.count++;
    if (entry.count > this.limit) {
      throw new HttpException('Too many requests', HttpStatus.TOO_MANY_REQUESTS);
    }
    return true;
  }
}
