"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";

// ── API Client ────────────────────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_URL || "";

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<{ data: T | null; error: string | null }> {
  try {
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    const res = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
    if (res.status === 401) {
      // Try refresh
      const refreshed = await tryRefresh();
      if (refreshed) return apiFetch(path, options);
      window.location.href = "/login";
      return { data: null, error: "Unauthorized" };
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { data: null, error: body.detail || `HTTP ${res.status}` };
    }
    const data: T = await res.json();
    return { data, error: null };
  } catch (err: unknown) {
    return { data: null, error: err instanceof Error ? err.message : "Network error" };
  }
}

async function tryRefresh(): Promise<boolean> {
  const refresh_token = localStorage.getItem("refresh_token");
  if (!refresh_token) return false;
  try {
    const res = await fetch(`${API}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
    if (!res.ok) return false;
    const { access_token, refresh_token: new_refresh } = await res.json();
    localStorage.setItem("access_token", access_token);
    if (new_refresh) localStorage.setItem("refresh_token", new_refresh);
    return true;
  } catch {
    return false;
  }
}

// ── Types ──────────────────────────────────────────────────────────

type Signal = {
  id: string; symbol: string; direction: "BUY" | "SELL" | "HOLD";
  entry_price: number; stop_loss: number; take_profit_1: number;
  confidence_score: number; risk_score: number; timeframe: string;
  ai_explanation: string; ai_sentiment: string;
  xgboost_score: number; lstm_score: number; transformer_score: number;
  generated_at: string;
};

type Trade = {
  id: string; symbol: string; direction: "BUY" | "SELL";
  status: "open" | "closed" | "pending";
  entry_price: number; current_price?: number;
  unrealized_pnl?: number; realized_pnl?: number;
  lot_size: number; risk_pct: number; opened_at: string;
};

type PortfolioStats = {
  balance: number; equity: number; total_pnl: number;
  win_rate: number; total_trades: number; open_trades: number; drawdown: number;
};

type ForexAccount = {
  id: string; broker_name: string; account_number: string;
  server: string; is_demo: boolean; is_active: boolean;
  balance?: number; currency?: string; last_sync?: string;
};

type CryptoAccount = {
  id: string; exchange: string; label?: string;
  is_testnet: boolean; is_active: boolean; last_sync?: string;
};

type RiskSettings = {
  max_risk_per_trade: number; max_daily_loss: number;
  max_drawdown: number; min_confidence: number;
  max_open_trades: number; max_spread_pips: number;
  news_filter_enabled: boolean; auto_trade_enabled: boolean;
};

type NotifPrefs = {
  telegram_chat_id?: string; telegram_enabled: boolean;
  email_enabled: boolean; push_enabled: boolean;
  signal_alerts: boolean; trade_alerts: boolean;
  risk_alerts: boolean; news_alerts: boolean;
};

type User = {
  id: string; email: string; username: string;
  full_name?: string; plan: string;
};

type Toast = { id: number; msg: string; type: "success" | "error" | "info" };

// ── Utilities ─────────────────────────────────────────────────────

const fmt = (n: number, d = 2) =>
  n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtPrice = (n: number, sym: string) => {
  if (sym.includes("BTC") || sym.includes("ETH")) return fmt(n, 0);
  if (sym.includes("JPY")) return fmt(n, 3);
  if (sym.includes("XAU")) return fmt(n, 2);
  return fmt(n, 4);
};
const timeAgo = (iso: string) => {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

// ── Toast Hook ────────────────────────────────────────────────────

function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);
  const push = useCallback((msg: string, type: Toast["type"] = "info") => {
    const id = ++counter.current;
    setToasts(p => [...p, { id, msg, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000);
  }, []);
  return { toasts, push };
}

// ── Small Components ──────────────────────────────────────────────

const StatCard = ({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) => (
  <div className="stat-card">
    <div className="stat-label">{label}</div>
    <div className={`stat-value ${accent || ""}`}>{value}</div>
    {sub && <div className="stat-sub">{sub}</div>}
  </div>
);

const ConfidenceBar = ({ value, label }: { value: number; label: string }) => (
  <div className="conf-row">
    <span className="conf-label">{label}</span>
    <div className="conf-track"><div className="conf-fill" style={{ width: `${value * 100}%` }} /></div>
    <span className="conf-pct">{(value * 100).toFixed(0)}%</span>
  </div>
);

const DirectionBadge = ({ direction }: { direction: "BUY" | "SELL" | "HOLD" }) => (
  <span className={`dir-badge dir-${direction.toLowerCase()}`}>{direction}</span>
);

const Spinner = ({ size = 16 }: { size?: number }) => (
  <span className="spinner" style={{ width: size, height: size }} />
);

// ── Plan Badge + Trial Countdown ──────────────────────────────────

function PlanBadge({ user }: { user: User | null }) {
  if (!user) return null;
  const plan = user.plan || "free";

  if (plan === "expired_free") {
    return (
      <a href="/pricing" className="plan-badge plan-expired">
        ⚠ Trial ended — Upgrade
      </a>
    );
  }

  if (plan === "free") {
    const created = (user as unknown as { created_at?: string }).created_at;
    if (created) {
      const daysUsed = Math.floor((Date.now() - new Date(created).getTime()) / 86400000);
      const daysLeft = Math.max(0, 7 - daysUsed);
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="plan-badge">FREE Trial</span>
          <span style={{ fontSize: 10, color: daysLeft <= 2 ? "var(--red)" : "var(--text3)" }}>
            {daysLeft === 0 ? "Expires today" : `${daysLeft}d remaining`}
          </span>
          {daysLeft <= 3 && (
            <a href="/pricing" className="upgrade-cta">Upgrade to Pro →</a>
          )}
        </div>
      );
    }
    return <span className="plan-badge">FREE Trial</span>;
  }

  return (
    <span className="plan-badge">
      {plan === "enterprise" ? "⭐ ENTERPRISE" : "✦ PRO"} Plan
    </span>
  );
}

// ── Upgrade Banner (shown inline when plan is expired/limited) ────

function UpgradeBanner({ plan, onDismiss }: { plan: string; onDismiss: () => void }) {
  if (plan === "pro" || plan === "enterprise") return null;
  const expired = plan === "expired_free";
  return (
    <div className="upgrade-banner">
      <div>
        <strong>{expired ? "Your free trial has ended" : "You're on the free trial"}</strong>
        <span style={{ color: "var(--text3)", marginLeft: 8, fontSize: 12 }}>
          {expired
            ? "Upgrade to keep receiving signals on all 8 pairs."
            : "Free trial gives you EURUSD + BTCUSDT on 1H only. Pro unlocks all 8 pairs × 4 timeframes."}
        </span>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <a href="/pricing" className="btn btn-primary" style={{ padding: "6px 14px", fontSize: 12, flex: "none" }}>
          Upgrade to Pro
        </a>
        {!expired && (
          <button onClick={onDismiss} className="btn btn-outline" style={{ padding: "6px 10px", fontSize: 12 }}>✕</button>
        )}
      </div>
    </div>
  );
}

// ── Toasts ────────────────────────────────────────────────────────

function ToastContainer({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type}`}>{t.msg}</div>
      ))}
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────

export default function MeritTradeDashboard() {
  // ── Toast (must be first — used by effects and callbacks below) ──
  const { toasts, push } = useToast();

  const [activeTab, setActiveTab] = useState<"dashboard" | "signals" | "trades" | "risk" | "brokers" | "notifications">("dashboard");
  const [signals, setSignals] = useState<Signal[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<PortfolioStats | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [autoTrade, setAutoTrade] = useState(false);
  const [loading, setLoading] = useState(true);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const [livePrice, setLivePrice] = useState<Record<string, number>>({
    EURUSD: 1.0857, GBPUSD: 1.2641, BTCUSDT: 67180, XAUUSD: 2321.40,
  });

  // ── Initial data load ─────────────────────────────────────────
  useEffect(() => {
    async function bootstrap() {
      setLoading(true);
      const [userRes, signalsRes, tradesRes] = await Promise.all([
        apiFetch<User>("/api/users/me"),
        apiFetch<Signal[]>("/api/signals"),
        apiFetch<Trade[]>("/api/execute/trades"),
      ]);
      if (userRes.data) setUser(userRes.data);
      if (signalsRes.data) setSignals(signalsRes.data);
      if (tradesRes.data) {
        setTrades(tradesRes.data);
        const open = tradesRes.data.filter(t => t.status === "open");
        const closed = tradesRes.data.filter(t => t.status === "closed");
        const wins = closed.filter(t => (t.realized_pnl || 0) > 0).length;
        const totalPnl = closed.reduce((s, t) => s + (t.realized_pnl || 0), 0);
        setStats({
          balance: 10000, equity: 10000 + open.reduce((s, t) => s + (t.unrealized_pnl || 0), 0),
          total_pnl: totalPnl, win_rate: closed.length ? wins / closed.length * 100 : 0,
          total_trades: closed.length, open_trades: open.length, drawdown: 0,
        });
      }
      setLoading(false);
    }
    bootstrap();
  }, []);

  // ── WebSocket ─────────────────────────────────────────────────
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    const wsUrl = (process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000") + `/ws/signals?token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "new_signal") {
          setSignals(prev => [msg.data, ...prev].slice(0, 20));
          push(`New signal: ${msg.data.symbol} ${msg.data.direction}`, "info");
        }
        if (msg.type === "price_tick") {
          setLivePrice(prev => ({ ...prev, [msg.symbol]: msg.price }));
        }
        if (msg.type === "trade_update") {
          setTrades(prev => prev.map(t => t.id === msg.data.id ? { ...t, ...msg.data } : t));
        }
      } catch {}
    };
    return () => ws.close();
  }, [push]);

  // ── Simulate live ticks (fallback when WS not connected) ──────
  useEffect(() => {
    if (wsConnected) return;
    const iv = setInterval(() => {
      setLivePrice(prev => ({
        EURUSD: prev.EURUSD + (Math.random() - 0.5) * 0.0003,
        GBPUSD: prev.GBPUSD + (Math.random() - 0.5) * 0.0004,
        BTCUSDT: prev.BTCUSDT + (Math.random() - 0.5) * 80,
        XAUUSD: prev.XAUUSD + (Math.random() - 0.5) * 1.2,
      }));
    }, 1200);
    return () => clearInterval(iv);
  }, [wsConnected]);

  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: "◈" },
    { id: "signals", label: "Signals", icon: "⚡" },
    { id: "trades", label: "Trades", icon: "↕" },
    { id: "risk", label: "Risk", icon: "◎" },
    { id: "brokers", label: "Brokers", icon: "⌗" },
    { id: "notifications", label: "Alerts", icon: "🔔" },
  ] as const;

  const equityCurve = Array.from({ length: 30 }, (_, i) => ({
    day: `D${i + 1}`,
    equity: 10000 + Math.sin(i * 0.3) * 500 + i * 80,
  }));

  const handleExecuteTrade = useCallback(async (signal: Signal) => {
    push("Submitting trade through risk engine…", "info");
    // User must have an account selected — for now use first available
    const accountsRes = await apiFetch<{ forex: ForexAccount[]; crypto: CryptoAccount[] }>("/api/users/accounts");
    const accounts = accountsRes.data;
    const isCrypto = signal.symbol.includes("BTC") || signal.symbol.includes("ETH") || signal.symbol.includes("SOL");
    const account = isCrypto ? accounts?.crypto[0] : accounts?.forex[0];
    if (!account) {
      push("No broker account connected. Please add one in the Brokers tab.", "error");
      return;
    }
    const { data, error } = await apiFetch<{ trade_id: string; status: string }>("/api/execute/trade", {
      method: "POST",
      body: JSON.stringify({
        signal_id: signal.id,
        account_id: account.id,
        account_type: isCrypto ? "crypto" : "forex",
      }),
    });
    if (error) { push(`Trade rejected: ${error}`, "error"); return; }
    push(`Trade opened: ${signal.symbol} ${signal.direction} ✓`, "success");
    const tradesRes = await apiFetch<Trade[]>("/api/execute/trades");
    if (tradesRes.data) setTrades(tradesRes.data);
  }, [push]);

  const handleCloseTrade = useCallback(async (tradeId: string) => {
    const { error } = await apiFetch<unknown>(`/api/execute/close/${tradeId}`, { method: "POST" });
    if (error) { push(`Failed to close trade: ${error}`, "error"); return; }
    push("Trade closed successfully", "success");
    const res = await apiFetch<Trade[]>("/api/execute/trades");
    if (res.data) setTrades(res.data);
  }, [push]);

  const handleAutoTradeToggle = useCallback(async () => {
    const next = !autoTrade;
    setAutoTrade(next);
    const { error } = await apiFetch<unknown>(`/api/risk/settings/${user?.id}`, {
      method: "PUT",
      body: JSON.stringify({ auto_trade_enabled: next }),
    });
    if (error) { push(`Failed to update auto-trade: ${error}`, "error"); setAutoTrade(!next); return; }
    push(`Auto-trade ${next ? "enabled" : "disabled"}`, "success");
  }, [autoTrade, user, push]);

  return (
    <div className="app">
      <ToastContainer toasts={toasts} />

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">M</div>
          <div>
            <div className="brand-name">Merit-Trade</div>
            <div className="brand-sub">AI Trading</div>
          </div>
        </div>
        <nav className="nav">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id as typeof activeTab)}
              className={`nav-item ${activeTab === t.id ? "nav-active" : ""}`}>
              <span className="nav-icon">{t.icon}</span>
              <span>{t.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className={`ws-badge ${wsConnected ? "ws-live" : "ws-offline"}`}>
            <span className="ws-dot" />{wsConnected ? "Live" : "Demo Mode"}
          </div>
          <PlanBadge user={user} />
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        <header className="topbar">
          <div className="page-title">{tabs.find(t => t.id === activeTab)?.label}</div>
          <div className="ticker-strip">
            {Object.entries(livePrice).map(([sym, price]) => (
              <div key={sym} className="ticker-item">
                <span className="ticker-sym">{sym}</span>
                <span className="ticker-price">{fmtPrice(price, sym)}</span>
              </div>
            ))}
          </div>
          <div className="topbar-actions">
            <div className="auto-toggle">
              <span className="toggle-label">Auto-trade</span>
              <button onClick={handleAutoTradeToggle}
                className={`toggle-btn ${autoTrade ? "toggle-on" : ""}`}>
                <div className="toggle-thumb" />
              </button>
            </div>
            <div className="user-avatar" title={user?.email}>
              {user?.username?.slice(0, 2).toUpperCase() || "??"}
            </div>
            <button
              className="btn btn-outline btn-sm"
              title="Sign out"
              onClick={async () => {
                await apiFetch("/api/auth/logout", { method: "POST" });
                localStorage.removeItem("access_token");
                localStorage.removeItem("refresh_token");
                localStorage.removeItem("user");
                // Clear the cookie mirror used by middleware
                document.cookie = "access_token=; path=/; max-age=0; SameSite=Strict";
                window.location.href = "/login";
              }}
              style={{ padding: "5px 12px", fontSize: 12 }}
            >
              Sign out
            </button>
          </div>
        </header>

        <div className="content">
          {!bannerDismissed && user && (
            <UpgradeBanner plan={user.plan || "free"} onDismiss={() => setBannerDismissed(true)} />
          )}
          {loading ? (
            <div className="loading-state">
              <Spinner size={32} />
              <span>Loading your account…</span>
            </div>
          ) : (
            <>
              {activeTab === "dashboard" && (
                <DashboardView stats={stats} trades={trades} equityCurve={equityCurve} />
              )}
              {activeTab === "signals" && (
                <SignalsView signals={signals} livePrice={livePrice} onExecute={handleExecuteTrade} />
              )}
              {activeTab === "trades" && (
                <TradesView trades={trades} onClose={handleCloseTrade} />
              )}
              {activeTab === "risk" && (
                <RiskView userId={user?.id} push={push} />
              )}
              {activeTab === "brokers" && (
                <BrokersView push={push} />
              )}
              {activeTab === "notifications" && (
                <NotificationsView userId={user?.id} push={push} />
              )}
            </>
          )}
        </div>
      </main>

      <style jsx global>{`
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
          --bg: #050a14; --bg2: #0a1628; --bg3: #0f2040;
          --card: #0d1f35; --card2: #112540;
          --border: #1a3050; --border2: #1f3d60;
          --accent: #00d4ff; --accent2: #0095c8;
          --green: #00e676; --green2: #00b259;
          --red: #ff3d5a; --red2: #c4003d;
          --yellow: #ffd740;
          --text: #e2f0ff; --text2: #8baabb; --text3: #4a6a80;
          --font-mono: 'Courier New', monospace;
        }
        body { background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif; font-size: 14px; overflow: hidden; }
        .app { display: flex; height: 100vh; }

        /* Sidebar */
        .sidebar { width: 220px; background: var(--bg2); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: 20px 0; flex-shrink: 0; }
        .brand { display: flex; align-items: center; gap: 10px; padding: 0 20px 28px; border-bottom: 1px solid var(--border); margin-bottom: 16px; }
        .brand-icon { width: 36px; height: 36px; background: linear-gradient(135deg, var(--accent), var(--accent2)); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 18px; color: #000; }
        .brand-name { font-size: 15px; font-weight: 700; color: var(--text); }
        .brand-sub { font-size: 10px; color: var(--text3); letter-spacing: .08em; text-transform: uppercase; }
        .nav { flex: 1; padding: 0 12px; }
        .nav-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px; background: none; border: none; color: var(--text2); border-radius: 8px; cursor: pointer; font-size: 14px; transition: all .15s; margin-bottom: 2px; text-align: left; }
        .nav-item:hover { background: var(--bg3); color: var(--text); }
        .nav-active { background: rgba(0,212,255,0.1) !important; color: var(--accent) !important; border: 1px solid rgba(0,212,255,0.2); }
        .nav-icon { font-size: 16px; width: 20px; text-align: center; }
        .sidebar-footer { padding: 16px 20px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; }
        .ws-badge { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; }
        .ws-dot { width: 7px; height: 7px; border-radius: 50%; }
        .ws-live .ws-dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
        .ws-offline .ws-dot { background: var(--text3); }
        .ws-live { color: var(--green); } .ws-offline { color: var(--text3); }
        .plan-badge { font-size: 10px; font-weight: 700; letter-spacing: .1em; color: var(--accent); background: rgba(0,212,255,.08); border: 1px solid rgba(0,212,255,.2); padding: 3px 8px; border-radius: 4px; width: fit-content; text-decoration: none; display: inline-block; }
        .plan-expired { color: var(--red); background: rgba(255,61,90,.08); border-color: rgba(255,61,90,.3); animation: pulse-border 2s infinite; }
        @keyframes pulse-border { 0%,100% { border-color: rgba(255,61,90,.3); } 50% { border-color: rgba(255,61,90,.8); } }
        .upgrade-cta { font-size: 10px; color: var(--accent); text-decoration: none; font-weight: 600; }
        .upgrade-cta:hover { text-decoration: underline; }
        .upgrade-banner { display: flex; align-items: center; justify-content: space-between; gap: 12px; background: rgba(0,212,255,.05); border: 1px solid rgba(0,212,255,.2); border-radius: 10px; padding: 12px 16px; margin-bottom: 20px; flex-wrap: wrap; font-size: 13px; }

        /* Main */
        .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .topbar { display: flex; align-items: center; gap: 16px; padding: 0 28px; height: 60px; background: var(--bg2); border-bottom: 1px solid var(--border); flex-shrink: 0; }
        .page-title { font-size: 18px; font-weight: 700; min-width: 120px; }
        .ticker-strip { display: flex; gap: 20px; flex: 1; overflow: hidden; }
        .ticker-item { display: flex; gap: 6px; align-items: baseline; }
        .ticker-sym { font-size: 11px; color: var(--text3); font-weight: 600; letter-spacing: .05em; }
        .ticker-price { font-size: 13px; font-family: var(--font-mono); color: var(--text); font-weight: 600; }
        .topbar-actions { display: flex; align-items: center; gap: 16px; }
        .auto-toggle { display: flex; align-items: center; gap: 8px; }
        .toggle-label { font-size: 12px; color: var(--text2); }
        .toggle-btn { width: 40px; height: 22px; border-radius: 11px; background: var(--bg3); border: 1px solid var(--border2); cursor: pointer; padding: 2px; transition: background .2s; display: flex; align-items: center; }
        .toggle-on { background: var(--green2); border-color: var(--green); }
        .toggle-thumb { width: 16px; height: 16px; border-radius: 50%; background: var(--text2); transition: transform .2s; flex-shrink: 0; }
        .toggle-on .toggle-thumb { transform: translateX(18px); background: #fff; }
        .user-avatar { width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--accent2)); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: #000; cursor: pointer; }
        .content { flex: 1; overflow-y: auto; padding: 24px 28px; }
        .loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 16px; color: var(--text3); }

        /* Spinner */
        .spinner { display: inline-block; border: 2px solid rgba(0,212,255,.2); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Toasts */
        .toast-container { position: fixed; bottom: 24px; right: 24px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; }
        .toast { padding: 12px 18px; border-radius: 10px; font-size: 13px; font-weight: 500; max-width: 340px; animation: slideIn .25s ease; }
        @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: none; opacity: 1; } }
        .toast-success { background: rgba(0,230,118,.15); border: 1px solid rgba(0,230,118,.4); color: var(--green); }
        .toast-error { background: rgba(255,61,90,.15); border: 1px solid rgba(255,61,90,.4); color: var(--red); }
        .toast-info { background: rgba(0,212,255,.1); border: 1px solid rgba(0,212,255,.3); color: var(--accent); }

        /* Stats */
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(175px, 1fr)); gap: 14px; margin-bottom: 24px; }
        .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; }
        .stat-label { font-size: 11px; color: var(--text3); text-transform: uppercase; letter-spacing: .07em; margin-bottom: 8px; }
        .stat-value { font-size: 22px; font-weight: 700; font-family: var(--font-mono); }
        .stat-sub { font-size: 11px; color: var(--text3); margin-top: 4px; }
        .green { color: var(--green); } .red { color: var(--red); } .accent { color: var(--accent); } .yellow { color: var(--yellow); }

        /* Charts */
        .chart-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
        .chart-title { font-size: 13px; font-weight: 600; color: var(--text2); margin-bottom: 16px; text-transform: uppercase; letter-spacing: .05em; }
        .charts-row { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 24px; }

        /* Signals */
        .signals-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
        .signal-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 18px; cursor: pointer; transition: border-color .15s, transform .1s; }
        .signal-card:hover { border-color: var(--border2); transform: translateY(-1px); }
        .signal-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
        .signal-symbol { font-size: 17px; font-weight: 700; }
        .signal-tf { font-size: 11px; background: var(--bg3); color: var(--text3); padding: 2px 6px; border-radius: 4px; }
        .signal-time { font-size: 11px; color: var(--text3); margin-left: auto; }
        .dir-badge { padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; letter-spacing: .05em; }
        .dir-buy { background: rgba(0,230,118,.15); color: var(--green); border: 1px solid rgba(0,230,118,.3); }
        .dir-sell { background: rgba(255,61,90,.15); color: var(--red); border: 1px solid rgba(255,61,90,.3); }
        .dir-hold { background: rgba(255,215,64,.1); color: var(--yellow); border: 1px solid rgba(255,215,64,.2); }
        .signal-prices { display: grid; grid-template-columns: repeat(3,1fr); gap: 8px; margin-bottom: 14px; }
        .price-item { text-align: center; }
        .price-label { font-size: 9px; color: var(--text3); text-transform: uppercase; letter-spacing: .07em; }
        .price-val { font-family: var(--font-mono); font-size: 13px; font-weight: 600; }
        .price-entry { color: var(--text); } .price-sl { color: var(--red); } .price-tp { color: var(--green); }
        .signal-metrics { margin-bottom: 12px; }
        .conf-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .conf-label { font-size: 11px; color: var(--text3); width: 80px; flex-shrink: 0; }
        .conf-track { flex: 1; height: 4px; background: var(--bg3); border-radius: 2px; overflow: hidden; }
        .conf-fill { height: 100%; background: linear-gradient(90deg, var(--accent2), var(--accent)); border-radius: 2px; }
        .conf-pct { font-size: 11px; color: var(--text2); width: 32px; text-align: right; font-family: var(--font-mono); }
        .signal-ai { font-size: 11px; color: var(--text3); line-height: 1.5; background: var(--bg3); border-radius: 6px; padding: 8px 10px; margin-bottom: 12px; }
        .signal-actions { display: flex; gap: 8px; }

        /* Buttons */
        .btn { padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; border: none; transition: all .15s; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
        .btn:disabled { opacity: .5; cursor: not-allowed; }
        .btn-primary { background: var(--accent); color: #000; flex: 1; }
        .btn-primary:hover:not(:disabled) { background: #00f0ff; transform: translateY(-1px); }
        .btn-outline { background: transparent; color: var(--text2); border: 1px solid var(--border2); }
        .btn-outline:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
        .btn-danger { background: transparent; color: var(--red); border: 1px solid rgba(255,61,90,.3); }
        .btn-danger:hover:not(:disabled) { background: rgba(255,61,90,.1); }
        .btn-sm { padding: 5px 10px; font-size: 12px; }

        /* Trades table */
        .trades-table { width: 100%; border-collapse: collapse; }
        .trades-table th { text-align: left; padding: 10px 14px; font-size: 11px; color: var(--text3); text-transform: uppercase; letter-spacing: .06em; border-bottom: 1px solid var(--border); background: var(--bg2); }
        .trades-table td { padding: 12px 14px; border-bottom: 1px solid rgba(26,48,80,.5); font-family: var(--font-mono); font-size: 13px; }
        .trades-table tr:hover td { background: var(--bg3); }
        .status-badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
        .status-open { background: rgba(0,212,255,.1); color: var(--accent); }
        .status-closed { background: rgba(255,255,255,.05); color: var(--text3); }

        /* Risk */
        .risk-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-bottom: 20px; }
        .risk-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
        .risk-card-title { font-size: 13px; font-weight: 600; margin-bottom: 16px; color: var(--text2); }
        .risk-field-value { font-size: 20px; font-weight: 700; font-family: var(--font-mono); color: var(--accent); margin-bottom: 4px; }
        .risk-slider { width: 100%; accent-color: var(--accent); margin-bottom: 4px; }
        .risk-range-labels { display: flex; justify-content: space-between; font-size: 10px; color: var(--text3); }

        /* Brokers */
        .broker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .broker-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; }
        .broker-header { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
        .broker-icon { width: 42px; height: 42px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
        .broker-forex { background: rgba(0,212,255,.1); } .broker-crypto { background: rgba(255,215,64,.1); } .broker-notif { background: rgba(0,230,118,.1); }
        .broker-name { font-size: 16px; font-weight: 700; } .broker-sub { font-size: 12px; color: var(--text3); }
        .form-field { margin-bottom: 12px; }
        .form-field label { display: block; font-size: 11px; color: var(--text3); margin-bottom: 5px; text-transform: uppercase; letter-spacing: .05em; }
        .form-field input, .form-field select { width: 100%; background: var(--bg3); border: 1px solid var(--border2); border-radius: 8px; padding: 10px 12px; color: var(--text); font-size: 13px; outline: none; font-family: var(--font-mono); }
        .form-field input:focus, .form-field select:focus { border-color: var(--accent); }
        .form-field select option { background: var(--bg3); }
        .connection-status { display: flex; align-items: center; gap: 6px; font-size: 12px; padding: 8px 0; }
        .conn-dot { width: 7px; height: 7px; border-radius: 50%; }
        .conn-active { background: var(--green); box-shadow: 0 0 6px var(--green); }
        .conn-inactive { background: var(--text3); }
        .section-title { font-size: 13px; font-weight: 600; color: var(--text2); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 16px; }

        /* Connected accounts list */
        .account-list { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; }
        .account-row { display: flex; align-items: center; justify-content: space-between; background: var(--bg3); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; }
        .account-info { display: flex; flex-direction: column; gap: 2px; }
        .account-name { font-size: 13px; font-weight: 600; color: var(--text); }
        .account-detail { font-size: 11px; color: var(--text3); font-family: var(--font-mono); }

        /* Notification toggle rows */
        .notif-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid var(--border); }
        .notif-row:last-child { border-bottom: none; }
        .notif-label { font-size: 13px; color: var(--text); }
        .notif-sub { font-size: 11px; color: var(--text3); margin-top: 2px; }
        .alert-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 16px; }
        .alert-title { font-size: 13px; font-weight: 600; color: var(--text2); margin-bottom: 16px; text-transform: uppercase; letter-spacing: .05em; }
      `}</style>
    </div>
  );
}

// ── Dashboard View ────────────────────────────────────────────────

function DashboardView({ stats, trades, equityCurve }: {
  stats: PortfolioStats | null; trades: Trade[]; equityCurve: { day: string; equity: number }[];
}) {
  const pnlData = Array.from({ length: 14 }, (_, i) => ({
    day: `D${i + 1}`, pnl: Math.random() * 400 - 100,
  }));
  const s = stats || { balance: 0, equity: 0, total_pnl: 0, win_rate: 0, total_trades: 0, open_trades: 0, drawdown: 0 };

  return (
    <>
      <div className="stats-grid">
        <StatCard label="Balance" value={`$${fmt(s.balance)}`} sub="Account balance" />
        <StatCard label="Total P&L" value={`${s.total_pnl >= 0 ? "+" : ""}$${fmt(s.total_pnl)}`} accent="green" />
        <StatCard label="Win Rate" value={`${fmt(s.win_rate, 1)}%`} sub={`${s.total_trades} closed trades`} accent="accent" />
        <StatCard label="Open Trades" value={String(s.open_trades)} sub="Active positions" />
        <StatCard label="Drawdown" value={`${fmt(s.drawdown, 1)}%`} accent="yellow" />
        <StatCard label="Equity" value={`$${fmt(s.equity)}`} sub="Unrealized incl." />
      </div>
      <div className="charts-row">
        <div className="chart-card">
          <div className="chart-title">Equity Curve (30 Days)</div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={equityCurve}>
              <defs>
                <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00d4ff" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a3050" />
              <XAxis dataKey="day" tick={{ fill: "#4a6a80", fontSize: 10 }} tickLine={false} />
              <YAxis tick={{ fill: "#4a6a80", fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#0d1f35", border: "1px solid #1a3050", borderRadius: 8 }} itemStyle={{ color: "#00d4ff" }} />
              <Area type="monotone" dataKey="equity" stroke="#00d4ff" strokeWidth={2} fill="url(#eqGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-card">
          <div className="chart-title">Daily P&L</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={pnlData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a3050" />
              <XAxis dataKey="day" tick={{ fill: "#4a6a80", fontSize: 10 }} tickLine={false} />
              <YAxis tick={{ fill: "#4a6a80", fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#0d1f35", border: "1px solid #1a3050", borderRadius: 8 }} />
              <ReferenceLine y={0} stroke="#1a3050" />
              <Bar dataKey="pnl" radius={[3, 3, 0, 0]}
                fill="#00e676"
                label={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="chart-card">
        <div className="chart-title">Recent Trades</div>
        <table className="trades-table">
          <thead>
            <tr><th>Symbol</th><th>Dir</th><th>Status</th><th>Entry</th><th>P&L</th><th>Risk</th><th>Opened</th></tr>
          </thead>
          <tbody>
            {trades.slice(0, 8).map(t => (
              <tr key={t.id}>
                <td style={{ fontWeight: 600, color: "#e2f0ff" }}>{t.symbol}</td>
                <td><DirectionBadge direction={t.direction} /></td>
                <td><span className={`status-badge status-${t.status}`}>{t.status}</span></td>
                <td>{fmtPrice(t.entry_price, t.symbol)}</td>
                <td className={(t.status === "open" ? (t.unrealized_pnl || 0) : (t.realized_pnl || 0)) >= 0 ? "green" : "red"}>
                  {((t.status === "open" ? (t.unrealized_pnl || 0) : (t.realized_pnl || 0)) >= 0 ? "+" : "")}${fmt(t.status === "open" ? (t.unrealized_pnl || 0) : (t.realized_pnl || 0))}
                </td>
                <td style={{ color: "#8baabb" }}>{t.risk_pct}%</td>
                <td style={{ color: "#4a6a80" }}>{timeAgo(t.opened_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Signals View ──────────────────────────────────────────────────

function SignalsView({ signals, livePrice, onExecute }: {
  signals: Signal[]; livePrice: Record<string, number>;
  onExecute: (s: Signal) => Promise<void>;
}) {
  const [executing, setExecuting] = useState<string | null>(null);

  const handleExecute = async (sig: Signal) => {
    setExecuting(sig.id);
    await onExecute(sig);
    setExecuting(null);
  };

  return (
    <>
      <div style={{ marginBottom: 20, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="section-title">Live Signal Feed</div>
        <div style={{ fontSize: 12, color: "#4a6a80" }}>⚡ {signals.length} active signals</div>
      </div>
      {signals.length === 0 && (
        <div style={{ textAlign: "center", padding: "60px 0", color: "#4a6a80" }}>
          No signals yet. The ML engine generates signals every hour.
        </div>
      )}
      <div className="signals-grid">
        {signals.map(sig => (
          <div key={sig.id} className="signal-card">
            <div className="signal-header">
              <span className="signal-symbol">{sig.symbol}</span>
              <DirectionBadge direction={sig.direction} />
              <span className="signal-tf">{sig.timeframe}</span>
              <span className="signal-time">{timeAgo(sig.generated_at)}</span>
            </div>
            <div className="signal-prices">
              <div className="price-item">
                <div className="price-label">Entry</div>
                <div className="price-val price-entry">{fmtPrice(sig.entry_price, sig.symbol)}</div>
              </div>
              <div className="price-item">
                <div className="price-label">Stop Loss</div>
                <div className="price-val price-sl">{fmtPrice(sig.stop_loss, sig.symbol)}</div>
              </div>
              <div className="price-item">
                <div className="price-label">Take Profit</div>
                <div className="price-val price-tp">{fmtPrice(sig.take_profit_1, sig.symbol)}</div>
              </div>
            </div>
            <div className="signal-metrics">
              <ConfidenceBar value={sig.xgboost_score} label="XGBoost" />
              <ConfidenceBar value={sig.lstm_score} label="LSTM" />
              <ConfidenceBar value={sig.transformer_score} label="Transformer" />
            </div>
            <div style={{ display: "flex", gap: 10, marginBottom: 12, fontSize: 12 }}>
              <div style={{ flex: 1, background: "var(--bg3)", borderRadius: 8, padding: "8px 10px", textAlign: "center" }}>
                <div style={{ color: "var(--text3)", fontSize: 10, marginBottom: 2 }}>CONFIDENCE</div>
                <div style={{ color: "var(--accent)", fontFamily: "monospace", fontWeight: 700, fontSize: 16 }}>{sig.confidence_score}%</div>
              </div>
              <div style={{ flex: 1, background: "var(--bg3)", borderRadius: 8, padding: "8px 10px", textAlign: "center" }}>
                <div style={{ color: "var(--text3)", fontSize: 10, marginBottom: 2 }}>RISK SCORE</div>
                <div style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 16, color: sig.risk_score < 30 ? "var(--green)" : sig.risk_score < 60 ? "var(--yellow)" : "var(--red)" }}>{sig.risk_score}</div>
              </div>
            </div>
            <div className="signal-ai">💬 {sig.ai_explanation}</div>
            <div className="signal-actions">
              <button
                className="btn btn-primary"
                disabled={executing === sig.id}
                onClick={() => handleExecute(sig)}
              >
                {executing === sig.id ? <><Spinner size={14} /> Submitting…</> : "Execute Trade"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// ── Trades View ───────────────────────────────────────────────────

function TradesView({ trades, onClose }: { trades: Trade[]; onClose: (id: string) => Promise<void> }) {
  const [closing, setClosing] = useState<string | null>(null);
  const open = trades.filter(t => t.status === "open");
  const closed = trades.filter(t => t.status !== "open");

  const handleClose = async (id: string) => {
    setClosing(id);
    await onClose(id);
    setClosing(null);
  };

  return (
    <>
      <div className="section-title" style={{ marginBottom: 16 }}>Open Positions ({open.length})</div>
      <div className="chart-card" style={{ marginBottom: 24 }}>
        <table className="trades-table">
          <thead>
            <tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>Lot</th><th>Risk%</th><th>Unrealized P&L</th><th>Opened</th><th></th></tr>
          </thead>
          <tbody>
            {open.length === 0 && (
              <tr><td colSpan={8} style={{ textAlign: "center", color: "#4a6a80", padding: "24px" }}>No open positions</td></tr>
            )}
            {open.map(t => (
              <tr key={t.id}>
                <td style={{ fontWeight: 600, color: "#e2f0ff" }}>{t.symbol}</td>
                <td><DirectionBadge direction={t.direction} /></td>
                <td>{fmtPrice(t.entry_price, t.symbol)}</td>
                <td>{t.lot_size}</td>
                <td style={{ color: "#8baabb" }}>{t.risk_pct}%</td>
                <td className={(t.unrealized_pnl || 0) >= 0 ? "green" : "red"}>
                  {(t.unrealized_pnl || 0) >= 0 ? "+" : ""}${fmt(t.unrealized_pnl || 0)}
                </td>
                <td style={{ color: "#4a6a80" }}>{timeAgo(t.opened_at)}</td>
                <td>
                  <button className="btn btn-danger btn-sm" disabled={closing === t.id} onClick={() => handleClose(t.id)}>
                    {closing === t.id ? <Spinner size={12} /> : "Close"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title" style={{ marginBottom: 16 }}>Trade History ({closed.length})</div>
      <div className="chart-card">
        <table className="trades-table">
          <thead>
            <tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>Lot</th><th>Risk%</th><th>Realized P&L</th><th>Opened</th></tr>
          </thead>
          <tbody>
            {closed.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: "center", color: "#4a6a80", padding: "24px" }}>No closed trades yet</td></tr>
            )}
            {closed.map(t => (
              <tr key={t.id}>
                <td style={{ fontWeight: 600, color: "#e2f0ff" }}>{t.symbol}</td>
                <td><DirectionBadge direction={t.direction} /></td>
                <td>{fmtPrice(t.entry_price, t.symbol)}</td>
                <td>{t.lot_size}</td>
                <td style={{ color: "#8baabb" }}>{t.risk_pct}%</td>
                <td className={(t.realized_pnl || 0) >= 0 ? "green" : "red"}>
                  {(t.realized_pnl || 0) >= 0 ? "+" : ""}${fmt(t.realized_pnl || 0)}
                </td>
                <td style={{ color: "#4a6a80" }}>{timeAgo(t.opened_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Risk View ─────────────────────────────────────────────────────

function RiskView({ userId, push }: { userId?: string; push: (msg: string, type?: Toast["type"]) => void }) {
  const [settings, setSettings] = useState<RiskSettings>({
    max_risk_per_trade: 0.02, max_daily_loss: 0.05, max_drawdown: 0.15,
    min_confidence: 65, max_open_trades: 5, max_spread_pips: 3.0,
    news_filter_enabled: true, auto_trade_enabled: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!userId) return;
    apiFetch<RiskSettings>(`/api/risk/settings/${userId}`).then(({ data, error }) => {
      if (data) setSettings(data);
      if (error) push(`Failed to load risk settings: ${error}`, "error");
      setLoading(false);
    });
  }, [userId, push]);

  const update = (key: keyof RiskSettings, value: number | boolean) => {
    setSettings(prev => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const save = async () => {
    if (!userId) return;
    setSaving(true);
    const { error } = await apiFetch(`/api/risk/settings/${userId}`, {
      method: "PUT",
      body: JSON.stringify(settings),
    });
    setSaving(false);
    if (error) { push(`Failed to save: ${error}`, "error"); return; }
    push("Risk settings saved ✓", "success");
    setDirty(false);
  };

  if (loading) return <div className="loading-state"><Spinner size={24} /><span>Loading risk settings…</span></div>;

  const sliders = [
    { key: "max_risk_per_trade" as const, label: "Max Risk Per Trade", suffix: "%", min: 0.001, max: 0.05, step: 0.001, display: (v: number) => `${(v * 100).toFixed(1)}%` },
    { key: "max_daily_loss" as const, label: "Max Daily Loss", suffix: "%", min: 0.01, max: 0.20, step: 0.005, display: (v: number) => `${(v * 100).toFixed(1)}%` },
    { key: "max_drawdown" as const, label: "Max Drawdown", suffix: "%", min: 0.05, max: 0.50, step: 0.01, display: (v: number) => `${(v * 100).toFixed(0)}%` },
    { key: "min_confidence" as const, label: "Min Signal Confidence", suffix: "%", min: 50, max: 95, step: 1, display: (v: number) => `${v}%` },
    { key: "max_open_trades" as const, label: "Max Open Trades", suffix: "", min: 1, max: 20, step: 1, display: (v: number) => `${v}` },
    { key: "max_spread_pips" as const, label: "Max Spread (pips)", suffix: "", min: 0.5, max: 10, step: 0.5, display: (v: number) => `${v}` },
  ];

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div className="section-title">Risk Management Settings</div>
        <button className="btn btn-primary" style={{ flex: "none", width: "auto" }} disabled={!dirty || saving} onClick={save}>
          {saving ? <><Spinner size={14} /> Saving…</> : "Save Changes"}
        </button>
      </div>

      <div className="risk-grid">
        {sliders.map(f => (
          <div key={f.key} className="risk-card">
            <div className="risk-card-title">{f.label}</div>
            <div className="risk-field-value">{f.display(settings[f.key] as number)}</div>
            <input
              type="range" className="risk-slider"
              min={f.min} max={f.max} step={f.step}
              value={settings[f.key] as number}
              onChange={e => update(f.key, parseFloat(e.target.value))}
            />
            <div className="risk-range-labels">
              <span>{f.display(f.min)}</span><span>{f.display(f.max)}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="risk-card" style={{ marginBottom: 16 }}>
        <div className="risk-card-title">Feature Toggles</div>
        {[
          { key: "news_filter_enabled" as const, label: "News Filter", desc: "Block trades during high-impact news events" },
          { key: "auto_trade_enabled" as const, label: "Auto-Execute Trades", desc: "Automatically execute signals that pass the risk gate (Enterprise only)" },
        ].map(item => (
          <div key={item.key} className="notif-row">
            <div>
              <div className="notif-label">{item.label}</div>
              <div className="notif-sub">{item.desc}</div>
            </div>
            <button onClick={() => update(item.key, !settings[item.key])}
              className={`toggle-btn ${settings[item.key] ? "toggle-on" : ""}`}>
              <div className="toggle-thumb" />
            </button>
          </div>
        ))}
      </div>

      <div style={{ padding: 16, background: "rgba(255,61,90,0.05)", border: "1px solid rgba(255,61,90,0.2)", borderRadius: 12, fontSize: 12, color: "#8baabb" }}>
        🔒 <strong style={{ color: "#e2f0ff" }}>Risk Engine is always active.</strong> These settings are enforced server-side. No trade can bypass the risk engine regardless of client state.
      </div>
    </>
  );
}

// ── Brokers View ──────────────────────────────────────────────────

function BrokersView({ push }: { push: (msg: string, type?: Toast["type"]) => void }) {
  const [accounts, setAccounts] = useState<{ forex: ForexAccount[]; crypto: CryptoAccount[] }>({ forex: [], crypto: [] });
  const [mt5Form, setMt5Form] = useState({ broker_name: "", server: "", account_number: "", password: "", is_demo: true });
  const [cryptoForm, setCryptoForm] = useState({ exchange: "binance", label: "", api_key: "", api_secret: "", passphrase: "", is_testnet: true });
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [savingMt5, setSavingMt5] = useState(false);
  const [savingCrypto, setSavingCrypto] = useState(false);
  const [mt5Errors, setMt5Errors] = useState<Record<string, string>>({});
  const [cryptoErrors, setCryptoErrors] = useState<Record<string, string>>({});

  const loadAccounts = useCallback(async () => {
    const { data, error } = await apiFetch<{ forex: ForexAccount[]; crypto: CryptoAccount[] }>("/api/users/accounts");
    if (data) setAccounts(data);
    if (error) push(`Failed to load accounts: ${error}`, "error");
    setLoadingAccounts(false);
  }, [push]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  const validateMt5 = () => {
    const errs: Record<string, string> = {};
    if (!mt5Form.broker_name.trim()) errs.broker_name = "Broker name is required";
    if (!mt5Form.server.trim()) errs.server = "Server is required";
    if (!mt5Form.account_number.trim()) errs.account_number = "Account number is required";
    if (!mt5Form.password.trim()) errs.password = "Password is required";
    setMt5Errors(errs);
    return Object.keys(errs).length === 0;
  };

  const validateCrypto = () => {
    const errs: Record<string, string> = {};
    if (!cryptoForm.api_key.trim()) errs.api_key = "API key is required";
    if (!cryptoForm.api_secret.trim()) errs.api_secret = "API secret is required";
    setCryptoErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const connectMt5 = async () => {
    if (!validateMt5()) return;
    setSavingMt5(true);
    const { error } = await apiFetch("/api/users/forex-accounts", {
      method: "POST",
      body: JSON.stringify(mt5Form),
    });
    setSavingMt5(false);
    if (error) { push(`Failed to connect MT5: ${error}`, "error"); return; }
    push("MT5 account connected (credentials encrypted) ✓", "success");
    setMt5Form({ broker_name: "", server: "", account_number: "", password: "", is_demo: true });
    loadAccounts();
  };

  const connectCrypto = async () => {
    if (!validateCrypto()) return;
    setSavingCrypto(true);
    const { error } = await apiFetch("/api/users/crypto-accounts", {
      method: "POST",
      body: JSON.stringify(cryptoForm),
    });
    setSavingCrypto(false);
    if (error) { push(`Failed to connect exchange: ${error}`, "error"); return; }
    push(`${cryptoForm.exchange} exchange connected ✓`, "success");
    setCryptoForm({ exchange: "binance", label: "", api_key: "", api_secret: "", passphrase: "", is_testnet: true });
    loadAccounts();
  };

  const InputField = ({ label, value, onChange, type = "text", placeholder = "", error = "" }: {
    label: string; value: string; onChange: (v: string) => void;
    type?: string; placeholder?: string; error?: string;
  }) => (
    <div className="form-field">
      <label>{label}</label>
      <input type={type} value={value} placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        style={error ? { borderColor: "var(--red)" } : {}} />
      {error && <div style={{ fontSize: 11, color: "var(--red)", marginTop: 4 }}>{error}</div>}
    </div>
  );

  return (
    <>
      {/* Connected accounts */}
      {(accounts.forex.length > 0 || accounts.crypto.length > 0) && (
        <div style={{ marginBottom: 28 }}>
          <div className="section-title">Connected Accounts</div>
          <div className="account-list">
            {accounts.forex.map(a => (
              <div key={a.id} className="account-row">
                <div className="account-info">
                  <div className="account-name">📈 {a.broker_name} — #{a.account_number}</div>
                  <div className="account-detail">{a.server} · {a.is_demo ? "Demo" : "Live"}{a.balance ? ` · $${fmt(a.balance)}` : ""}</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="connection-status">
                    <span className={`conn-dot ${a.is_active ? "conn-active" : "conn-inactive"}`} />
                    {a.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>
            ))}
            {accounts.crypto.map(a => (
              <div key={a.id} className="account-row">
                <div className="account-info">
                  <div className="account-name">₿ {a.exchange.charAt(0).toUpperCase() + a.exchange.slice(1)}{a.label ? ` — ${a.label}` : ""}</div>
                  <div className="account-detail">{a.is_testnet ? "Testnet" : "Mainnet"}</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="connection-status">
                    <span className={`conn-dot ${a.is_active ? "conn-active" : "conn-inactive"}`} />
                    {a.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {loadingAccounts && <div style={{ marginBottom: 20, color: "#4a6a80", fontSize: 13 }}><Spinner size={14} /> Loading accounts…</div>}

      {/* Add new accounts */}
      <div className="section-title">Add Broker Account</div>
      <div className="broker-grid">
        {/* MT5 */}
        <div className="broker-card">
          <div className="broker-header">
            <div className="broker-icon broker-forex">📈</div>
            <div>
              <div className="broker-name">MetaTrader 5</div>
              <div className="broker-sub">Forex & CFD execution</div>
            </div>
          </div>
          <InputField label="Broker Name" value={mt5Form.broker_name} onChange={v => setMt5Form(p => ({ ...p, broker_name: v }))} placeholder="e.g. IC Markets" error={mt5Errors.broker_name} />
          <InputField label="Server" value={mt5Form.server} onChange={v => setMt5Form(p => ({ ...p, server: v }))} placeholder="ICMarketsSC-Demo01" error={mt5Errors.server} />
          <InputField label="Account Number" value={mt5Form.account_number} onChange={v => setMt5Form(p => ({ ...p, account_number: v }))} placeholder="12345678" error={mt5Errors.account_number} />
          <InputField label="Password" type="password" value={mt5Form.password} onChange={v => setMt5Form(p => ({ ...p, password: v }))} placeholder="••••••••" error={mt5Errors.password} />
          <div className="notif-row" style={{ paddingTop: 8 }}>
            <div>
              <div className="notif-label">Demo Account</div>
              <div className="notif-sub">Disable when switching to live</div>
            </div>
            <button onClick={() => setMt5Form(p => ({ ...p, is_demo: !p.is_demo }))}
              className={`toggle-btn ${mt5Form.is_demo ? "toggle-on" : ""}`}>
              <div className="toggle-thumb" />
            </button>
          </div>
          <div style={{ marginTop: 4, padding: "8px 10px", background: "rgba(0,212,255,0.05)", borderRadius: 6, fontSize: 11, color: "#4a6a80" }}>
            🔒 Credentials are encrypted with AES-256-GCM before storage. We never store plaintext passwords.
          </div>
          <button className="btn btn-primary" style={{ width: "100%", marginTop: 14 }} disabled={savingMt5} onClick={connectMt5}>
            {savingMt5 ? <><Spinner size={14} /> Connecting…</> : "Connect MT5 Account"}
          </button>
        </div>

        {/* Crypto */}
        <div className="broker-card">
          <div className="broker-header">
            <div className="broker-icon broker-crypto">₿</div>
            <div>
              <div className="broker-name">Crypto Exchange</div>
              <div className="broker-sub">Spot & Futures via CCXT</div>
            </div>
          </div>
          <div className="form-field">
            <label>Exchange</label>
            <select value={cryptoForm.exchange} onChange={e => setCryptoForm(p => ({ ...p, exchange: e.target.value }))}>
              {["binance", "coinbase", "kraken", "bybit", "okx", "kucoin", "bitfinex", "huobi"].map(ex => (
                <option key={ex} value={ex}>{ex.charAt(0).toUpperCase() + ex.slice(1)}</option>
              ))}
            </select>
          </div>
          <InputField label="Label (optional)" value={cryptoForm.label} onChange={v => setCryptoForm(p => ({ ...p, label: v }))} placeholder="e.g. Main account" />
          <InputField label="API Key" value={cryptoForm.api_key} onChange={v => setCryptoForm(p => ({ ...p, api_key: v }))} placeholder="••••••••••••••••" error={cryptoErrors.api_key} />
          <InputField label="API Secret" type="password" value={cryptoForm.api_secret} onChange={v => setCryptoForm(p => ({ ...p, api_secret: v }))} placeholder="••••••••••••••••" error={cryptoErrors.api_secret} />
          <InputField label="Passphrase (if required)" type="password" value={cryptoForm.passphrase} onChange={v => setCryptoForm(p => ({ ...p, passphrase: v }))} placeholder="Required for OKX, KuCoin" />
          <div className="notif-row" style={{ paddingTop: 8 }}>
            <div>
              <div className="notif-label">Testnet / Sandbox</div>
              <div className="notif-sub">Disable when switching to mainnet</div>
            </div>
            <button onClick={() => setCryptoForm(p => ({ ...p, is_testnet: !p.is_testnet }))}
              className={`toggle-btn ${cryptoForm.is_testnet ? "toggle-on" : ""}`}>
              <div className="toggle-thumb" />
            </button>
          </div>
          <div style={{ marginTop: 4, padding: "8px 10px", background: "rgba(0,212,255,0.05)", borderRadius: 6, fontSize: 11, color: "#4a6a80" }}>
            🔒 API keys are encrypted with AES-256-GCM. Use read + trade permissions only — never withdrawal permission.
          </div>
          <button className="btn btn-primary" style={{ width: "100%", marginTop: 14 }} disabled={savingCrypto} onClick={connectCrypto}>
            {savingCrypto ? <><Spinner size={14} /> Connecting…</> : "Connect Exchange"}
          </button>
        </div>
      </div>
    </>
  );
}

// ── Notifications View ────────────────────────────────────────────

function NotificationsView({ userId, push }: { userId?: string; push: (msg: string, type?: Toast["type"]) => void }) {
  const [prefs, setPrefs] = useState<NotifPrefs>({
    telegram_chat_id: "", telegram_enabled: false,
    email_enabled: true, push_enabled: false,
    signal_alerts: true, trade_alerts: true, risk_alerts: true, news_alerts: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!userId) return;
    apiFetch<NotifPrefs>(`/api/notify/preferences/${userId}`).then(({ data, error }) => {
      if (data) setPrefs(data);
      if (error && !error.includes("404")) push(`Failed to load preferences: ${error}`, "error");
      setLoading(false);
    });
  }, [userId, push]);

  const update = <K extends keyof NotifPrefs>(key: K, value: NotifPrefs[K]) => {
    setPrefs(prev => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const save = async () => {
    if (!userId) return;
    setSaving(true);
    const { error } = await apiFetch(`/api/notify/preferences/${userId}`, {
      method: "PUT",
      body: JSON.stringify(prefs),
    });
    setSaving(false);
    if (error) { push(`Failed to save: ${error}`, "error"); return; }
    push("Notification preferences saved ✓", "success");
    setDirty(false);
  };

  if (loading) return <div className="loading-state"><Spinner size={24} /></div>;

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div className="section-title">Notification Preferences</div>
        <button className="btn btn-primary" style={{ flex: "none", width: "auto" }} disabled={!dirty || saving} onClick={save}>
          {saving ? <><Spinner size={14} /> Saving…</> : "Save Changes"}
        </button>
      </div>

      {/* Telegram */}
      <div className="alert-card">
        <div className="alert-title">📱 Telegram</div>
        <div className="notif-row">
          <div>
            <div className="notif-label">Enable Telegram alerts</div>
            <div className="notif-sub">Receive signals and trade updates in Telegram</div>
          </div>
          <button onClick={() => update("telegram_enabled", !prefs.telegram_enabled)}
            className={`toggle-btn ${prefs.telegram_enabled ? "toggle-on" : ""}`}>
            <div className="toggle-thumb" />
          </button>
        </div>
        {prefs.telegram_enabled && (
          <div className="form-field" style={{ marginTop: 12 }}>
            <label>Your Telegram Chat ID</label>
            <input
              type="text"
              value={prefs.telegram_chat_id || ""}
              placeholder="e.g. 123456789"
              onChange={e => update("telegram_chat_id", e.target.value)}
            />
            <div style={{ fontSize: 11, color: "#4a6a80", marginTop: 6, lineHeight: 1.5 }}>
              To get your Chat ID: message <strong style={{ color: "#8baabb" }}>@userinfobot</strong> on Telegram, then paste the ID here.
              Make sure to start a conversation with <strong style={{ color: "#8baabb" }}>@MeritTradeBot</strong> first.
            </div>
          </div>
        )}
      </div>

      {/* Email */}
      <div className="alert-card">
        <div className="alert-title">✉️ Email</div>
        <div className="notif-row">
          <div>
            <div className="notif-label">Enable email alerts</div>
            <div className="notif-sub">HTML digest sent to your registered email</div>
          </div>
          <button onClick={() => update("email_enabled", !prefs.email_enabled)}
            className={`toggle-btn ${prefs.email_enabled ? "toggle-on" : ""}`}>
            <div className="toggle-thumb" />
          </button>
        </div>
      </div>

      {/* Web Push */}
      <div className="alert-card">
        <div className="alert-title">🔔 Browser Push</div>
        <div className="notif-row">
          <div>
            <div className="notif-label">Enable browser push notifications</div>
            <div className="notif-sub">Real-time alerts even when the tab is in the background</div>
          </div>
          <button onClick={async () => {
            if (!prefs.push_enabled) {
              if (!("Notification" in window)) { push("Browser push not supported", "error"); return; }
              const perm = await Notification.requestPermission();
              if (perm !== "granted") { push("Push notifications denied by browser", "error"); return; }
            }
            update("push_enabled", !prefs.push_enabled);
          }} className={`toggle-btn ${prefs.push_enabled ? "toggle-on" : ""}`}>
            <div className="toggle-thumb" />
          </button>
        </div>
      </div>

      {/* Alert types */}
      <div className="alert-card">
        <div className="alert-title">Alert Types</div>
        {[
          { key: "signal_alerts" as const, label: "New signal alerts", desc: "Notify when a new ML signal is generated" },
          { key: "trade_alerts" as const, label: "Trade execution alerts", desc: "Notify when a trade is opened or closed" },
          { key: "risk_alerts" as const, label: "Risk gate alerts", desc: "Notify when a trade is blocked by the risk engine" },
          { key: "news_alerts" as const, label: "High-impact news alerts", desc: "Notify before high-impact economic events" },
        ].map(item => (
          <div key={item.key} className="notif-row">
            <div>
              <div className="notif-label">{item.label}</div>
              <div className="notif-sub">{item.desc}</div>
            </div>
            <button onClick={() => update(item.key, !prefs[item.key])}
              className={`toggle-btn ${prefs[item.key] ? "toggle-on" : ""}`}>
              <div className="toggle-thumb" />
            </button>
          </div>
        ))}
      </div>
    </>
  );
}
