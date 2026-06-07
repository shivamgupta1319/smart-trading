import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
  Logger,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { IS_PUBLIC_KEY } from './public.decorator';

/**
 * Global guard requiring a shared API key on every HTTP request.
 *
 * Auth is OPT-IN: if the `API_KEY` env var is not set, the guard is a no-op
 * (preserves the original open behaviour for local dev). When `API_KEY` is set,
 * callers must send it as either `x-api-key: <key>` or `Authorization: Bearer <key>`.
 */
@Injectable()
export class ApiKeyGuard implements CanActivate {
  private readonly logger = new Logger(ApiKeyGuard.name);

  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const required = process.env.API_KEY;
    if (!required) return true; // auth disabled

    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (isPublic) return true;

    const req = context.switchToHttp().getRequest();
    const headerKey = req.headers['x-api-key'];
    const authz: string | undefined = req.headers['authorization'];
    const bearer = authz?.startsWith('Bearer ') ? authz.slice(7) : undefined;
    const provided = headerKey || bearer;

    if (provided && provided === required) return true;

    this.logger.warn(`Rejected request to ${req.method} ${req.url} — bad API key`);
    throw new UnauthorizedException('Invalid or missing API key');
  }
}
