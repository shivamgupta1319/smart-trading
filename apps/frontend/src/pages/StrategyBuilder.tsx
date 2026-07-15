import { useState, useEffect } from 'react';
import axios from 'axios';
import { API } from '../config';
import { AddStockModal } from '../components/AddStockModal';

const INDICATORS = ['CLOSE', 'EMA', 'SMA', 'RSI', 'ATR'];
const OPS = ['>', '<', '>=', '<=', 'crosses_above', 'crosses_below'];
const OP_LABEL: Record<string, string> = {
  '>': '>', '<': '<', '>=': '≥', '<=': '≤',
  crosses_above: 'crosses ↑', crosses_below: 'crosses ↓',
};
const NEEDS_LEN = (ind: string) => ind !== 'CLOSE';

interface Operand { ind: string; len: number; }
interface Condition {
  left: Operand;
  op: string;
  rightKind: 'ind' | 'value';
  right: Operand;
  value: number;
}

const blankCondition = (): Condition => ({
  left: { ind: 'EMA', len: 50 },
  op: '>',
  rightKind: 'ind',
  right: { ind: 'EMA', len: 200 },
  value: 0,
});

const STORAGE = 'st_custom_specs';

export function StrategyBuilder() {
  const [name, setName] = useState('My Strategy');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [timeframe, setTimeframe] = useState('1D');
  const [conditions, setConditions] = useState<Condition[]>([blankCondition()]);
  const [stopType, setStopType] = useState<'atr' | 'pct'>('atr');
  const [stopVal, setStopVal] = useState(2);
  const [targetType, setTargetType] = useState<'rr' | 'pct' | 'atr'>('rr');
  const [targetVal, setTargetVal] = useState(2);
  const [symbol, setSymbol] = useState('RELIANCE');
  const [company, setCompany] = useState('Reliance Industries Limited');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [metrics, setMetrics] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<any[]>([]);

  useEffect(() => {
    try { setSaved(JSON.parse(localStorage.getItem(STORAGE) || '[]')); } catch { setSaved([]); }
  }, []);

  const buildSpec = () => ({
    name, side, timeframe,
    entry: conditions.map((c) => ({
      left: NEEDS_LEN(c.left.ind) ? { ind: c.left.ind, len: c.left.len } : { ind: c.left.ind },
      op: c.op,
      right: c.rightKind === 'value'
        ? { value: c.value }
        : NEEDS_LEN(c.right.ind) ? { ind: c.right.ind, len: c.right.len } : { ind: c.right.ind },
    })),
    stop: stopType === 'atr' ? { type: 'atr', mult: stopVal, len: 14 } : { type: 'pct', value: stopVal },
    target: targetType === 'rr' ? { type: 'rr', value: targetVal }
      : targetType === 'atr' ? { type: 'atr', mult: targetVal, len: 14 }
      : { type: 'pct', value: targetVal },
  });

  const setCond = (i: number, patch: Partial<Condition>) =>
    setConditions((cs) => cs.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));

  const runBacktest = async () => {
    setRunning(true); setError(null); setMetrics(null);
    try {
      const res = await axios.post(`${API}/api/engine/custom-backtest`, { symbol, spec: buildSpec() });
      setMetrics(res.data.metrics);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.response?.data?.message || 'Backtest failed.');
    } finally {
      setRunning(false);
    }
  };

  const saveSpec = () => {
    const next = [...saved.filter((s) => s.name !== name), buildSpec()];
    localStorage.setItem(STORAGE, JSON.stringify(next));
    setSaved(next);
  };

  const deleteSpec = (specName: string) => {
    const next = saved.filter((s) => s.name !== specName);
    localStorage.setItem(STORAGE, JSON.stringify(next));
    setSaved(next);
  };

  const loadSpec = (spec: any) => {
    setName(spec.name); setSide(spec.side); setTimeframe(spec.timeframe);
    setConditions(spec.entry.map((e: any) => ({
      left: { ind: e.left.ind, len: e.left.len ?? 14 },
      op: e.op,
      rightKind: e.right.value !== undefined ? 'value' : 'ind',
      right: { ind: e.right.ind ?? 'EMA', len: e.right.len ?? 14 },
      value: e.right.value ?? 0,
    })));
    if (spec.stop?.type === 'atr') { setStopType('atr'); setStopVal(spec.stop.mult); }
    else { setStopType('pct'); setStopVal(spec.stop?.value ?? 2); }
    if (spec.target?.type === 'rr') { setTargetType('rr'); setTargetVal(spec.target.value); }
    else if (spec.target?.type === 'atr') { setTargetType('atr'); setTargetVal(spec.target.mult); }
    else { setTargetType('pct'); setTargetVal(spec.target?.value ?? 4); }
    setMetrics(null); setError(null);
  };

  const sel = { background: 'var(--bg-input, #1a1f2e)', color: 'var(--text-primary)', border: '1px solid var(--border)', borderRadius: 6, padding: '0.45rem 0.55rem', fontSize: '0.875rem' } as const;
  const num = { ...sel, width: 72 } as const;
  const sectionTitle = { fontSize: '0.8rem', textTransform: 'uppercase' as const, letterSpacing: '0.05em', color: 'var(--text-muted)', marginBottom: '0.85rem', fontWeight: 600 };

  return (
    <div className="page animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">Strategy <span>Builder</span></h1>
        <p className="page-subtitle">Compose entry rules from indicators, then backtest with realistic fills + Indian costs.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: '1.5rem', alignItems: 'start' }}>
        {/* ── Left: the builder ─────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

          {/* Basics */}
          <div className="card" style={{ padding: '1.5rem' }}>
            <div style={sectionTitle}>① Strategy basics</div>
            <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Name
                <input value={name} onChange={(e) => setName(e.target.value)} style={{ ...sel, width: 220 }} />
              </label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Direction
                <div style={{ display: 'flex', gap: '0.4rem' }}>
                  {(['BUY', 'SELL'] as const).map((s) => (
                    <button key={s} onClick={() => setSide(s)} className="btn btn-sm"
                      style={{
                        background: side === s ? (s === 'BUY' ? 'var(--green)' : 'var(--red)') : 'var(--bg-input, #1a1f2e)',
                        color: side === s ? '#fff' : 'var(--text-secondary)',
                        border: '1px solid var(--border)', minWidth: 64,
                      }}>
                      {s === 'BUY' ? '▲ BUY' : '▼ SELL'}
                    </button>
                  ))}
                </div>
              </div>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Timeframe
                <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} style={sel}>
                  <option>1D</option><option>15m</option><option>5m</option>
                </select>
              </label>
            </div>
          </div>

          {/* Entry conditions */}
          <div className="card" style={{ padding: '1.5rem' }}>
            <div style={sectionTitle}>② Entry conditions <span style={{ textTransform: 'none', letterSpacing: 0, color: 'var(--text-muted)', fontWeight: 400 }}>— all must be true</span></div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {conditions.map((c, i) => (
                <div key={i} style={{
                  display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap',
                  background: 'var(--bg-secondary, rgba(255,255,255,0.02))', border: '1px solid var(--border)',
                  borderRadius: 8, padding: '0.6rem 0.75rem',
                }}>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontWeight: 600, minWidth: 18 }}>{i === 0 ? 'IF' : '&'}</span>
                  <select value={c.left.ind} onChange={(e) => setCond(i, { left: { ...c.left, ind: e.target.value } })} style={sel}>{INDICATORS.map((x) => <option key={x}>{x}</option>)}</select>
                  {NEEDS_LEN(c.left.ind) && <input type="number" value={c.left.len} onChange={(e) => setCond(i, { left: { ...c.left, len: +e.target.value } })} style={num} aria-label="left length" />}
                  <select value={c.op} onChange={(e) => setCond(i, { op: e.target.value })} style={{ ...sel, fontWeight: 600 }}>{OPS.map((x) => <option key={x} value={x}>{OP_LABEL[x]}</option>)}</select>
                  <select value={c.rightKind} onChange={(e) => setCond(i, { rightKind: e.target.value as any })} style={sel}><option value="ind">indicator</option><option value="value">value</option></select>
                  {c.rightKind === 'ind' ? (
                    <>
                      <select value={c.right.ind} onChange={(e) => setCond(i, { right: { ...c.right, ind: e.target.value } })} style={sel}>{INDICATORS.map((x) => <option key={x}>{x}</option>)}</select>
                      {NEEDS_LEN(c.right.ind) && <input type="number" value={c.right.len} onChange={(e) => setCond(i, { right: { ...c.right, len: +e.target.value } })} style={num} aria-label="right length" />}
                    </>
                  ) : (
                    <input type="number" value={c.value} onChange={(e) => setCond(i, { value: +e.target.value })} style={num} aria-label="value" />
                  )}
                  <div style={{ marginLeft: 'auto' }}>
                    {conditions.length > 1 && <button className="btn btn-secondary btn-sm" onClick={() => setConditions((cs) => cs.filter((_, idx) => idx !== i))} aria-label="Remove condition">✕</button>}
                  </div>
                </div>
              ))}
            </div>
            <button className="btn btn-secondary btn-sm" onClick={() => setConditions((cs) => [...cs, blankCondition()])} style={{ marginTop: '0.85rem' }}>+ Add condition</button>
          </div>

          {/* Risk */}
          <div className="card" style={{ padding: '1.5rem' }}>
            <div style={sectionTitle}>③ Risk management</div>
            <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Stop loss
                <div style={{ display: 'flex', gap: '0.4rem' }}>
                  <select value={stopType} onChange={(e) => setStopType(e.target.value as any)} style={sel}><option value="atr">ATR ×</option><option value="pct">%</option></select>
                  <input type="number" value={stopVal} onChange={(e) => setStopVal(+e.target.value)} style={num} />
                </div>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Target
                <div style={{ display: 'flex', gap: '0.4rem' }}>
                  <select value={targetType} onChange={(e) => setTargetType(e.target.value as any)} style={sel}><option value="rr">R:R</option><option value="pct">%</option><option value="atr">ATR ×</option></select>
                  <input type="number" value={targetVal} onChange={(e) => setTargetVal(+e.target.value)} style={num} />
                </div>
              </label>
            </div>
          </div>
        </div>

        {/* ── Right: run panel (sticky) ─────────────────────── */}
        <div className="card" style={{ padding: '1.5rem', position: 'sticky', top: '1rem' }}>
          <div style={sectionTitle}>④ Backtest</div>

          <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Stock</label>
          <button onClick={() => setPickerOpen(true)}
            style={{
              width: '100%', textAlign: 'left', marginTop: '0.35rem', marginBottom: '1.1rem',
              background: 'var(--bg-input, #1a1f2e)', border: '1px solid var(--border)', borderRadius: 8,
              padding: '0.7rem 0.85rem', cursor: 'pointer', color: 'var(--text-primary)',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem',
            }}>
            <span style={{ overflow: 'hidden' }}>
              <div style={{ fontWeight: 700 }}>{symbol}</div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{company || 'Tap to choose'}</div>
            </span>
            <span style={{ color: 'var(--accent, #6366f1)', fontSize: '0.8rem', flexShrink: 0 }}>🔍 Change</span>
          </button>

          <button className="btn btn-primary" onClick={runBacktest} disabled={running} style={{ width: '100%', marginBottom: '0.6rem' }}>
            {running ? 'Running…' : '▶ Run Backtest'}
          </button>
          <button className="btn btn-secondary" onClick={saveSpec} style={{ width: '100%' }}>💾 Save strategy</button>

          {error && <div style={{ marginTop: '1rem', padding: '0.75rem', borderRadius: 8, background: 'rgba(239,68,68,0.1)', color: 'var(--red)', fontSize: '0.85rem' }}>⚠️ {error}</div>}

          {saved.length > 0 && (
            <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
              <div style={sectionTitle}>Saved</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {saved.map((s) => (
                  <div key={s.name} style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                    <button className="btn btn-secondary btn-sm" style={{ flex: 1, textAlign: 'left' }} onClick={() => loadSpec(s)}>
                      {s.side === 'SELL' ? '▼' : '▲'} {s.name}
                    </button>
                    <button className="btn btn-secondary btn-sm" onClick={() => deleteSpec(s.name)} aria-label={`Delete ${s.name}`}>🗑</button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      {metrics && (
        <div className="card animate-fade-in-up" style={{ padding: '1.5rem', marginTop: '1.5rem' }}>
          <h3 style={{ marginTop: 0 }}>Result — {name} on {symbol}</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem' }}>
            <Metric label="Net ROI" value={`${metrics.roiPercentage}%`} good={metrics.roiPercentage >= 0} />
            <Metric label="Win rate" value={`${metrics.winRate}%`} good={metrics.winRate >= 50} />
            <Metric label="Trades" value={metrics.totalTrades} />
            <Metric label="Profit factor" value={metrics.profitFactor} good={metrics.profitFactor >= 1} />
            <Metric label="Net profit" value={`₹${Number(metrics.netProfit).toLocaleString('en-IN')}`} good={metrics.netProfit >= 0} />
            <Metric label="Costs paid" value={`₹${Number(metrics.totalCosts).toLocaleString('en-IN')}`} />
            <Metric label="Max DD" value={`${metrics.maxDrawdownPct}%`} />
            <Metric label="Expectancy" value={`₹${metrics.expectancy}`} good={metrics.expectancy >= 0} />
          </div>
        </div>
      )}

      <AddStockModal
        isOpen={pickerOpen}
        title="Select a stock to backtest"
        actionLabel="Select"
        onClose={() => setPickerOpen(false)}
        onAdd={(sym, comp) => { setSymbol(sym); setCompany(comp || ''); setPickerOpen(false); }}
      />
    </div>
  );
}

function Metric({ label, value, good }: { label: string; value: any; good?: boolean }) {
  return (
    <div className="metric-card">
      <p className="metric-label">{label}</p>
      <p className="metric-value" style={good === undefined ? {} : { color: good ? 'var(--green)' : 'var(--red)' }}>{value}</p>
    </div>
  );
}
