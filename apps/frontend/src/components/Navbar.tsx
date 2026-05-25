import { NavLink } from "react-router-dom";

function isMarketOpen() {
  const now = new Date();
  const ist = new Date(
    now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }),
  );
  const h = ist.getHours(),
    m = ist.getMinutes();
  const day = ist.getDay();
  const minutes = h * 60 + m;
  return day >= 1 && day <= 5 && minutes >= 555 && minutes <= 930; // 09:15–15:30
}

export function Navbar() {
  const open = isMarketOpen();

  return (
    <nav className="navbar">
      <NavLink to="/" className="navbar-brand">
        <span className="brand-icon">⚡</span>
        <span>SmartTrader</span>
      </NavLink>

      <div className="navbar-links">
        <NavLink
          to="/dashboard"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          📊 Dashboard
        </NavLink>
        <NavLink
          to="/scanner"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          📡 Live Scanner
        </NavLink>
        <NavLink
          to="/news"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          📰 Market News
        </NavLink>
        <NavLink
          to="/sectors"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          🗂️ Sector Analysis
        </NavLink>
        <div className="market-status">
          <span className={`market-dot ${open ? "open" : ""}`}></span>
          <span>{open ? "MARKET OPEN" : "MARKET CLOSED"}</span>
        </div>
      </div>
    </nav>
  );
}
