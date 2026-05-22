import { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://localhost:3000';

interface NseStock {
  id: number;
  symbol: string;
  companyName: string;
}

export function AddStockModal({ isOpen, onClose, onAdd }: { isOpen: boolean; onClose: () => void; onAdd: (symbol: string) => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<NseStock[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      setResults([]);
    }
  }, [isOpen]);

  useEffect(() => {
    const fetchStocks = async () => {
      setLoading(true);
      try {
        const res = await axios.get(`${API}/api/nse-stocks`, { params: { q: query } });
        setResults(res.data);
      } catch (e) {
        console.error("Failed to fetch NSE stocks", e);
      } finally {
        setLoading(false);
      }
    };
    
    const timeoutId = setTimeout(fetchStocks, 300);
    return () => clearTimeout(timeoutId);
  }, [query]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="modal-content card">
        <div className="modal-header">
          <h2 className="page-title" style={{ fontSize: '1.25rem' }}>Add NSE Stock</h2>
          <button onClick={onClose} className="btn-close">
            <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        
        <div className="modal-body p-4">
          <input
            type="text"
            placeholder="Search symbol or company name..."
            className="form-input mb-4"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          
          <div className="stock-results custom-scrollbar">
            {loading ? (
              <div className="empty-state"><div className="spinner"></div></div>
            ) : results.length === 0 ? (
              <div className="empty-state"><p className="empty-subtitle">No stocks found.</p></div>
            ) : (
              <div className="stock-list">
                {results.map((stock) => (
                  <div 
                    key={stock.id} 
                    className="stock-list-item"
                    onClick={() => onAdd(stock.symbol)}
                  >
                    <div>
                      <div className="stock-symbol">{stock.symbol}</div>
                      <div className="stock-company">{stock.companyName}</div>
                    </div>
                    <button className="btn btn-sm btn-primary">
                      Add
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
