/**
 * Settings shared with the Python engine — read from config/trading.json.
 *
 * Every constant the two runtimes must agree on (fund size, leverage, risk cap,
 * transaction costs) used to be typed twice and kept in step by "MUST match"
 * comments. Both sides now read the same file; `apps/engine/shared_config.py` is
 * the twin.
 *
 * Lookup order for a value: environment variable of the same name → the file.
 * There is no in-code default: a missing key is an error at start-up.
 */
import { existsSync, readFileSync } from 'fs';
import { join } from 'path';

const candidates = (): string[] => {
  const paths: string[] = [];
  if (process.env.TRADING_CONFIG_PATH) paths.push(process.env.TRADING_CONFIG_PATH);
  paths.push(join(process.cwd(), 'config', 'trading.json')); // image (/app) and repo root
  paths.push(join(process.cwd(), '..', '..', 'config', 'trading.json')); // run from apps/api
  paths.push(join(__dirname, '..', 'config', 'trading.json')); // next to dist/
  return paths;
};

let cache: Record<string, number> | null = null;

const values = (): Record<string, number> => {
  if (cache) return cache;
  const path = candidates().find((p) => existsSync(p));
  if (!path) {
    throw new Error(`config/trading.json not found (tried: ${candidates().join(', ')})`);
  }
  const raw = JSON.parse(readFileSync(path, 'utf8')) as Record<string, unknown>;
  const flat: Record<string, number> = {};
  for (const body of Object.values(raw)) {
    if (body && typeof body === 'object' && !Array.isArray(body)) {
      Object.assign(flat, body as Record<string, number>);
    }
  }
  cache = flat;
  return flat;
};

/** A shared setting as a number: env override first, else the file. */
export const shared = (name: string): number => {
  const env = process.env[name];
  if (env !== undefined && env !== '') {
    const n = Number(env);
    if (!Number.isFinite(n)) throw new Error(`${name}=${JSON.stringify(env)} is not a number`);
    return n;
  }
  const v = values()[name];
  if (typeof v !== 'number' || !Number.isFinite(v)) {
    throw new Error(`${name} is not defined in config/trading.json`);
  }
  return v;
};

/**
 * RISK_PER_TRADE_PCT as a fraction, refusing a percent-style value.
 * `RISK_PER_TRADE_PCT=2` (meant as 2%) used to be read as 200% of the fund,
 * which silently switched the risk cap off.
 */
export const riskPerTradeFraction = (): number => {
  const value = shared('RISK_PER_TRADE_PCT');
  if (!(value > 0 && value <= 0.2)) {
    throw new Error(
      `RISK_PER_TRADE_PCT=${value} must be a fraction of the fund between 0 and 0.2 ` +
        '(0.02 means 2%). A value like 2 would disable the risk cap.',
    );
  }
  return value;
};
