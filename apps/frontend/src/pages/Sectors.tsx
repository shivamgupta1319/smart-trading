import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import { Brain, PieChart, TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import { API_URL } from "../config";

interface SectorPerf {
  name: string;
  ticker: string;
  changePct: number;
  status: "Up" | "Down" | "Neutral";
}

const perfColor = (v: number) => (v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-muted)");

export function Sectors() {
  const [sectors, setSectors] = useState<string[]>([]);
  const [sectorPerf, setSectorPerf] = useState<SectorPerf[]>([]);
  const [leading, setLeading] = useState<SectorPerf[]>([]);
  const [lagging, setLagging] = useState<SectorPerf[]>([]);
  const [analysis, setAnalysis] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchData = async (force = false) => {
    if (!force) {
      const cachedSectors = localStorage.getItem('sectors_data');
      if (cachedSectors) setSectors(JSON.parse(cachedSectors));
    }

    setLoading(true);
    try {
      // Sector-index performance is time-sensitive — always fetch it live. The GICS
      // sector list (used for drill-down) can come from cache.
      const [sectorsRes, analysisRes] = await Promise.all([
        axios.get(`${API_URL}/nse-stocks/sectors/list`),
        axios.get(`${API_URL}/engine/analysis/sectors`),
      ]);

      setSectors(sectorsRes.data);
      localStorage.setItem('sectors_data', JSON.stringify(sectorsRes.data));

      if (analysisRes.data.status === "success") {
        setAnalysis(analysisRes.data.analysis || "");
        setSectorPerf(analysisRes.data.data || []);
        setLeading(analysisRes.data.leading || []);
        setLagging(analysisRes.data.lagging || []);
      }
    } catch (error) {
      console.error("Error fetching sector data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
           <div className="spinner" style={{ width: '32px', height: '32px' }}></div>
           <p className="page-subtitle">Loading sector intelligence...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page animate-fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h1 className="page-title">Sector Analysis</h1>
          <p className="page-subtitle">Discover market performance grouped by industry sectors.</p>
        </div>
        <button
          onClick={() => fetchData(true)}
          disabled={loading}
          className="btn btn-secondary"
        >
          {loading ? 'Refreshing...' : 'Refresh Data'}
        </button>
      </div>

      {/* Real sector-index performance today (NSE sectoral indices) */}
      {sectorPerf.length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
            <h2 className="card-title" style={{ margin: 0, fontSize: '1rem', textTransform: 'none', letterSpacing: 'normal' }}>
              📊 Sector Performance Today
            </h2>
            <div style={{ display: 'flex', gap: '1rem', fontSize: '0.8rem' }}>
              {leading[0] && (
                <span style={{ color: 'var(--green)' }}>▲ Leading: <strong>{leading[0].name}</strong> {leading[0].changePct >= 0 ? '+' : ''}{leading[0].changePct}%</span>
              )}
              {lagging[0] && (
                <span style={{ color: 'var(--red)' }}>▼ Lagging: <strong>{lagging[0].name}</strong> {lagging[0].changePct}%</span>
              )}
            </div>
          </div>
          <div className="grid-4" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '0.75rem' }}>
            {[...sectorPerf].sort((a, b) => b.changePct - a.changePct).map((s) => (
              <div key={s.ticker} className="card" style={{ padding: '0.85rem', borderLeft: `3px solid ${perfColor(s.changePct)}`, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>{s.name}</span>
                  {s.changePct >= 0 ? <TrendingUp size={16} color="var(--green)" /> : <TrendingDown size={16} color="var(--red)" />}
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1.15rem', fontWeight: 700, color: perfColor(s.changePct) }}>
                  {s.changePct >= 0 ? '+' : ''}{s.changePct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid-3" style={{ gridTemplateColumns: '1fr 2fr' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="card" style={{ position: 'relative', overflow: 'hidden' }}>
             <div style={{ position: 'absolute', top: 0, right: 0, padding: '1rem', opacity: 0.1 }}>
                <Brain size={80} color="var(--cyan)" />
             </div>
             <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', fontSize: '1rem', color: 'var(--text-primary)', marginBottom: '1rem', textTransform: 'none', letterSpacing: 'normal' }}>
                <Brain size={20} color="var(--cyan)" style={{ marginRight: '0.5rem' }} />
                AI Market Intelligence
             </h2>
             <div className="markdown-body" style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                {analysis ? (
                   <ReactMarkdown>{analysis}</ReactMarkdown>
                ) : (
                   <div style={{ display: 'flex', alignItems: 'center', color: 'var(--yellow)' }}>
                      <AlertTriangle size={16} style={{ marginRight: '0.5rem' }} />
                      AI Analysis currently unavailable.
                   </div>
                )}
             </div>
          </div>
        </div>

        <div>
          <div className="grid-2">
            {sectors.map((sector, index) => (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: index * 0.05 }}
                key={sector}
                onClick={() => navigate(`/sectors/${encodeURIComponent(sector)}`)}
                className="card"
                style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                  <div style={{ background: 'var(--bg-input)', padding: '0.75rem', borderRadius: 'var(--radius-sm)', color: 'var(--text-muted)' }}>
                    <PieChart size={24} />
                  </div>
                  <TrendingUp size={20} color="var(--text-muted)" style={{ opacity: 0.5 }} />
                </div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {sector}
                </h3>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
