import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { AddStockModal } from '../components/AddStockModal';

const API = 'http://localhost:3000';

interface Stock {
  id: number;
  symbol: string;
  isActive: boolean;
}

export function Dashboard() {
  const navigate = useNavigate();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [livePrices, setLivePrices] = useState<Record<string, number | null>>({});
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [message, setMessage] = useState<{ type: string; text: string } | null>(null);

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

  useEffect(() => {
    fetchStocks().then(fetchLivePrices);

    const intervalId = setInterval(async () => {
      const currentStocks = await fetchStocks();
      fetchLivePrices(currentStocks);
    }, 30000);

    return () => clearInterval(intervalId);
  }, []);

  const handleAddStock = async (symbol: string) => {
    try {
      await axios.post(`${API}/api/stocks`, { symbol });
      setIsModalOpen(false);
      showMessage('success', `✓ ${symbol} added successfully`);
      const updated = await fetchStocks();
      fetchLivePrices(updated);
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

      <div className="grid-3">
        {stocks.map(stock => {
          const price = livePrices[stock.symbol];
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
                    <span className="market-dot open"></span>
                    <span>Live</span>
                  </div>
                </div>
                <button 
                  onClick={(e) => removeStock(e, stock.id)}
                  className="btn-close stock-card-remove"
                  title="Remove stock"
                >
                  <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
              </div>

              <div style={{ marginTop: '1.5rem' }}>
                <p className="metric-label">Current Price</p>
                {price === undefined ? (
                  <div className="skeleton-loader" style={{ height: '40px', width: '120px', borderRadius: '8px', marginTop: '4px' }}></div>
                ) : price === null ? (
                  <span className="metric-value">Unavailable</span>
                ) : (
                  <div className="metric-value highlight" style={{ fontSize: '2rem' }}>
                    ₹{price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
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
