import axios from 'axios';

/**
 * What the API should answer when a call to the Python engine fails.
 *
 * - The engine refused the request (4xx): pass its status and its reason on unchanged, so
 *   the page can say "need at least 5 trades" instead of "internal server error".
 * - The engine failed (5xx), did not answer or timed out: 502/504 with a plain reason.
 */
export function engineErrorToHttp(err: unknown): { status: number; message: string } {
  if (axios.isAxiosError(err)) {
    const res = err.response;
    if (res) {
      const body = res.data as { detail?: unknown; message?: unknown } | undefined;
      const raw = body?.detail ?? body?.message;
      const reason = typeof raw === 'string' ? raw : raw ? JSON.stringify(raw) : '';
      if (res.status >= 400 && res.status < 500) {
        return { status: res.status, message: reason || 'The engine refused the request.' };
      }
      return { status: 502, message: reason ? `The engine failed: ${reason}` : 'The engine failed while working on this request.' };
    }
    if (err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT') {
      return { status: 504, message: 'The engine took too long to answer. Try again.' };
    }
    return { status: 502, message: 'The engine could not be reached. Try again in a minute.' };
  }
  return { status: 500, message: 'Unexpected error while calling the engine.' };
}
