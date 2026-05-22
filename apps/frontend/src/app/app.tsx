import { Routes, Route, Navigate } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { BacktestArena } from '../pages/BacktestArena';
import { LiveScanner } from '../pages/LiveScanner';
import '../styles/index.css';

export default function App() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<Navigate to="/backtest" replace />} />
        <Route path="/backtest" element={<BacktestArena />} />
        <Route path="/scanner" element={<LiveScanner />} />
      </Routes>
    </>
  );
}
