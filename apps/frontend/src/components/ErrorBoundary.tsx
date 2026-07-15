import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/** Catches render errors so one broken page doesn't blank the whole app. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error('UI error boundary caught:', error);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>
          <div className="card" style={{ maxWidth: 480, padding: '2rem', textAlign: 'center' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>💥</div>
            <h2 className="page-title" style={{ fontSize: '1.4rem' }}>Something went wrong</h2>
            <p className="page-subtitle">{this.state.error.message}</p>
            <button className="btn btn-primary" onClick={() => location.reload()} style={{ marginTop: '1rem' }}>
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
