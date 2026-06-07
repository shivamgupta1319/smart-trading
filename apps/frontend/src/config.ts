import axios from 'axios';

export const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:3000').replace(/\/+$/, '');
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
