import { useState, useEffect } from 'react';
import axios from 'axios';
import { API } from '../config';

interface TokenStatus {
  present: boolean;
  expiresAt: string | null;
  expired: boolean | null;
  hoursLeft: number | null;
}
interface BrokerStatus {
  broker: string;
  dataSource: string;
  dhanConfigured: boolean;
  upstoxConfigured: boolean;
  dhanToken?: TokenStatus;
  liveSource?: string;
  historicalSource?: string;
}

export function Settings() {
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const fetchStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API}/api/engine/broker/status`);
      setStatus(res.data);
    } catch (err: any) {
      setError(err?.message || 'Could not load broker status.');
    } finally {
      setLoading(false);
    }
  };

  const [resetting, setResetting] = useState(false);
  const [resetMsg, setResetMsg] = useState<string | null>(null);

  useEffect(() => {
    fetchStatus();
  }, []);

  const resetPaperTrading = async () => {
    const ok = window.confirm(
      'This permanently deletes ALL trades, signals and selected stock+strategy configs.\n\n' +
        'Backtest reports and historical data are kept. Continue?',
    );
    if (!ok) return;
    setResetting(true);
    setResetMsg(null);
    try {
      const res = await axios.post(`${API}/api/admin/reset`, { confirm: 'RESET' });
      const d = res.data;
      setResetMsg(
        `Done — removed ${d.tradesDeleted} trades, ${d.signalsDeleted} signals, ${d.activeConfigsDeleted} configs.`,
      );
    } catch (err: any) {
      setResetMsg(err?.response?.data?.message || err?.message || 'Reset failed.');
    } finally {
      setResetting(false);
    }
  };

  const saveToken = async () => {
    if (!token.trim()) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const res = await axios.post(`${API}/api/engine/broker/dhan/token`, {
        token: token.trim(),
      });
      const ts: TokenStatus | undefined = res.data?.tokenStatus;
      if (ts?.expired === false) {
        setMessage(
          `✅ Token saved & active — Dhan live data on${
            ts.hoursLeft != null ? ` (expires in ${ts.hoursLeft}h)` : ''
          }.`,
        );
      } else if (ts?.expired === true) {
        setMessage('⚠️ Token saved but it is already expired — generate a fresh one.');
      } else {
        setMessage('✅ Token saved.');
      }
      setToken('');
      fetchStatus();
    } catch (err: any) {
      setError(err?.response?.data?.message || err?.message || 'Failed to save token.');
    } finally {
      setSaving(false);
    }
  };

  const ts = status?.dhanToken;
  const live = (status?.dataSource || '').toLowerCase();
  const onDhan = live === 'dhan';

  return (
    <div className="page animate-fade-in">
      <div
        className="page-header"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}
      >
        <div>
          <h1 className="page-title">
            Settings — <span>Market Data</span>
          </h1>
          <p className="page-subtitle">
            Paper trading uses simulated fills priced off a real market-data feed.
          </p>
        </div>
        <button onClick={fetchStatus} disabled={loading} className="btn btn-secondary">
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="card" style={{ padding: '1rem', marginBottom: '1.5rem', color: 'var(--red)' }}>
          ⚠️ {error}
        </div>
      )}

      {/* Live status card */}
      <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem', borderTop: '4px solid var(--cyan)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
          <h2 className="card-title" style={{ margin: 0 }}>Data source</h2>
          <span className={`badge ${onDhan ? 'badge-active' : ''}`}>
            {loading ? '…' : (status?.dataSource || 'unknown')}
          </span>
        </div>
        <div className="grid-2" style={{ gap: '0.5rem 2rem' }}>
          <Row label="Live quotes" value={status?.liveSource || status?.dataSource || '—'} />
          <Row label="Historical" value={status?.historicalSource || 'yfinance'} />
          <Row label="Broker" value={status?.broker || '—'} />
          <Row
            label="Dhan token"
            value={
              !ts?.present
                ? 'not set'
                : ts.expired
                ? '⚠️ EXPIRED — refresh below'
                : `valid${ts.hoursLeft != null ? ` · ${ts.hoursLeft}h left` : ''}`
            }
            danger={ts?.expired === true}
          />
          {ts?.expiresAt && (
            <Row label="Expires at" value={new Date(ts.expiresAt).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} />
          )}
        </div>
        {!onDhan && (
          <p className="page-subtitle" style={{ marginTop: '1rem', marginBottom: 0 }}>
            Currently on the free yfinance fallback. Paste a fresh Dhan token below to switch live quotes to Dhan.
          </p>
        )}
      </div>

      {/* Token refresh card */}
      <div className="card" style={{ padding: '1.5rem' }}>
        <h2 className="card-title" style={{ marginTop: 0 }}>Refresh Dhan access token</h2>
        <p className="page-subtitle" style={{ marginTop: 0 }}>
          Dhan tokens expire ~24h. Generate a new one in the Dhan app (Profile → DhanHQ Trading APIs → Access Token),
          paste it here, and hit Save — the engine picks it up instantly, no restart.
        </p>
        <textarea
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Paste new Dhan access token (JWT)…"
          rows={4}
          style={{
            width: '100%',
            background: 'var(--bg-input)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            padding: '0.75rem',
            fontFamily: 'monospace',
            fontSize: '0.85rem',
            resize: 'vertical',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '1rem' }}>
          <button onClick={saveToken} disabled={saving || !token.trim()} className="btn btn-primary">
            {saving ? 'Saving…' : 'Save & Activate'}
          </button>
          {message && <span style={{ color: 'var(--text-secondary)' }}>{message}</span>}
        </div>
      </div>

      {/* Danger zone — reset paper trading */}
      <div className="card" style={{ padding: '1.5rem', marginTop: '1.5rem', borderTop: '4px solid var(--red)' }}>
        <h2 className="card-title" style={{ marginTop: 0, color: 'var(--red)' }}>Danger zone — reset paper trading</h2>
        <p className="page-subtitle" style={{ marginTop: 0 }}>
          Clears all trades, live signals and selected (stock × strategy) configs so you can start fresh —
          e.g. before running auto-select. Backtest reports and historical price data are preserved.
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '1rem' }}>
          <button onClick={resetPaperTrading} disabled={resetting} className="btn btn-danger">
            {resetting ? 'Resetting…' : 'Reset paper trading'}
          </button>
          {resetMsg && <span style={{ color: 'var(--text-secondary)' }}>{resetMsg}</span>}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.35rem 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ color: danger ? 'var(--red)' : 'var(--text-primary)', fontWeight: 500 }}>{value}</span>
    </div>
  );
}
