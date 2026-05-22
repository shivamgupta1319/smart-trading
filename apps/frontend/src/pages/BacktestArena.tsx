import { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://localhost:3000';

const STRATEGIES = [
  { name: '15m_ORB', label: '15m Opening Range Breakout', group: 'Intraday', timeframe: '15m' },
  { name: 'VWAP_Supertrend', label: 'VWAP + Supertrend (10,3)', group: 'Intraday', timeframe: '15m' },
  { name: 'EMA_RSI', label: '9/15 EMA Crossover + RSI', group: 'Intraday', timeframe: '5m' },
  { name: 'MACD_Zero', label: 'MACD Zero-Line Cross', group: 'Intraday', timeframe: '15m' },
  { name: 'Inside_Bar', label: 'Inside Bar Breakout', group: 'Intraday', timeframe: '15m' },
  { name: 'SMA44_Pullback', label: '44 SMA Pullback', group: 'Swing', timeframe: '1D' },
  { name: 'EMA200_MACD', label: '200 EMA + MACD Golden Trend', group: 'Swing', timeframe: '1D' },
  { name: 'BB_Squeeze', label: 'Bollinger Band Squeeze', group: 'Swing', timeframe: '1D' },
  { name: 'RSI_Divergence', label: 'RSI Divergence', group: 'Swing', timeframe: '1D' },
  { name: 'Golden_Cross', label: '50/200 Golden Cross', group: 'Swing', timeframe: '1D' },
];

interface Stock { id: number; symbol: string; name: string; isActive: boolean; }
interface BacktestResult { strategy: string; timeframe: string; metrics: { winRate: number; totalTrades: number; maxDrawdown: number; expectancy: number; }; }

export function BacktestArena() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [selectedStock, setSelectedStock] = useState('');
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [newSymbol, setNewSymbol] = useState('');
  const [newName, setNewName] = useState('');
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [fetching, setFetching] = useState(false);
  const [running, setRunning] = useState(false);
  const [settingActive, setSettingActive] = useState(false);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);

  useEffect(() => {
    axios.get(`${API}/api/stocks`).then(r => setStocks(r.data)).catch(() => {});
  }, []);

  const showMessage = (type: string, text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  const addStock = async () => {
    if (!newSymbol || !newName) return;
    try {
      const r = await axios.post(`${API}/api/stocks`, {
        symbol: newSymbol.toUpperCase(),
        name: newName,
      });
      setStocks(prev => [...prev, r.data]);
      setNewSymbol('');
      setNewName('');
      showMessage('success', `✓ ${newSymbol.toUpperCase()} added`);
    } catch (e: any) {
      showMessage('error', e.response?.data?.message || 'Failed to add stock');
    }
  };

  const fetchHistory = async () => {
    if (!selectedStock) return;
    setFetching(true);
    try {
      await axios.post(`${API}/api/engine/fetch-history`, { symbol: selectedStock });
      showMessage('success', `✓ History fetched for ${selectedStock}`);
    } catch (e: any) {
      showMessage('error', e.response?.data?.message || 'Failed to fetch history');
    } finally {
      setFetching(false);
    }
  };

  const runBacktest = async () => {
    if (!selectedStock || !selectedStrategy) return;
    setRunning(true);
    const strategy = STRATEGIES.find(s => s.name === selectedStrategy)!;
    try {
      const r = await axios.post(`${API}/api/engine/run-backtest`, {
        symbol: selectedStock,
        strategy: selectedStrategy,
        timeframe: strategy.timeframe,
      });
      setResults(prev => {
        const filtered = prev.filter(p => p.strategy !== selectedStrategy);
        return [{ strategy: selectedStrategy, timeframe: strategy.timeframe, metrics: r.data.metrics }, ...filtered];
      });
      showMessage('success', `✓ Backtest complete: ${strategy.label}`);
    } catch (e: any) {
      showMessage('error', e.response?.data?.message || 'Backtest failed. Fetch history first.');
    } finally {
      setRunning(false);
    }
  };

  const setActive = async (strategyName: string, timeframe: string) => {
    const stock = stocks.find(s => s.symbol === selectedStock);
    if (!stock) return;
    setSettingActive(true);
    try {
      await axios.post(`${API}/api/configs`, {
        stockId: stock.id,
        strategyName,
        timeframe,
      });
      showMessage('success', `✓ ${selectedStock} will now be monitored with ${strategyName}`);
    } catch {
      showMessage('error', 'Failed to set active strategy');
    } finally {
      setSettingActive(false);
    }
  };

  const bestResult = results.length
    ? results.reduce((a, b) => a.metrics.expectancy > b.metrics.expectancy ? a : b)
    : null;

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Backtest <span>Arena</span></h1>
        <p className="page-subtitle">Run strategies against historical data and find your edge</p>
      </div>

      {/* Add Stock */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-title">Add NSE Stock</div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Symbol</label>
            <input
              className="form-input"
              placeholder="RELIANCE"
              value={newSymbol}
              onChange={e => setNewSymbol(e.target.value.toUpperCase())}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Company Name</label>
            <input
              className="form-input"
              placeholder="Reliance Industries"
              value={newName}
              onChange={e => setNewName(e.target.value)}
            />
          </div>
          <button className="btn btn-secondary" onClick={addStock}>+ Add Stock</button>
        </div>
      </div>

      {/* Select & Run */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-title">Configure & Run</div>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Stock</label>
            <select className="form-select" value={selectedStock} onChange={e => setSelectedStock(e.target.value)}>
              <option value="">— Select stock —</option>
              {stocks.map(s => <option key={s.id} value={s.symbol}>{s.symbol} — {s.name}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Strategy</label>
            <select className="form-select" value={selectedStrategy} onChange={e => setSelectedStrategy(e.target.value)}>
              <option value="">— Select strategy —</option>
              <optgroup label="Intraday">
                {STRATEGIES.filter(s => s.group === 'Intraday').map(s => (
                  <option key={s.name} value={s.name}>{s.label}</option>
                ))}
              </optgroup>
              <optgroup label="Swing">
                {STRATEGIES.filter(s => s.group === 'Swing').map(s => (
                  <option key={s.name} value={s.name}>{s.label}</option>
                ))}
              </optgroup>
            </select>
          </div>
          <button className="btn btn-secondary" onClick={fetchHistory} disabled={!selectedStock || fetching}>
            {fetching ? <><div className="spinner"></div> Fetching...</> : '⬇ Fetch History'}
          </button>
          <button className="btn btn-primary" onClick={runBacktest} disabled={!selectedStock || !selectedStrategy || running}>
            {running ? <><div className="spinner"></div> Running...</> : '▶ Run Backtest'}
          </button>
        </div>
      </div>

      {/* Message */}
      {message && (
        <div className={`alert alert-${message.type === 'success' ? 'success' : 'error'}`} style={{ marginBottom: '1.5rem' }}>
          {message.text}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="card">
          <div className="card-title">Backtest Results — {selectedStock}</div>

          {/* Summary metrics of best strategy */}
          {bestResult && (
            <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
              <div className="metric-card">
                <span className="metric-label">Best Strategy</span>
                <span className="metric-value highlight" style={{ fontSize: '1rem' }}>{bestResult.strategy}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Win Rate</span>
                <span className={`metric-value ${bestResult.metrics.winRate >= 50 ? 'positive' : 'negative'}`}>
                  {bestResult.metrics.winRate.toFixed(1)}%
                </span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Expectancy</span>
                <span className={`metric-value ${bestResult.metrics.expectancy >= 0 ? 'positive' : 'negative'}`}>
                  ₹{bestResult.metrics.expectancy.toFixed(2)}
                </span>
              </div>
            </div>
          )}

          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>TF</th>
                  <th>Win Rate</th>
                  <th>Total Trades</th>
                  <th>Max Drawdown</th>
                  <th>Expectancy</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {results.sort((a, b) => b.metrics.expectancy - a.metrics.expectancy).map(r => (
                  <tr key={r.strategy} className={r === bestResult ? 'signal-row-new' : ''}>
                    <td>
                      <span className="mono">{r.strategy}</span>
                      {r === bestResult && <span style={{ color: 'var(--yellow)', marginLeft: '0.5rem' }}>★</span>}
                    </td>
                    <td><span className="badge badge-active">{r.timeframe}</span></td>
                    <td>
                      <span style={{ color: r.metrics.winRate >= 50 ? 'var(--green)' : 'var(--red)', fontFamily: 'var(--font-mono)' }}>
                        {r.metrics.winRate.toFixed(1)}%
                      </span>
                    </td>
                    <td className="mono">{r.metrics.totalTrades}</td>
                    <td><span style={{ color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>{r.metrics.maxDrawdown.toFixed(2)}%</span></td>
                    <td>
                      <span style={{ color: r.metrics.expectancy >= 0 ? 'var(--green)' : 'var(--red)', fontFamily: 'var(--font-mono)' }}>
                        ₹{r.metrics.expectancy.toFixed(2)}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn btn-success btn-sm"
                        onClick={() => setActive(r.strategy, r.timeframe)}
                        disabled={settingActive}
                      >
                        Set Active ►
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {results.length === 0 && (
        <div className="card">
          <div className="empty-state">
            <span className="empty-icon">📊</span>
            <span className="empty-title">No backtest results yet</span>
            <span className="empty-subtitle">Select a stock, fetch history, then run a backtest</span>
          </div>
        </div>
      )}
    </div>
  );
}
