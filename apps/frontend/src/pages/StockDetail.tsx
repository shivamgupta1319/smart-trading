import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';

const API = 'http://localhost:3000';

interface BacktestResult {
  strategy: string;
  timeframe: string;
  metrics: {
    winRate: number;
    totalTrades: number;
    maxDrawdown: number;
    netProfit: number;
    roiPercentage: number;
  };
}

export function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [running, setRunning] = useState(false);
  const [activeStrategies, setActiveStrategies] = useState<string[]>([]);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);
  
  const [activeTab, setActiveTab] = useState<'backtest' | 'research'>('backtest');
  const [researchData, setResearchData] = useState<string | null>(null);
  const [loadingResearch, setLoadingResearch] = useState(false);

  const showMessage = (type: string, text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  useEffect(() => {
    if (symbol) {
      axios.get(`${API}/api/configs/${symbol}`).then(res => {
        setActiveStrategies(res.data.map((c: any) => c.strategyName));
      }).catch(err => console.error("Failed to load active strategies:", err));
    }
  }, [symbol]);

  const fetchResearch = async () => {
    if (!symbol || researchData) return;
    setLoadingResearch(true);
    try {
      const res = await axios.get(`${API}/api/engine/analysis/stock/${symbol}`);
      if (res.data.status === 'success') {
        setResearchData(res.data.analysis);
      } else {
        setResearchData(`> [!WARNING]\n> Failed to fetch analysis: ${res.data.message}`);
      }
    } catch (e: any) {
      setResearchData(`> [!WARNING]\n> Failed to fetch analysis: ${e.message}`);
    } finally {
      setLoadingResearch(false);
    }
  };

  const handleTabChange = (tab: 'backtest' | 'research') => {
    setActiveTab(tab);
    if (tab === 'research') fetchResearch();
  };

  const runFullBacktest = async () => {
    if (!symbol) return;
    setRunning(true);
    try {
      // First fetch history
      await axios.post(`${API}/api/engine/fetch-history`, { symbol });
      showMessage('success', `History fetched. Running strategies...`);
      
      // Then run all strategies
      const r = await axios.post(`${API}/api/engine/run-all-strategies`, { symbol });
      setResults(r.data.results || []);
      showMessage('success', `✓ Backtest complete across all strategies`);
    } catch (e: any) {
      showMessage('error', e.response?.data?.message || 'Backtest failed.');
    } finally {
      setRunning(false);
    }
  };

  const handleSetLive = async (strategy: string, timeframe: string) => {
    try {
      const res = await axios.post(`${API}/api/configs/toggle`, { symbol, strategyName: strategy, timeframe });
      if (res.data.status === 'added') {
        setActiveStrategies(prev => [...prev, strategy]);
        showMessage('success', `${strategy} is now set for Live Signals!`);
      } else {
        setActiveStrategies(prev => prev.filter(s => s !== strategy));
        showMessage('success', `${strategy} is removed from Live Signals!`);
      }
    } catch (e: any) {
      showMessage('error', e.response?.data?.message || 'Failed to toggle live strategy.');
    }
  };

  return (
    <div className="page animate-fade-in">
      {message && (
        <div className={`toast-container`}>
          <div className={`toast ${message.type}`}>
             <div className="toast-header"><span className="toast-title">{message.text}</span></div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
        <button 
          onClick={() => navigate('/dashboard')}
          className="btn btn-secondary"
          style={{ padding: '0.5rem', borderRadius: 'var(--radius-md)' }}
        >
          <svg width="24" height="24" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
        </button>
        <div>
          <h1 className="page-title">{symbol}</h1>
          <p className="page-subtitle">Stock Details & Analysis</p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', borderBottom: '1px solid var(--border)' }}>
        <button 
          className={`btn ${activeTab === 'backtest' ? 'btn-primary' : 'btn-secondary'}`}
          style={{ borderRadius: 'var(--radius-md) var(--radius-md) 0 0', borderBottom: 'none' }}
          onClick={() => handleTabChange('backtest')}
        >
          Backtesting Engine
        </button>
        <button 
          className={`btn ${activeTab === 'research' ? 'btn-primary' : 'btn-secondary'}`}
          style={{ borderRadius: 'var(--radius-md) var(--radius-md) 0 0', borderBottom: 'none' }}
          onClick={() => handleTabChange('research')}
        >
          AI Research & Analysis
        </button>
      </div>

      {activeTab === 'backtest' && (
        <>
          <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1.5rem', padding: '3rem 2rem', textAlign: 'center' }}>
        <div style={{ maxWidth: '600px' }}>
          <h2 className="page-title" style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>Run Full Backtest</h2>
          <p className="page-subtitle" style={{ marginBottom: '1.5rem' }}>
            Clicking the button below will automatically fetch the latest historical data for {symbol} and run all available trading strategies using a fixed <strong style={{ color: 'var(--text-primary)' }}>₹1,00,000 capital baseline</strong>.
          </p>
          <button 
            onClick={runFullBacktest}
            disabled={running}
            className="btn btn-primary"
            style={{ padding: '1rem 2rem', fontSize: '1.1rem', borderRadius: 'var(--radius-md)' }}
          >
            {running ? (
              <>
                <div className="spinner"></div>
                <span>Processing...</span>
              </>
            ) : (
              <>
                <svg width="24" height="24" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <span>Run Full Backtest</span>
              </>
            )}
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <div className="animate-fade-in-up" style={{ marginTop: '2rem' }}>
          <h2 className="page-title" style={{ fontSize: '1.5rem', marginBottom: '1.5rem' }}>Strategy Results</h2>
          <div className="grid-3">
            {results.map((r, i) => (
              <div key={i} className="card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                    <h3 className="card-title" style={{ color: 'var(--cyan)', margin: 0 }}>{r.strategy}</h3>
                    <span className="badge badge-active">{r.timeframe}</span>
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.5rem' }}>
                    <div className="grid-2">
                      <div className="metric-card" style={{ background: 'var(--bg-input)' }}>
                        <p className="metric-label">Net Profit</p>
                        <p className={`metric-value ${r.metrics.netProfit >= 0 ? 'positive' : 'negative'}`}>
                          {r.metrics.netProfit >= 0 ? '+' : ''}₹{r.metrics.netProfit.toLocaleString('en-IN')}
                        </p>
                      </div>
                      <div className="metric-card" style={{ background: 'var(--bg-input)' }}>
                        <p className="metric-label">ROI</p>
                        <p className={`metric-value ${r.metrics.roiPercentage >= 0 ? 'positive' : 'negative'}`}>
                          {r.metrics.roiPercentage >= 0 ? '+' : ''}{r.metrics.roiPercentage}%
                        </p>
                      </div>
                    </div>
                    
                    <div className="grid-3" style={{ paddingTop: '0.5rem' }}>
                      <div>
                        <p className="metric-label">Win Rate</p>
                        <p className="metric-value" style={{ fontSize: '1.1rem' }}>{r.metrics.winRate}%</p>
                      </div>
                      <div>
                        <p className="metric-label">Trades</p>
                        <p className="metric-value" style={{ fontSize: '1.1rem' }}>{r.metrics.totalTrades}</p>
                      </div>
                      <div>
                        <p className="metric-label">Max DD</p>
                        <p className="metric-value negative" style={{ fontSize: '1.1rem' }}>-₹{r.metrics.maxDrawdown.toLocaleString('en-IN')}</p>
                      </div>
                    </div>
                  </div>
                </div>
                <button 
                  className={`btn ${activeStrategies.includes(r.strategy) ? 'btn-primary' : 'btn-secondary'}`} 
                  style={{ width: '100%' }}
                  onClick={() => handleSetLive(r.strategy, r.timeframe)}
                >
                  <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    {activeStrategies.includes(r.strategy) ? (
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    ) : (
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    )}
                  </svg>
                  <span>{activeStrategies.includes(r.strategy) ? 'Live (Click to Remove)' : 'Set as Live Strategy'}</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      </>
      )}

      {activeTab === 'research' && (
        <div className="card animate-fade-in-up" style={{ padding: '2rem' }}>
          {loadingResearch ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem', padding: '3rem' }}>
              <div className="spinner"></div>
              <p className="page-subtitle">AI is analyzing fundamental, technical, and sentimental data...</p>
            </div>
          ) : (
            <div className="markdown-body" style={{ lineHeight: '1.6', color: 'var(--text-primary)' }}>
              {researchData ? (
                <ReactMarkdown>{researchData}</ReactMarkdown>
              ) : (
                <p>No research data available.</p>
              )}
            </div>
          )}
        </div>
      )}

    </div>
  );
}
