import { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { AddStockModal } from '../components/AddStockModal';
import { API } from '../config';

interface Stock {
  id: number;
  symbol: string;
  isActive: boolean;
  intraday?: boolean; // on the intraday list
  sector?: string | null;
}

// Live prices are fetched only for the cards on screen, and never for more than this many:
// the price source answers a handful of quotes a second.
const MAX_PRICED = 80;

export function Dashboard() {
  const navigate = useNavigate();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [livePrices, setLivePrices] = useState<Record<string, number | null>>({});
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);

  const [marketAnalysis, setMarketAnalysis] = useState<string | null>(null);
  // With the NIFTY 500 loaded there are hundreds of stocks. The dashboard opens on the
  // ones in use: on the intraday list, or with a pair on the roster.
  const [view, setView] = useState<'inUse' | 'all'>('inUse');
  const [query, setQuery] = useState('');
  const [rosterSymbols, setRosterSymbols] = useState<Set<string>>(new Set());
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);

  const showMessage = (type: string, text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  };

  const fetchStocks = async () => {
    try {
      const r = await axios.get(`${API}/api/stocks`);
      setStocks(r.data);
      return r.data;
    } catch (e) {
      console.error(e);
      return [];
    }
  };

  const fetchLivePrices = async (stockList: Stock[]) => {
    if (stockList.length === 0) return;
    try {
      const symbols = stockList.map(s => s.symbol);
      const r = await axios.post(`${API}/api/engine/live-prices`, { symbols });
      setLivePrices(r.data);
    } catch (e) {
      console.error('Failed to fetch live prices', e);
    }
  };

  const fetchMarketAnalysis = async (force = false) => {
    if (!force) {
      const cached = localStorage.getItem('dashboard_market_analysis');
      if (cached) {
        setMarketAnalysis(cached);
        return;
      }
    }

    setLoadingAnalysis(true);
    try {
      const res = await axios.get(`${API}/api/engine/analysis/dashboard`);
      if (res.data.status === 'success') {
        setMarketAnalysis(res.data.analysis);
        localStorage.setItem('dashboard_market_analysis', res.data.analysis);
      } else {
        setMarketAnalysis(`> [!WARNING]\n> ${res.data.message}`);
      }
    } catch (e: any) {
      setMarketAnalysis('> [!WARNING]\n> The market analysis could not be loaded. Check your connection, then press Refresh Analysis.');
    } finally {
      setLoadingAnalysis(false);
    }
  };

  const inUse = useMemo(
    () => stocks.filter((s) => s.intraday || rosterSymbols.has(s.symbol)),
    [stocks, rosterSymbols],
  );
  const shown = useMemo(() => {
    const q = query.trim().toUpperCase();
    const base = view === 'inUse' ? inUse : stocks;
    return q ? base.filter((s) => s.symbol.includes(q) || (s.sector ?? '').toUpperCase().includes(q)) : base;
  }, [view, query, inUse, stocks]);
  const priced = shown.length <= MAX_PRICED;
  // The 30-second refresh must price whatever is on screen at that moment.
  const shownRef = useRef<Stock[]>([]);
  shownRef.current = priced ? shown : [];

  useEffect(() => {
    fetchMarketAnalysis();
    fetchStocks();
    axios
      .get(`${API}/api/configs`)
      .then((r) => setRosterSymbols(new Set((r.data || []).map((c: any) => c.stock?.symbol ?? c.symbol).filter(Boolean))))
      .catch(() => setRosterSymbols(new Set()));

    const intervalId = setInterval(async () => {
      await fetchStocks();
      fetchLivePrices(shownRef.current);
    }, 30000);

    return () => clearInterval(intervalId);
  }, []);

  // Price the cards on screen whenever the list on screen changes.
  const shownKey = priced ? shown.map((s) => s.symbol).join(',') : '';
  useEffect(() => {
    if (shownKey) fetchLivePrices(shownRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the symbols shown
  }, [shownKey]);

  const handleAddStock = async (symbol: string) => {
    try {
      await axios.post(`${API}/api/stocks`, { symbol });
      setIsModalOpen(false);
      showMessage('success', `✓ ${symbol} added successfully`);
      await fetchStocks();
      setView('all');
      setQuery(symbol.toUpperCase());
    } catch (e: any) {
      showMessage('error', e.response?.data?.message || 'Failed to add stock');
    }
  };

  const removeStock = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    try {
      await axios.delete(`${API}/api/stocks/${id}`);
      showMessage('success', 'Stock removed');
      fetchStocks();
    } catch (e) {
      showMessage('error', 'Failed to remove stock');
    }
  };

  const toggleStockActive = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    try {
      await axios.post(`${API}/api/stocks/${id}/toggle-active`);
      fetchStocks();
    } catch (e) {
      showMessage('error', 'Failed to toggle stock status');
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

      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 className="page-title">Trading <span>Dashboard</span></h1>
          <p className="page-subtitle">Monitor live prices and manage your portfolio</p>
        </div>
        <button 
          onClick={() => setIsModalOpen(true)}
          className="btn btn-primary"
        >
          <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
          <span>Add Stock</span>
        </button>
      </div>

      <div className="card" style={{ marginBottom: '2rem', padding: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h2 className="card-title" style={{ margin: 0, fontSize: '1.2rem', color: 'var(--cyan)' }}>AI Market Intelligence</h2>
            <span className="badge badge-active" style={{ fontSize: '0.7rem' }}>Nifty 50</span>
          </div>
          <button 
            onClick={() => fetchMarketAnalysis(true)} 
            disabled={loadingAnalysis}
            className="btn btn-secondary btn-sm"
          >
            {loadingAnalysis ? 'Refreshing...' : 'Refresh Analysis'}
          </button>
        </div>
        
        {loadingAnalysis ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '1rem 0' }}>
            <div className="spinner"></div>
            <p className="page-subtitle" style={{ margin: 0 }}>Analyzing Indian Stock Market sentiment...</p>
          </div>
        ) : (
          <div className="markdown-body" style={{ lineHeight: '1.6', color: 'var(--text-primary)', fontSize: '0.95rem' }}>
            {marketAnalysis ? (
              <ReactMarkdown>{marketAnalysis}</ReactMarkdown>
            ) : (
              <p>No analysis data available.</p>
            )}
          </div>
        )}
      </div>

      <div className="sc-toolbar">
        <div className="sc-filters" role="group" aria-label="Which stocks to show">
          <button className={`sc-chip ${view === 'inUse' ? 'on' : ''}`} aria-pressed={view === 'inUse'} onClick={() => setView('inUse')}>
            In use <span className="sc-chip-count mono">{inUse.length}</span>
          </button>
          <button className={`sc-chip ${view === 'all' ? 'on' : ''}`} aria-pressed={view === 'all'} onClick={() => setView('all')}>
            All stocks <span className="sc-chip-count mono">{stocks.length}</span>
          </button>
        </div>
        <label className="sc-field">
          <span className="sc-field-label">Find a stock or sector</span>
          <input
            className="form-input"
            style={{ minHeight: 44, fontSize: '1rem', minWidth: '12rem' }}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. TATA or Banking"
          />
        </label>
      </div>
      <p className="page-subtitle" style={{ marginTop: 0, marginBottom: '1rem' }}>
        {view === 'inUse'
          ? 'Stocks on the intraday list or with a pair on the roster.'
          : 'Every stock being tested. Daily candles for all; intraday candles for the intraday list.'}
        {!priced && ` Live prices are shown for up to ${MAX_PRICED} stocks at a time: search to narrow the list.`}
      </p>

      {shown.length === 0 && (
        <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>
          <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
            {stocks.length === 0
              ? 'No stocks yet. Add one to start.'
              : query
                ? `No stock matches "${query}" in this view.`
                : 'No stock is in use yet. Open "All stocks" to see everything being tested.'}
          </p>
        </div>
      )}

      <div className="grid-3">
        {shown.map(stock => {
          const priceData = livePrices[stock.symbol];
          const price = priceData ? (typeof priceData === 'object' ? (priceData as any).price : priceData) : priceData;
          return (
            <div 
              key={stock.id} 
              onClick={() => navigate(`/stock/${stock.symbol}`)}
              className="card stock-card"
              style={{ cursor: 'pointer' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <h3 className="stock-card-title">{stock.symbol}</h3>
                  <div className="market-status" style={{ marginLeft: 0, alignSelf: 'flex-start' }}>
                    <span className={`market-dot ${stock.isActive ? 'open' : 'closed'}`} style={{ backgroundColor: stock.isActive ? 'var(--green)' : 'var(--red)' }}></span>
                    <span style={{ color: stock.isActive ? 'var(--green)' : 'var(--text-muted)' }}>{stock.isActive ? 'Live' : 'Paused'}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button 
                    onClick={(e) => toggleStockActive(e, stock.id)}
                    className="btn-close"
                    style={{ background: 'transparent', border: '1px solid var(--border-light)', padding: '0.25rem', borderRadius: '4px', color: 'var(--text-muted)' }}
                    title={stock.isActive ? 'Deactivate Stock' : 'Activate Stock'}
                  >
                    {stock.isActive ? (
                      <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    ) : (
                      <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    )}
                  </button>
                  <button 
                    onClick={(e) => removeStock(e, stock.id)}
                    className="btn-close stock-card-remove"
                    title="Remove stock"
                  >
                    <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </button>
                </div>
              </div>

              <div style={{ marginTop: '1.5rem' }}>
                <p className="metric-label">Current Price</p>
                {price === undefined ? (
                  <div className="skeleton-loader" style={{ height: '40px', width: '120px', borderRadius: '8px', marginTop: '4px' }}></div>
                ) : price === null ? (
                  <span className="metric-value">Unavailable</span>
                ) : (
                  <div className="metric-value highlight" style={{ fontSize: '2rem' }}>
                    ₹{Number(price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {stocks.length === 0 && (
          <div className="empty-state" style={{ gridColumn: '1 / -1', border: '2px dashed var(--border)', borderRadius: 'var(--radius-lg)' }}>
            <div className="empty-icon">📈</div>
            <h3 className="empty-title">No stocks added</h3>
            <p className="empty-subtitle">Add a stock to start tracking its live price and run backtests.</p>
          </div>
        )}
      </div>

      <AddStockModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onAdd={handleAddStock} 
      />
    </div>
  );
}
