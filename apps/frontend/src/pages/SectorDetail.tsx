import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  Brain,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3000/api";

interface StockData {
  id: number;
  symbol: string;
  companyName: string;
  price?: number;
  change?: number;
  changePct?: number;
}

export function SectorDetail() {
  const { sectorName } = useParams<{ sectorName: string }>();
  const navigate = useNavigate();
  const [stocks, setStocks] = useState<StockData[]>([]);
  const [loading, setLoading] = useState(true);
  const [analysis, setAnalysis] = useState<string>("");
  const [analyzing, setAnalyzing] = useState(false);
  const [sortOrder, setSortOrder] = useState<
    "gainers" | "losers" | "alphabetical"
  >("alphabetical");

  useEffect(() => {
    const fetchSectorStocks = async () => {
      try {
        const response = await axios.get(
          `${API_URL}/nse-stocks/sectors/${sectorName}`,
        );
        const stockList: StockData[] = response.data;

        // Optimistically set the list
        setStocks(stockList);

        // Fetch live prices for these stocks
        const symbols = stockList.map((s) => s.symbol).slice(0, 50); // Limit to 50 for performance
        if (symbols.length > 0) {
          try {
            const liveRes = await axios.post(`${API_URL}/engine/live-prices`, {
              symbols,
            });
            const liveData = liveRes.data;

            setStocks((prev) =>
              prev.map((stock) => {
                const live = liveData[stock.symbol];
                if (live) {
                  return {
                    ...stock,
                    price: live.price,
                    change: live.change,
                    changePct: live.change_pct,
                  };
                }
                return stock;
              }),
            );
          } catch (e) {
            console.error("Failed to fetch live prices", e);
          }
        }
      } catch (error) {
        console.error("Error fetching sector stocks:", error);
      } finally {
        setLoading(false);
      }
    };

    if (sectorName) {
      fetchSectorStocks();
    }
  }, [sectorName]);

  const requestAnalysis = async () => {
    setAnalyzing(true);
    try {
      const symbols = stocks.map((s) => s.symbol).slice(0, 20); // Top 20 stocks
      const res = await axios.post(
        `${API_URL}/engine/analysis/sectors/analyze-list`,
        {
          sector_name: sectorName,
          stocks: symbols,
        },
      );
      if (res.data.status === "success") {
        setAnalysis(res.data.analysis);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setAnalyzing(false);
    }
  };

  const sortedStocks = [...stocks].sort((a, b) => {
    if (sortOrder === "gainers") {
      return (b.changePct || 0) - (a.changePct || 0);
    } else if (sortOrder === "losers") {
      return (a.changePct || 0) - (b.changePct || 0);
    } else {
      return a.symbol.localeCompare(b.symbol);
    }
  });

  if (loading) {
    return (
      <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
           <div className="spinner" style={{ width: '32px', height: '32px' }}></div>
           <p className="page-subtitle">Loading sector data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page animate-fade-in">
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
        <button
          onClick={() => navigate("/sectors")}
          className="btn btn-secondary"
          style={{ padding: '0.5rem', borderRadius: 'var(--radius-md)' }}
        >
          <ArrowLeft size={24} />
        </button>
        <div>
          <h1 className="page-title">
            {sectorName}
          </h1>
          <p className="page-subtitle">
            Showing {stocks.length} stocks in this sector.
          </p>
        </div>
      </div>

      <div className="grid-3" style={{ gridTemplateColumns: '1fr 2fr' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="card" style={{ position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', top: 0, right: 0, padding: '1rem', opacity: 0.1 }}>
              <Brain size={80} color="var(--cyan)" />
            </div>
            <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', fontSize: '1rem', color: 'var(--text-primary)', marginBottom: '1rem', textTransform: 'none', letterSpacing: 'normal' }}>
              <Brain size={20} color="var(--cyan)" style={{ marginRight: '0.5rem' }} />
              Sector Insight
            </h2>

            {!analysis ? (
              <div style={{ textAlign: 'center', padding: '1.5rem 0' }}>
                <button
                  onClick={requestAnalysis}
                  disabled={analyzing}
                  className="btn btn-primary"
                  style={{ width: '100%' }}
                >
                  {analyzing ? (
                    <>
                      <div className="spinner"></div>
                      <span>Analyzing...</span>
                    </>
                  ) : (
                    "Generate AI Insight"
                  )}
                </button>
                <p className="page-subtitle" style={{ fontSize: '0.8rem', marginTop: '1rem' }}>
                  Powered by advanced LLM quantitative analysis.
                </p>
              </div>
            ) : (
              <div className="markdown-body" style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                <ReactMarkdown>{analysis}</ReactMarkdown>
              </div>
            )}
          </div>

          <div className="card">
            <h3 className="card-title" style={{ marginBottom: '1rem' }}>Filters</h3>
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as any)}
              className="form-select"
            >
              <option value="alphabetical">Alphabetical</option>
              <option value="gainers">Top Gainers</option>
              <option value="losers">Top Losers</option>
            </select>
          </div>
        </div>

        <div>
          <div className="grid-2">
            {sortedStocks.map((stock, index) => {
              const isPositive = (stock.changePct || 0) >= 0;
              return (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{
                    duration: 0.2,
                    delay: Math.min(index * 0.02, 0.5),
                  }}
                  key={stock.id}
                  onClick={() => navigate(`/stock/${stock.symbol}`)}
                  className="card"
                  style={{ cursor: 'pointer', padding: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                >
                  <div style={{ overflow: 'hidden' }}>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                      {stock.symbol}
                    </h3>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '200px' }}>
                      {stock.companyName}
                    </p>
                  </div>
                  {stock.price !== undefined ? (
                    <div style={{ textAlign: 'right' }}>
                      <p style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                        ₹{stock.price.toFixed(2)}
                      </p>
                      <div
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', fontSize: '0.8rem', fontWeight: 600, color: isPositive ? 'var(--green)' : 'var(--red)' }}
                      >
                        {isPositive ? (
                          <ArrowUpRight size={14} style={{ marginRight: '0.2rem' }} />
                        ) : (
                          <ArrowDownRight size={14} style={{ marginRight: '0.2rem' }} />
                        )}
                        {Math.abs(stock.changePct!).toFixed(2)}%
                      </div>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'right', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      <Activity size={16} style={{ display: 'inline', marginRight: '0.2rem', opacity: 0.5 }} />{" "}
                      Pending
                    </div>
                  )}
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
