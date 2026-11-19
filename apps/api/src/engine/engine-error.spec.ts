import { describe, expect, it } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import { engineErrorToHttp } from './engine-error';

function engineAnswered(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError('failed', 'ERR_BAD_REQUEST', config, {}, { status, data, statusText: '', headers: {}, config });
}

describe('engineErrorToHttp', () => {
  it("passes on the engine's refusal and its reason", () => {
    expect(engineErrorToHttp(engineAnswered(400, { detail: 'Monte-Carlo needs at least 5 trades.' }))).toEqual({
      status: 400,
      message: 'Monte-Carlo needs at least 5 trades.',
    });
    expect(engineErrorToHttp(engineAnswered(409, { detail: 'already running' })).status).toBe(409);
    expect(engineErrorToHttp(engineAnswered(404, {})).message).toBe('The engine refused the request.');
  });

  it('reports an engine failure as 502, not as a bug in this API', () => {
    expect(engineErrorToHttp(engineAnswered(500, { detail: 'boom' }))).toEqual({ status: 502, message: 'The engine failed: boom' });
  });

  it('tells a timeout from an unreachable engine', () => {
    expect(engineErrorToHttp(new AxiosError('timeout', 'ECONNABORTED')).status).toBe(504);
    expect(engineErrorToHttp(new AxiosError('refused', 'ECONNREFUSED')).status).toBe(502);
  });

  it('keeps a validation list readable', () => {
    expect(engineErrorToHttp(engineAnswered(422, { detail: [{ msg: 'field required' }] })).message).toContain('field required');
  });
});
