"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

// ── Animated counter hook ──────────────────────────────────────────
function useCounter(target: number, duration = 2000, start = false) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!start) return;
    let startTime: number | null = null;
    const step = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      setCount(Math.floor(progress * target));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration, start]);
  return count;
}

// ── Types ──────────────────────────────────────────────────────────
interface PricingPlan {
  name: string;
  price: string;
  period: string;
  description: string;
  features: string[];
  cta: string;
  highlighted: boolean;
}

// ── Data ───────────────────────────────────────────────────────────
const PLANS: PricingPlan[] = [
  {
    name: "Free",
    price: "$0",
    period: "/month",
    description: "Start exploring AI-powered signals",
    features: [
      "View live trading signals",
      "AI-generated explanations",
      "Telegram & email alerts",
      "Basic portfolio stats",
      "Community access",
    ],
    cta: "Get started free",
    highlighted: false,
  },
  {
    name: "Pro",
    price: "$49",
    period: "/month",
    description: "Semi-automated trading for serious traders",
    features: [
      "Everything in Free",
      "Semi-auto trade execution",
      "MT5 & crypto exchange links",
      "Priority signal delivery",
      "Risk engine controls",
      "Web push notifications",
      "Advanced analytics",
    ],
    cta: "Start Pro trial",
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: "$149",
    period: "/month",
    description: "Full automation for professional desks",
    features: [
      "Everything in Pro",
      "Full auto-execution",
      "Multi-account management",
      "API access",
      "Custom risk thresholds",
      "Dedicated support",
      "SLA guarantee",
    ],
    cta: "Contact sales",
    highlighted: false,
  },
];

const FEATURES = [
  {
    icon: "🧠",
    title: "ML Ensemble Engine",
    body: "XGBoost, LSTM, and Transformer models combine in a weighted ensemble. Each signal carries a confidence score and a full model breakdown.",
  },
  {
    icon: "🛡️",
    title: "Hard-Rule Risk Gate",
    body: "Every trade passes an immutable rules engine before execution. Confidence thresholds, spread limits, drawdown caps, and R:R requirements enforced automatically.",
  },
  {
    icon: "⚡",
    title: "Multi-Asset Execution",
    body: "Connect your MetaTrader 5 account for Forex or link any CCXT-supported crypto exchange. Credentials encrypted with AES-256-GCM.",
  },
  {
    icon: "📡",
    title: "Real-Time Signals",
    body: "Live OHLCV ingestion with RSI, MACD, EMA, ATR, VWAP, and market structure analysis. Signals delivered over WebSocket with sub-second latency.",
  },
  {
    icon: "🤖",
    title: "AI Explanations",
    body: "Claude by Anthropic generates plain-language trade rationale for every signal — for insight only, never for execution decisions.",
  },
  {
    icon: "🔔",
    title: "Multi-Channel Alerts",
    body: "Instant Telegram messages, email digests, and browser push notifications. Customise by signal type, confidence level, or asset class.",
  },
  {
    icon: "📊",
    title: "Live Portfolio Dashboard",
    body: "Real-time equity curves, open trade P&L, drawdown monitor, win rate, and full execution history — all in one unified view.",
  },
  {
    icon: "🔒",
    title: "Enterprise Security",
    body: "bcrypt password hashing, short-lived JWTs, Redis token blacklisting, account lockout, role-based access, and full audit logs for every execution.",
  },
];

const TECH_STACK = [
  { layer: "API Gateway", tech: "FastAPI + Nginx", detail: "Rate limiting, JWT validation, WebSocket hub" },
  { layer: "ML Pipeline", tech: "XGBoost · LSTM · Transformer", detail: "PyTorch, scikit-learn, Celery workers" },
  { layer: "Market Data", tech: "TimescaleDB + Redis", detail: "OHLCV + 15 technical indicators" },
  { layer: "Execution", tech: "MT5 + CCXT", detail: "Forex & crypto, 100+ exchanges" },
  { layer: "Messaging", tech: "RabbitMQ + Celery", detail: "Async task queue, beat scheduler" },
  { layer: "Frontend", tech: "Next.js 14 + TypeScript", detail: "Real-time WebSocket, Recharts" },
];

// ── Nav ────────────────────────────────────────────────────────────
function Nav() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", fn);
    return () => window.removeEventListener("scroll", fn);
  }, []);

  return (
    <nav className={`nav${scrolled ? " nav--scrolled" : ""}`}>
      <div className="nav__inner">
        <div className="nav__brand">
          <span className="brand-icon">◈</span>
          <span className="brand-name">Merit<span>Trade</span> AI</span>
        </div>
        <div className="nav__links">
          <a href="#features">Features</a>
          <a href="#pipeline">Pipeline</a>
          <a href="#pricing">Pricing</a>
          <a href="#stack">Technology</a>
        </div>
        <div className="nav__actions">
          <Link href="/login" className="btn btn--ghost">Sign in</Link>
          <Link href="/register" className="btn btn--primary">Get started →</Link>
        </div>
      </div>
    </nav>
  );
}

// ── Hero ───────────────────────────────────────────────────────────
function Hero() {
  const [started, setStarted] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setStarted(true), 400);
    return () => clearTimeout(t);
  }, []);

  const winRate = useCounter(67, 1800, started);
  const signals = useCounter(2400, 1800, started);
  const rr = useCounter(18, 1400, started);

  return (
    <section className="hero">
      <div className="hero__glow hero__glow--1" />
      <div className="hero__glow hero__glow--2" />
      <div className="hero__content">
        <div className="hero__badge">
          <span className="pulse-dot" /> Live signals active
        </div>
        <h1 className="hero__headline">
          AI Trading Intelligence<br />
          <span className="hero__headline--accent">Built for Professionals</span>
        </h1>
        <p className="hero__sub">
          A production-grade platform combining XGBoost, LSTM, and Transformer models
          with a hard-rule risk engine — for Forex and crypto traders who demand precision.
        </p>
        <div className="hero__actions">
          <Link href="/register" className="btn btn--hero">Start trading free →</Link>
          <Link href="/dashboard" className="btn btn--outline">View live dashboard</Link>
        </div>
        <div className="hero__links">
          <Link href="/ai-reference" className="btn btn--outline">AI Reference</Link>
          <Link href="/privacy-policy" className="btn btn--ghost">Privacy Policy</Link>
          <Link href="/terms-of-service" className="btn btn--ghost">Terms of Service</Link>
        </div>
        <div className="hero__stats">
          <div className="hero__stat">
            <span className="stat-val">{winRate}%</span>
            <span className="stat-label">Historical win rate</span>
          </div>
          <div className="hero__divider" />
          <div className="hero__stat">
            <span className="stat-val">{signals.toLocaleString()}+</span>
            <span className="stat-label">Signals generated</span>
          </div>
          <div className="hero__divider" />
          <div className="hero__stat">
            <span className="stat-val">1:{rr}</span>
            <span className="stat-label">Avg risk/reward</span>
          </div>
        </div>
      </div>

      {/* Signal card preview */}
      <div className="hero__preview">
        <div className="signal-card">
          <div className="signal-card__header">
            <span className="signal-pair">EURUSD</span>
            <span className="signal-badge signal-badge--buy">BUY</span>
            <span className="signal-tf">1H</span>
          </div>
          <div className="signal-card__body">
            <div className="signal-row">
              <span>Entry</span><strong>1.0842</strong>
            </div>
            <div className="signal-row signal-row--sl">
              <span>Stop loss</span><strong>1.0810</strong>
            </div>
            <div className="signal-row signal-row--tp">
              <span>Take profit</span><strong>1.0910</strong>
            </div>
          </div>
          <div className="signal-card__models">
            <ModelBar label="XGBoost" value={81} />
            <ModelBar label="LSTM" value={74} />
            <ModelBar label="Transformer" value={76} />
          </div>
          <div className="signal-card__confidence">
            <div className="conf-arc" style={{ "--pct": "78%" } as React.CSSProperties}>
              <span>78%</span>
              <small>confidence</small>
            </div>
            <div className="signal-ai">
              <p>"EMA crossover on hourly chart with RSI recovering from oversold territory. MACD histogram turning positive."</p>
              <span>— AI Explanation</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ModelBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="model-bar">
      <span>{label}</span>
      <div className="model-bar__track">
        <div className="model-bar__fill" style={{ width: `${value}%` }} />
      </div>
      <span>{value}%</span>
    </div>
  );
}

// ── Pipeline ───────────────────────────────────────────────────────
function Pipeline() {
  const steps = [
    { label: "Market Data", sub: "OHLCV ingestion", icon: "📈" },
    { label: "Feature Eng.", sub: "15 indicators", icon: "⚙️" },
    { label: "ML Ensemble", sub: "XGB + LSTM + TF", icon: "🧠" },
    { label: "AI Explain", sub: "Claude API", icon: "💬" },
    { label: "Risk Gate", sub: "8 hard rules", icon: "🛡️" },
    { label: "Execute", sub: "MT5 or CCXT", icon: "⚡" },
  ];

  return (
    <section className="pipeline" id="pipeline">
      <div className="section-label">Trading Pipeline</div>
      <h2 className="section-title">From market data to executed trade</h2>
      <p className="section-sub">Every trade passes through six deterministic stages. The risk gate cannot be bypassed.</p>
      <div className="pipeline__steps">
        {steps.map((step, i) => (
          <div key={i} className="pipeline__step">
            <div className="pipeline__icon">{step.icon}</div>
            <div className="pipeline__label">{step.label}</div>
            <div className="pipeline__sub">{step.sub}</div>
            {i < steps.length - 1 && <div className="pipeline__arrow">→</div>}
          </div>
        ))}
      </div>
      <div className="pipeline__weights">
        <div className="weight-card">
          <span className="weight-pct">40%</span>
          <span className="weight-model">XGBoost</span>
          <span className="weight-desc">BUY/SELL/HOLD probability</span>
        </div>
        <span className="weight-op">+</span>
        <div className="weight-card">
          <span className="weight-pct">30%</span>
          <span className="weight-model">LSTM</span>
          <span className="weight-desc">Sequential direction</span>
        </div>
        <span className="weight-op">+</span>
        <div className="weight-card">
          <span className="weight-pct">30%</span>
          <span className="weight-model">Transformer</span>
          <span className="weight-desc">Multi-TF context</span>
        </div>
        <span className="weight-op">=</span>
        <div className="weight-card weight-card--total">
          <span className="weight-pct">Score</span>
          <span className="weight-model">Ensemble</span>
          <span className="weight-desc">Final confidence 0–100</span>
        </div>
      </div>
    </section>
  );
}

// ── Features ───────────────────────────────────────────────────────
function Features() {
  return (
    <section className="features" id="features">
      <div className="section-label">Platform Features</div>
      <h2 className="section-title">Everything you need to trade with edge</h2>
      <div className="features__grid">
        {FEATURES.map((f, i) => (
          <div key={i} className="feature-card">
            <div className="feature-card__icon">{f.icon}</div>
            <h3>{f.title}</h3>
            <p>{f.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ── Risk section ───────────────────────────────────────────────────
function RiskSection() {
  const rules = [
    "Confidence score ≥ threshold",
    "Spread within limit",
    "No high-impact news window",
    "Daily loss not exceeded",
    "Max drawdown within limit",
    "Max open trades not exceeded",
    "Valid SL/TP placement",
    "Risk/Reward ≥ 1.5",
  ];

  return (
    <section className="risk-section">
      <div className="risk-section__inner">
        <div className="risk-section__text">
          <div className="section-label">Risk Engine</div>
          <h2 className="section-title">A hard gate that cannot be bypassed</h2>
          <p>The risk engine is a deterministic, rules-based system — not AI. Every trade must satisfy all eight conditions simultaneously before the execution engine receives the order. If any rule fails, the trade is blocked and the user is notified with a specific rejection reason.</p>
          <Link href="/register" className="btn btn--primary" style={{ marginTop: "2rem", display: "inline-block" }}>
            Configure your risk settings →
          </Link>
        </div>
        <div className="risk-section__rules">
          {rules.map((rule, i) => (
            <div key={i} className="risk-rule">
              <span className="risk-rule__check">✓</span>
              <span>{rule}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Pricing ────────────────────────────────────────────────────────
function Pricing() {
  return (
    <section className="pricing" id="pricing">
      <div className="section-label">Pricing</div>
      <h2 className="section-title">Start free. Scale when you&apos;re ready.</h2>
      <p className="section-sub">All plans include live signals, AI explanations, and Telegram alerts.</p>
      <div className="pricing__grid">
        {PLANS.map((plan, i) => (
          <div key={i} className={`pricing-card${plan.highlighted ? " pricing-card--highlighted" : ""}`}>
            {plan.highlighted && <div className="pricing-card__badge">Most popular</div>}
            <div className="pricing-card__name">{plan.name}</div>
            <div className="pricing-card__price">
              {plan.price}<span>{plan.period}</span>
            </div>
            <p className="pricing-card__desc">{plan.description}</p>
            <ul className="pricing-card__features">
              {plan.features.map((f, fi) => (
                <li key={fi}><span>✓</span>{f}</li>
              ))}
            </ul>
            <Link href="/register" className={`btn ${plan.highlighted ? "btn--primary" : "btn--outline"}`}>
              {plan.cta}
            </Link>
          </div>
        ))}
      </div>
    </section>
  );
}

// ── Tech Stack ─────────────────────────────────────────────────────
function TechStack() {
  return (
    <section className="tech-stack" id="stack">
      <div className="section-label">Technology</div>
      <h2 className="section-title">Production-grade microservices architecture</h2>
      <div className="tech-stack__grid">
        {TECH_STACK.map((t, i) => (
          <div key={i} className="tech-row">
            <div className="tech-row__layer">{t.layer}</div>
            <div className="tech-row__tech">{t.tech}</div>
            <div className="tech-row__detail">{t.detail}</div>
          </div>
        ))}
      </div>
      <div className="tech-stack__services">
        {["api-gateway", "auth-service", "signal-engine", "market-data", "execution-engine", "risk-engine", "notification-service", "admin-service"].map((s) => (
          <span key={s} className="service-pill">{s}</span>
        ))}
      </div>
    </section>
  );
}

// ── Disclaimer ─────────────────────────────────────────────────────
function Disclaimer() {
  return (
    <div className="disclaimer">
      ⚠️ <strong>Risk Disclaimer:</strong> Trading involves substantial risk of loss. Merit-Trade AI is a technology platform, not financial advice. Always test on demo accounts before using real capital. Regulatory compliance is your responsibility.
    </div>
  );
}

// ── Footer ─────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <div className="footer__brand">
          <span className="brand-icon">◈</span>
          <span className="brand-name">Merit<span>Trade</span> AI</span>
        </div>
        <div className="footer__links">
          <Link href="/ai-reference">AI Reference</Link>
          <Link href="/privacy-policy">Privacy Policy</Link>
          <Link href="/terms-of-service">Terms of Service</Link>
        </div>
        <p className="footer__copy">© {new Date().getFullYear()} Merit-Trade AI. All rights reserved. Proprietary.</p>
      </div>
    </footer>
  );
}

// ── Main ───────────────────────────────────────────────────────────
export default function LandingPage() {
  return (
    <>
      <style>{`
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        html { scroll-behavior: smooth; }
        body {
          font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
          background: #070b14;
          color: #e2e8f0;
          line-height: 1.6;
          overflow-x: hidden;
        }

        /* ── NAV ── */
        .nav {
          position: fixed; top: 0; left: 0; right: 0; z-index: 100;
          padding: 1rem 2rem;
          transition: background 0.3s, border-color 0.3s;
        }
        .nav--scrolled {
          background: rgba(7, 11, 20, 0.92);
          backdrop-filter: blur(12px);
          border-bottom: 1px solid rgba(99, 179, 237, 0.12);
        }
        .nav__inner {
          max-width: 1200px; margin: 0 auto;
          display: flex; align-items: center; gap: 2rem;
        }
        .nav__brand { display: flex; align-items: center; gap: 0.5rem; font-weight: 700; font-size: 1.1rem; }
        .brand-icon { color: #63b3ed; font-size: 1.4rem; }
        .brand-name span { color: #63b3ed; }
        .nav__links { display: flex; gap: 2rem; flex: 1; margin-left: 2rem; }
        .nav__links a { color: #94a3b8; text-decoration: none; font-size: 0.9rem; transition: color 0.2s; }
        .nav__links a:hover { color: #e2e8f0; }
        .nav__actions { display: flex; gap: 0.75rem; margin-left: auto; }

        /* ── BUTTONS ── */
        .btn {
          padding: 0.6rem 1.25rem; border-radius: 8px; font-size: 0.9rem;
          font-weight: 500; cursor: pointer; text-decoration: none;
          display: inline-flex; align-items: center; gap: 0.4rem;
          transition: all 0.2s;
        }
        .btn--ghost { color: #94a3b8; border: 1px solid transparent; background: transparent; }
        .btn--ghost:hover { color: #e2e8f0; background: rgba(255,255,255,0.05); }
        .btn--primary {
          background: #63b3ed; color: #0a1628; border: 1px solid #63b3ed;
        }
        .btn--primary:hover { background: #90cdf4; border-color: #90cdf4; }
        .btn--outline { border: 1px solid rgba(99,179,237,0.4); color: #63b3ed; background: transparent; }
        .btn--outline:hover { background: rgba(99,179,237,0.08); }
        .hero__links {
          display: flex;
          flex-wrap: wrap;
          justify-content: center;
          gap: 0.85rem;
          margin: 1rem auto 0;
          max-width: 560px;
        }
        .hero__links .btn { min-width: 150px; justify-content: center; }
        .btn--hero {
          background: #63b3ed; color: #0a1628; border: none;
          padding: 0.9rem 2rem; font-size: 1rem; border-radius: 10px;
        }
        .btn--hero:hover { background: #90cdf4; transform: translateY(-1px); }

        /* ── HERO ── */
        .hero {
          min-height: 100vh; display: flex; align-items: center;
          padding: 7rem 2rem 4rem;
          max-width: 1200px; margin: 0 auto;
          gap: 4rem; position: relative;
        }
        .hero__glow {
          position: fixed; border-radius: 50%; filter: blur(80px);
          pointer-events: none; opacity: 0.15;
        }
        .hero__glow--1 {
          width: 600px; height: 600px; top: -100px; left: -200px;
          background: radial-gradient(circle, #63b3ed, transparent);
        }
        .hero__glow--2 {
          width: 400px; height: 400px; bottom: 100px; right: -100px;
          background: radial-gradient(circle, #4299e1, transparent);
        }
        .hero__content { flex: 1; min-width: 0; }
        .hero__badge {
          display: inline-flex; align-items: center; gap: 0.5rem;
          padding: 0.4rem 0.9rem; border-radius: 100px;
          border: 1px solid rgba(99,179,237,0.3);
          background: rgba(99,179,237,0.06);
          color: #63b3ed; font-size: 0.82rem; margin-bottom: 1.5rem;
        }
        .pulse-dot {
          width: 8px; height: 8px; border-radius: 50%; background: #48bb78;
          animation: pulse 2s infinite;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.85); }
        }
        .hero__headline {
          font-size: clamp(2.2rem, 5vw, 3.4rem); font-weight: 700;
          line-height: 1.15; margin-bottom: 1.25rem; color: #f1f5f9;
        }
        .hero__headline--accent {
          background: linear-gradient(135deg, #63b3ed, #4299e1);
          -webkit-background-clip: text; -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .hero__sub { color: #94a3b8; font-size: 1.05rem; max-width: 520px; margin-bottom: 2rem; }
        .hero__actions { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 2.5rem; }
        .hero__stats { display: flex; align-items: center; gap: 1.5rem; }
        .hero__stat { text-align: center; }
        .stat-val { display: block; font-size: 1.8rem; font-weight: 700; color: #63b3ed; }
        .stat-label { font-size: 0.8rem; color: #64748b; }
        .hero__divider { width: 1px; height: 40px; background: rgba(99,179,237,0.2); }

        /* ── SIGNAL CARD ── */
        .hero__preview { flex: 0 0 340px; }
        .signal-card {
          background: rgba(15, 23, 42, 0.9);
          border: 1px solid rgba(99,179,237,0.2);
          border-radius: 16px; padding: 1.25rem;
          backdrop-filter: blur(20px);
        }
        .signal-card__header {
          display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem;
        }
        .signal-pair { font-size: 1.1rem; font-weight: 700; color: #f1f5f9; flex: 1; }
        .signal-badge {
          padding: 0.2rem 0.6rem; border-radius: 6px; font-size: 0.8rem; font-weight: 700;
        }
        .signal-badge--buy { background: rgba(72,187,120,0.15); color: #48bb78; border: 1px solid rgba(72,187,120,0.3); }
        .signal-badge--sell { background: rgba(252,129,74,0.15); color: #fc814a; border: 1px solid rgba(252,129,74,0.3); }
        .signal-tf { font-size: 0.8rem; color: #64748b; border: 1px solid rgba(100,116,139,0.3); padding: 0.15rem 0.5rem; border-radius: 4px; }
        .signal-card__body { display: flex; flex-direction: column; gap: 0.4rem; margin-bottom: 1rem; }
        .signal-row {
          display: flex; justify-content: space-between; align-items: center;
          font-size: 0.88rem;
        }
        .signal-row span { color: #64748b; }
        .signal-row strong { color: #e2e8f0; }
        .signal-row--sl strong { color: #fc8181; }
        .signal-row--tp strong { color: #48bb78; }
        .signal-card__models { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 1rem; }
        .model-bar { display: flex; align-items: center; gap: 0.5rem; font-size: 0.78rem; }
        .model-bar span:first-child { width: 80px; color: #64748b; }
        .model-bar span:last-child { width: 32px; text-align: right; color: #94a3b8; }
        .model-bar__track { flex: 1; height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px; }
        .model-bar__fill { height: 100%; background: #63b3ed; border-radius: 2px; transition: width 1s ease; }
        .signal-card__confidence { display: flex; align-items: center; gap: 1rem; }
        .conf-arc {
          width: 72px; height: 72px; border-radius: 50%;
          background: conic-gradient(#63b3ed var(--pct), rgba(99,179,237,0.1) var(--pct));
          display: flex; flex-direction: column; align-items: center; justify-content: center;
          position: relative; flex-shrink: 0;
        }
        .conf-arc::before {
          content: ''; position: absolute; inset: 6px;
          border-radius: 50%; background: #0f172a;
        }
        .conf-arc span { font-size: 1rem; font-weight: 700; color: #63b3ed; z-index: 1; line-height: 1; }
        .conf-arc small { font-size: 0.6rem; color: #64748b; z-index: 1; }
        .signal-ai p { font-size: 0.78rem; color: #94a3b8; font-style: italic; line-height: 1.5; }
        .signal-ai span { font-size: 0.72rem; color: #63b3ed; }

        /* ── SECTIONS COMMON ── */
        .section-label {
          font-size: 0.8rem; font-weight: 600; letter-spacing: 0.12em;
          text-transform: uppercase; color: #63b3ed; margin-bottom: 0.75rem;
        }
        .section-title {
          font-size: clamp(1.6rem, 3vw, 2.2rem); font-weight: 700;
          color: #f1f5f9; margin-bottom: 1rem;
        }
        .section-sub { color: #94a3b8; max-width: 540px; margin-bottom: 3rem; }

        /* ── PIPELINE ── */
        .pipeline {
          padding: 5rem 2rem;
          max-width: 1200px; margin: 0 auto;
        }
        .pipeline__steps {
          display: flex; align-items: center; flex-wrap: wrap; gap: 1rem;
          margin-bottom: 3rem; position: relative;
        }
        .pipeline__step {
          display: flex; flex-direction: column; align-items: center; gap: 0.35rem;
          background: rgba(15,23,42,0.8); border: 1px solid rgba(99,179,237,0.15);
          border-radius: 12px; padding: 1.25rem 1rem; position: relative;
          min-width: 120px;
        }
        .pipeline__icon { font-size: 1.5rem; }
        .pipeline__label { font-size: 0.85rem; font-weight: 600; color: #e2e8f0; text-align: center; }
        .pipeline__sub { font-size: 0.72rem; color: #64748b; text-align: center; }
        .pipeline__arrow { font-size: 1.2rem; color: #4a5568; align-self: center; }
        .pipeline__weights {
          display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
          background: rgba(15,23,42,0.6); border: 1px solid rgba(99,179,237,0.1);
          border-radius: 12px; padding: 1.5rem;
        }
        .weight-card {
          display: flex; flex-direction: column; align-items: center; gap: 0.25rem;
          flex: 1; min-width: 120px;
        }
        .weight-pct { font-size: 1.5rem; font-weight: 700; color: #63b3ed; }
        .weight-model { font-size: 0.9rem; font-weight: 600; color: #e2e8f0; }
        .weight-desc { font-size: 0.75rem; color: #64748b; text-align: center; }
        .weight-op { font-size: 1.5rem; color: #4a5568; }
        .weight-card--total .weight-pct { color: #48bb78; }

        /* ── FEATURES ── */
        .features {
          padding: 5rem 2rem;
          background: rgba(7,11,20,0.5);
        }
        .features > * { max-width: 1200px; margin-left: auto; margin-right: auto; }
        .features__grid {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 1.5rem; max-width: 1200px; margin: 0 auto;
        }
        .feature-card {
          background: rgba(15,23,42,0.7); border: 1px solid rgba(99,179,237,0.1);
          border-radius: 12px; padding: 1.5rem;
          transition: border-color 0.2s, transform 0.2s;
        }
        .feature-card:hover { border-color: rgba(99,179,237,0.3); transform: translateY(-2px); }
        .feature-card__icon { font-size: 1.75rem; margin-bottom: 0.75rem; }
        .feature-card h3 { font-size: 1rem; font-weight: 600; color: #f1f5f9; margin-bottom: 0.5rem; }
        .feature-card p { font-size: 0.88rem; color: #94a3b8; line-height: 1.65; }

        /* ── RISK SECTION ── */
        .risk-section {
          padding: 5rem 2rem;
          max-width: 1200px; margin: 0 auto;
        }
        .risk-section__inner {
          display: flex; gap: 4rem; align-items: flex-start; flex-wrap: wrap;
        }
        .risk-section__text { flex: 1; min-width: 280px; }
        .risk-section__text p { color: #94a3b8; margin-bottom: 1rem; }
        .risk-section__rules { flex: 0 0 340px; display: flex; flex-direction: column; gap: 0.75rem; }
        .risk-rule {
          display: flex; align-items: center; gap: 0.75rem;
          background: rgba(72,187,120,0.05); border: 1px solid rgba(72,187,120,0.15);
          border-radius: 8px; padding: 0.75rem 1rem; font-size: 0.9rem;
        }
        .risk-rule__check { color: #48bb78; font-weight: 700; }

        /* ── PRICING ── */
        .pricing {
          padding: 5rem 2rem;
          background: rgba(7,11,20,0.5);
          text-align: center;
        }
        .pricing > .section-label, .pricing > .section-title, .pricing > .section-sub {
          margin-left: auto; margin-right: auto;
        }
        .pricing__grid {
          display: flex; gap: 1.5rem; max-width: 1000px; margin: 0 auto;
          flex-wrap: wrap; justify-content: center;
        }
        .pricing-card {
          flex: 1; min-width: 260px; max-width: 320px;
          background: rgba(15,23,42,0.8); border: 1px solid rgba(99,179,237,0.12);
          border-radius: 16px; padding: 2rem; text-align: left;
          position: relative;
        }
        .pricing-card--highlighted {
          border-color: #63b3ed;
          background: rgba(99,179,237,0.05);
        }
        .pricing-card__badge {
          position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
          background: #63b3ed; color: #0a1628; font-size: 0.75rem; font-weight: 700;
          padding: 0.2rem 0.8rem; border-radius: 100px;
        }
        .pricing-card__name { font-size: 0.85rem; font-weight: 600; color: #63b3ed; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.08em; }
        .pricing-card__price { font-size: 2.2rem; font-weight: 700; color: #f1f5f9; margin-bottom: 0.25rem; }
        .pricing-card__price span { font-size: 1rem; color: #64748b; }
        .pricing-card__desc { font-size: 0.85rem; color: #94a3b8; margin-bottom: 1.5rem; }
        .pricing-card__features { list-style: none; margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: 0.5rem; }
        .pricing-card__features li { display: flex; gap: 0.6rem; font-size: 0.88rem; color: #cbd5e1; }
        .pricing-card__features li span { color: #48bb78; }
        .pricing-card .btn { width: 100%; justify-content: center; }

        /* ── TECH STACK ── */
        .tech-stack {
          padding: 5rem 2rem; max-width: 1200px; margin: 0 auto;
        }
        .tech-stack__grid { margin-bottom: 2rem; border: 1px solid rgba(99,179,237,0.12); border-radius: 12px; overflow: hidden; }
        .tech-row {
          display: grid; grid-template-columns: 1fr 1.5fr 2fr;
          gap: 1.5rem; padding: 1rem 1.5rem;
          border-bottom: 1px solid rgba(99,179,237,0.08);
          align-items: center;
        }
        .tech-row:last-child { border-bottom: none; }
        .tech-row:nth-child(odd) { background: rgba(15,23,42,0.4); }
        .tech-row__layer { font-size: 0.82rem; font-weight: 600; color: #63b3ed; }
        .tech-row__tech { font-size: 0.9rem; color: #e2e8f0; font-weight: 500; }
        .tech-row__detail { font-size: 0.82rem; color: #64748b; }
        .tech-stack__services { display: flex; flex-wrap: wrap; gap: 0.5rem; }
        .service-pill {
          padding: 0.3rem 0.8rem; border-radius: 100px;
          border: 1px solid rgba(99,179,237,0.2); font-size: 0.78rem;
          color: #63b3ed; background: rgba(99,179,237,0.05);
          font-family: 'JetBrains Mono', monospace;
        }

        /* ── DISCLAIMER ── */
        .disclaimer {
          max-width: 1000px; margin: 3rem auto; padding: 1rem 1.5rem;
          background: rgba(251,191,36,0.05); border: 1px solid rgba(251,191,36,0.2);
          border-radius: 8px; font-size: 0.82rem; color: #a8945a;
          text-align: center;
        }

        /* ── FOOTER ── */
        .footer {
          border-top: 1px solid rgba(99,179,237,0.1);
          padding: 2.5rem 2rem;
        }
        .footer__inner {
          max-width: 1200px; margin: 0 auto;
          display: flex; align-items: center; gap: 2rem; flex-wrap: wrap;
        }
        .footer__links { display: flex; gap: 1.5rem; flex-wrap: wrap; }
        .footer__links a { color: #64748b; font-size: 0.85rem; text-decoration: none; }
        .footer__links a:hover { color: #94a3b8; }
        .footer__copy { margin-left: auto; font-size: 0.8rem; color: #475569; }

        @media (max-width: 768px) {
          .hero { flex-direction: column; }
          .hero__preview { display: none; }
          .nav__links { display: none; }
          .risk-section__inner { flex-direction: column; }
          .risk-section__rules { flex: 1; width: 100%; }
        }
      `}</style>

      <link
        href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
        rel="stylesheet"
      />

      <Nav />
      <Hero />
      <Pipeline />
      <Features />
      <RiskSection />
      <Pricing />
      <TechStack />
      <Disclaimer />
      <Footer />
    </>
  );
}
