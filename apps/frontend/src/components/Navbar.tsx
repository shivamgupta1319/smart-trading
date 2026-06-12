import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { NavLink } from "react-router-dom";
import axios from "axios";
import { API } from "../config";

const REGIME_UI: Record<
  string,
  { label: string; color: string; blurb: string }
> = {
  TRENDING_UP: {
    label: "📈 Trend Up",
    color: "var(--green)",
    blurb:
      "Strong directional uptrend — momentum and trend-following strategies are favoured.",
  },
  TRENDING_DOWN: {
    label: "📉 Trend Down",
    color: "var(--red)",
    blurb:
      "Strong directional downtrend — favour shorts / trend-following, avoid catching falling knives.",
  },
  RANGING: {
    label: "↔️ Ranging",
    color: "#f59e0b",
    blurb:
      "Low trend strength — price is oscillating in a band. Mean-reversion works; breakouts often fail.",
  },
  VOLATILE: {
    label: "⚡ Volatile",
    color: "#f97316",
    blurb:
      "Elevated volatility with no clear trend — reduce size, widen stops, expect whipsaws.",
  },
};

interface Regime {
  scope?: string;
  regime: string;
  adx: number;
  trendStrength?: string;
  atrPct?: number;
  priceVsEma50?: number;
  priceVsEma200?: number;
  playbook?: { favoured?: string[]; avoid?: string[] };
}

function RegimeModal({
  regime,
  onClose,
}: {
  regime: Regime;
  onClose: () => void;
}) {
  const ui = REGIME_UI[regime.regime] || {
    label: regime.regime,
    color: "var(--text-muted)",
    blurb: "",
  };
  const Stat = ({
    label,
    value,
    color,
  }: {
    label: string;
    value: ReactNode;
    color?: string;
  }) => (
    <div className="metric-card">
      <p className="metric-label">{label}</p>
      <p
        className="metric-value"
        style={{ color: color || "var(--text-primary)", fontSize: "1.1rem" }}
      >
        {value}
      </p>
    </div>
  );
  const pct = (v?: number) =>
    v === undefined ? "—" : `${v > 0 ? "+" : ""}${v}%`;
  return createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content card"
        style={{ maxWidth: 560 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2
            className="page-title"
            style={{ fontSize: "1.25rem", color: ui.color }}
          >
            {ui.label}{" "}
            <span
              style={{
                color: "var(--text-muted)",
                fontSize: "0.85rem",
                fontWeight: 400,
              }}
            >
              · {regime.scope || "NIFTY 50"}
            </span>
          </h2>
          <button onClick={onClose} className="btn-close" aria-label="Close">
            <svg
              width="24"
              height="24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
        <div className="modal-body p-4">
          <p className="page-subtitle" style={{ marginBottom: "1.25rem" }}>
            {ui.blurb}
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "0.75rem",
              marginBottom: "1.5rem",
            }}
          >
            <Stat label="ADX" value={regime.adx} color={ui.color} />
            <Stat label="Trend strength" value={regime.trendStrength || "—"} />
            <Stat
              label="ATR %"
              value={regime.atrPct !== undefined ? `${regime.atrPct}%` : "—"}
            />
            <Stat
              label="Price vs EMA50"
              value={pct(regime.priceVsEma50)}
              color={
                (regime.priceVsEma50 || 0) >= 0 ? "var(--green)" : "var(--red)"
              }
            />
            <Stat
              label="Price vs EMA200"
              value={pct(regime.priceVsEma200)}
              color={
                (regime.priceVsEma200 || 0) >= 0 ? "var(--green)" : "var(--red)"
              }
            />
          </div>

          {regime.playbook?.favoured?.length ? (
            <div style={{ marginBottom: "1rem" }}>
              <h3
                style={{
                  fontSize: "0.95rem",
                  marginBottom: "0.5rem",
                  color: "var(--green)",
                }}
              >
                ✓ Favoured
              </h3>
              <ul
                style={{
                  margin: 0,
                  paddingLeft: "1.25rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.7,
                }}
              >
                {regime.playbook.favoured.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {regime.playbook?.avoid?.length ? (
            <div>
              <h3
                style={{
                  fontSize: "0.95rem",
                  marginBottom: "0.5rem",
                  color: "var(--red)",
                }}
              >
                ✕ Avoid
              </h3>
              <ul
                style={{
                  margin: 0,
                  paddingLeft: "1.25rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.7,
                }}
              >
                {regime.playbook.avoid.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}

function RegimeChip() {
  const [regime, setRegime] = useState<Regime | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    axios
      .get(`${API}/api/engine/regime`)
      .then((r) => setRegime(r.data))
      .catch(() => setRegime(null));
  }, []);

  if (!regime) return null;
  const ui = REGIME_UI[regime.regime] || {
    label: regime.regime,
    color: "var(--text-muted)",
    blurb: "",
  };
  return (
    <>
      <button
        className="market-status"
        onClick={() => setOpen(true)}
        title="View market regime details"
        style={{
          color: ui.color,
          cursor: "pointer",
          background: "none",
          border: "none",
          font: "inherit",
        }}
      >
        <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>{ui.label}</span>
        <span style={{ fontSize: "0.7rem", opacity: 0.6 }}>ⓘ</span>
      </button>
      {open && <RegimeModal regime={regime} onClose={() => setOpen(false)} />}
    </>
  );
}

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
          to="/portfolio"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          💼 Portfolio
        </NavLink>
        <NavLink
          to="/news"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          📰 News
        </NavLink>
        <NavLink
          to="/sectors"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          🗂️ Sectors
        </NavLink>
        <NavLink
          to="/backtesting"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          ⚡ Backtesting
        </NavLink>
        <NavLink
          to="/builder"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          🧩 Builder
        </NavLink>
        <NavLink
          to="/settings"
          className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
        >
          ⚙️ Settings
        </NavLink>
        <RegimeChip />
        <div className="market-status">
          <span className={`market-dot ${open ? "open" : ""}`}></span>
          <span>{open ? "MARKET OPEN" : "MARKET CLOSED"}</span>
        </div>
      </div>
    </nav>
  );
}
