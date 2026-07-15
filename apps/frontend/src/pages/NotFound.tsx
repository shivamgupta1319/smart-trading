import { Link } from 'react-router-dom';

export function NotFound() {
  return (
    <div className="page" style={{ textAlign: 'center', paddingTop: '6rem' }}>
      <div style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>🧭</div>
      <h1 className="page-title">404 — Page not found</h1>
      <p className="page-subtitle">That route doesn't exist.</p>
      <Link to="/dashboard" className="btn btn-primary" style={{ marginTop: '1rem', display: 'inline-block' }}>
        Back to Dashboard
      </Link>
    </div>
  );
}
