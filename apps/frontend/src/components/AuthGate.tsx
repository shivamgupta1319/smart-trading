import { useEffect, useState } from 'react';
import axios from 'axios';
import { API, getApiKey, setApiKey } from '../config';

type Status = 'loading' | 'locked' | 'authed';

/**
 * Single-user lock screen. Wraps the whole app: until the correct PIN is
 * entered (which returns the API key from the backend), nothing else renders.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>('loading');
  const [pin, setPin] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (getApiKey()) {
      setStatus('authed');
      return;
    }
    axios
      .get(`${API}/api/auth/config`)
      .then(async ({ data }) => {
        if (!data.authRequired) {
          setStatus('authed'); // backend is open; no key needed
        } else if (data.pinRequired) {
          setStatus('locked');
        } else {
          // auth on, but no PIN configured → fetch the key silently
          const res = await axios.post(`${API}/api/auth/login`, {});
          setApiKey(res.data.apiKey);
          setStatus('authed');
        }
      })
      .catch(() => setStatus('locked')); // if we can't reach config, show the lock
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pin.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await axios.post(`${API}/api/auth/login`, { pin: pin.trim() });
      setApiKey(res.data.apiKey);
      setStatus('authed');
    } catch {
      setError('Incorrect PIN');
      setPin('');
    } finally {
      setSubmitting(false);
    }
  };

  if (status === 'authed') return <>{children}</>;

  if (status === 'loading') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-base, #0a0e17)' }}>
        <div className="spinner"></div>
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg-base, #0a0e17)', padding: '1rem',
      }}
    >
      <form onSubmit={submit} className="card animate-fade-in-up" style={{ width: '100%', maxWidth: '360px', padding: '2.5rem 2rem', textAlign: 'center' }}>
        <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>⚡</div>
        <h1 className="page-title" style={{ fontSize: '1.6rem', marginBottom: '0.25rem' }}>SmartTrader</h1>
        <p className="page-subtitle" style={{ marginBottom: '1.5rem' }}>Enter your app PIN to continue</p>
        <input
          type="password"
          inputMode="numeric"
          autoFocus
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          placeholder="••••"
          aria-label="App PIN"
          style={{
            width: '100%', textAlign: 'center', letterSpacing: '0.5rem', fontSize: '1.5rem',
            background: 'var(--bg-input)', color: 'var(--text-primary)',
            border: `1px solid ${error ? 'var(--red)' : 'var(--border)'}`,
            borderRadius: '10px', padding: '0.85rem', marginBottom: '1rem',
          }}
        />
        {error && <p style={{ color: 'var(--red)', marginTop: 0, marginBottom: '1rem' }}>⚠️ {error}</p>}
        <button type="submit" className="btn btn-primary" disabled={submitting || !pin.trim()} style={{ width: '100%', padding: '0.85rem' }}>
          {submitting ? 'Unlocking…' : 'Unlock'}
        </button>
      </form>
    </div>
  );
}
