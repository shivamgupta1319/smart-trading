import { Routes, Route, Navigate } from "react-router-dom";
import { Navbar } from "../components/Navbar";
import { Dashboard } from "../pages/Dashboard";
import { StockDetail } from "../pages/StockDetail";
import { LiveScanner } from "../pages/LiveScanner";
import { MarketNews } from "../pages/MarketNews";
import { Sectors } from "../pages/Sectors";
import { SectorDetail } from "../pages/SectorDetail";
import { Portfolio } from "../pages/Portfolio";
import { Backtesting } from "../pages/Backtesting";
import { BacktestingStrategy } from "../pages/BacktestingStrategy";
import "../styles/index.css";

export default function App() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/stock/:symbol" element={<StockDetail />} />
        <Route path="/scanner" element={<LiveScanner />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/news" element={<MarketNews />} />
        <Route path="/sectors" element={<Sectors />} />
        <Route path="/sectors/:sectorName" element={<SectorDetail />} />
        <Route path="/backtesting" element={<Backtesting />} />
        <Route
          path="/backtesting/:strategyName"
          element={<BacktestingStrategy />}
        />
      </Routes>
    </>
  );
}
