import { useState, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';

const API = 'http://localhost:3000';

interface NewsArticle {
  title: string;
  publisher: string;
  link: string;
  providerPublishTime: number;
}

export function MarketNews() {
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchNews = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await axios.get(`${API}/api/engine/analysis/news`);
        if (res.data.status === 'success') {
          setAnalysis(res.data.analysis);
          setArticles(res.data.articles || []);
        } else {
          setError(res.data.message || 'Failed to fetch news analysis.');
        }
      } catch (err: any) {
        setError(err.message || 'An error occurred while fetching news.');
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
  }, []);

  return (
    <div className="page animate-fade-in">
      <div className="page-header">
        <h1 className="page-title">Indian Market <span>News</span></h1>
        <p className="page-subtitle">AI-driven analysis of breaking news affecting Nifty 50 and Sensex</p>
      </div>

      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem', padding: '5rem' }}>
          <div className="spinner"></div>
          <p className="page-subtitle">Fetching latest headlines and generating AI impact analysis...</p>
        </div>
      ) : error ? (
        <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--negative)' }}>
          <p>⚠️ {error}</p>
        </div>
      ) : (
        <>
          {analysis && (
            <div className="card animate-fade-in-up" style={{ marginBottom: '2rem', padding: '2rem', borderTop: '4px solid var(--cyan)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
                <h2 className="card-title" style={{ margin: 0, fontSize: '1.5rem', color: 'var(--cyan)' }}>AI Sentiment Summary</h2>
                <span className="badge badge-active">Live</span>
              </div>
              <div className="markdown-body" style={{ lineHeight: '1.7', color: 'var(--text-primary)', fontSize: '1.05rem' }}>
                <ReactMarkdown>{analysis}</ReactMarkdown>
              </div>
            </div>
          )}

          {articles.length > 0 && (
            <div className="animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
              <h2 className="page-title" style={{ fontSize: '1.3rem', marginBottom: '1rem' }}>Latest Headlines</h2>
              <div className="grid-2">
                {articles.map((article, idx) => (
                  <a 
                    key={idx} 
                    href={article.link} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="card stock-card"
                    style={{ textDecoration: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}
                  >
                    <h3 className="stock-card-title" style={{ fontSize: '1.1rem', lineHeight: '1.4' }}>{article.title}</h3>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto', paddingTop: '1rem' }}>
                      <span className="badge" style={{ background: 'var(--bg-input)', color: 'var(--text-secondary)' }}>
                        {article.publisher}
                      </span>
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        {new Date(article.providerPublishTime * 1000).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                      </span>
                    </div>
                  </a>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
