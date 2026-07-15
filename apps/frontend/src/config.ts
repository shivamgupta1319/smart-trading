import axios from 'axios';

// In a production build the SPA is served behind nginx which proxies /api and
// /socket.io on the SAME origin, so default to RELATIVE paths (empty base). Only dev
// (vite dev server) talks to a separate localhost:3000 API. An explicit VITE_API_URL
// still overrides both. (A hardcoded localhost:3000 here shipped to the browser and
// caused ERR_CONNECTION_REFUSED on the public site.)
export const API_BASE = (
  import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:3000')
).replace(/\/+$/, '');
export const API = API_BASE;
export const API_URL = `${API_BASE}/api`;
export const SOCKET_URL = API_BASE;

/**
 * The API key is NOT baked into the bundle. The browser obtains it after the
 * user enters the app PIN (see AuthGate → POST /api/auth/login), and we keep it
 * in sessionStorage (cleared when the tab closes). All axios requests then carry
 * it via the default header.
 */
const KEY_STORAGE = 'st_api_key';

export function getApiKey(): string {
  return sessionStorage.getItem(KEY_STORAGE) || '';
}

export function setApiKey(key: string): void {
  sessionStorage.setItem(KEY_STORAGE, key);
  if (key) axios.defaults.headers.common['x-api-key'] = key;
}

export function clearApiKey(): void {
  sessionStorage.removeItem(KEY_STORAGE);
  delete axios.defaults.headers.common['x-api-key'];
}

// Re-apply any key already stored this session (e.g. on a page refresh).
const _existing = getApiKey();
if (_existing) axios.defaults.headers.common['x-api-key'] = _existing;
