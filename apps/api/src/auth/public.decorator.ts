import { SetMetadata } from '@nestjs/common';

/**
 * Marks a route handler (or controller) as public — bypasses the global
 * ApiKeyGuard. Use sparingly (e.g. health checks).
 */
export const IS_PUBLIC_KEY = 'isPublic';
export const Public = () => SetMetadata(IS_PUBLIC_KEY, true);
