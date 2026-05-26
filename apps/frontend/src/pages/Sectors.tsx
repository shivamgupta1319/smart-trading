import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import { Brain, PieChart, TrendingUp, AlertTriangle } from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3000/api";

export function Sectors() {
  const [sectors, setSectors] = useState<string[]>([]);
  const [analysis, setAnalysis] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchData = async (force = false) => {
    if (!force) {
      const cachedSectors = localStorage.getItem('sectors_data');
      const cachedAnalysis = localStorage.getItem('sectors_analysis');
      if (cachedSectors && cachedAnalysis) {
        setSectors(JSON.parse(cachedSectors));
        setAnalysis(cachedAnalysis);
        setLoading(false);
        return;
      }
    }

    setLoading(true);
    try {
      const [sectorsRes, analysisRes] = await Promise.all([
        axios.get(`${API_URL}/nse-stocks/sectors/list`),
        axios.get(`${API_URL}/engine/analysis/sectors`),
      ]);

      setSectors(sectorsRes.data);
      localStorage.setItem('sectors_data', JSON.stringify(sectorsRes.data));

      if (analysisRes.data.status === "success") {
        setAnalysis(analysisRes.data.analysis);
        localStorage.setItem('sectors_analysis', analysisRes.data.analysis);
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
