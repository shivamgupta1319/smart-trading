import { Routes, Route, Navigate } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { Dashboard } from '../pages/Dashboard';
import { StockDetail } from '../pages/StockDetail';
import { LiveScanner } from '../pages/LiveScanner';
import '../styles/index.css';

export default function App() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/stock/:symbol" element={<StockDetail />} />
        <Route path="/scanner" element={<LiveScanner />} />
      </Routes>
    </>
  );
}
