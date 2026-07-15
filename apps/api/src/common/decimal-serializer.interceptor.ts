import { CallHandler, ExecutionContext, Injectable, NestInterceptor } from '@nestjs/common';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

/**
 * Prisma returns Decimal columns as `Prisma.Decimal` objects, which serialize to
 * JSON *strings* (e.g. "100.5000"). The React frontend does numeric math on these
 * fields, so we recursively coerce every Decimal in a response to a plain number.
 * This keeps the API contract (numbers) identical to the pre-Decimal behaviour.
 */
function isDecimal(v: unknown): v is { toNumber: () => number } {
  // Prisma's Decimal (decimal.js) exposes both toNumber() and the internal
  // {s,e,d} fields. We duck-type rather than check constructor.name, which is
  // unreliable across Prisma/bundler versions (it leaked as {s,e,d} otherwise).
  if (typeof v !== 'object' || v === null) return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.toNumber === 'function' &&
    's' in o &&
    'e' in o &&
    'd' in o
  );
}

function convert(value: unknown): unknown {
  if (value == null) return value;
  if (isDecimal(value)) return value.toNumber();
  if (value instanceof Date) return value;
  if (Array.isArray(value)) return value.map(convert);
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = convert(v);
    }
    return out;
  }
  return value;
}

@Injectable()
export class DecimalSerializerInterceptor implements NestInterceptor {
  intercept(_context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return next.handle().pipe(map((data) => convert(data)));
  }
}
