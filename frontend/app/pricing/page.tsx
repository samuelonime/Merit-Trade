"use client";

import { useState } from "react";
import Link from "next/link";
import { token } from "@/lib/api";

const STYLES = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #050a14; color: #e2f0ff; font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; }
  .nav { display: flex; align-items: center; justify-content: space-between; padding: 1.25rem 2rem; border-bottom: 1px solid #0d1f35; max-width: 1100px; margin: 0 auto; }
  .logo { display: flex; align-items: center; gap: 10px; text-decoration: none; color: inherit; }
  .logo-icon { width: 36px; height: 36px; background: linear-gradient(135deg, #00d4ff, #0095c8); border-radius: 9px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 18px; color: #000; }
  .logo-text { font-size: 1.1rem; font-weight: 700; }
  .logo-text span { color: #00d4ff; }
  .nav-links { display: flex; gap: .75rem; }
  .btn { padding: .6rem 1.25rem; border-radius: 8px; font-size: .875rem; font-weight: 600; cursor: pointer; transition: all .15s; border: none; text-decoration: none; display: inline-flex; align-items: center; }
  .btn-ghost { background: transparent; color: #8baabb; border: 1px solid #1a3050; }
  .btn-ghost:hover { color: #e2f0ff; border-color: #2a5080; }
  .btn-primary { background: #00d4ff; color: #000; }
  .btn-primary:hover { background: #00f0ff; transform: translateY(-1px); }
  .hero { text-align: center; padding: 5rem 1.5rem 3.5rem; max-width: 680px; margin: 0 auto; }
  .hero h1 { font-size: clamp(1.8rem, 4vw, 2.8rem); font-weight: 800; line-height: 1.15; margin-bottom: 1rem; }
  .hero h1 span { color: #00d4ff; }
  .hero p { font-size: 1.05rem; color: #4a6a80; line-height: 1.7; }
  .toggle-wrap { display: flex; align-items: center; justify-content: center; gap: .75rem; margin: 2rem 0; font-size: .875rem; color: #4a6a80; }
  .toggle { position: relative; width: 48px; height: 26px; }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .toggle-slider { position: absolute; inset: 0; background: #0d1f35; border: 1px solid #1a3050; border-radius: 13px; cursor: pointer; transition: .2s; }
  .toggle-slider::before { content: ""; position: absolute; width: 18px; height: 18px; left: 3px; top: 3px; background: #4a6a80; border-radius: 50%; transition: .2s; }
  input:checked + .toggle-slider { background: rgba(0,212,255,.15); border-color: #00d4ff; }
  input:checked + .toggle-slider::before { transform: translateX(22px); background: #00d4ff; }
  .save-badge { background: rgba(0,230,118,.1); color: #00e676; border: 1px solid rgba(0,230,118,.2); border-radius: 20px; padding: 2px 10px; font-size: .75rem; font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; max-width: 1000px; margin: 0 auto 4rem; padding: 0 1.5rem; }
  .card { background: #0d1f35; border: 1px solid #1a3050; border-radius: 16px; padding: 2rem; position: relative; }
  .card.featured { border-color: #00d4ff; box-shadow: 0 0 0 1px rgba(0,212,255,.15), 0 20px 60px rgba(0,212,255,.08); }
  .popular-badge { position: absolute; top: -12px; left: 50%; transform: translateX(-50%); background: #00d4ff; color: #000; font-size: .7rem; font-weight: 800; letter-spacing: .1em; padding: 4px 14px; border-radius: 20px; white-space: nowrap; }
  .plan-name { font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .1em; color: #4a6a80; margin-bottom: .5rem; }
  .plan-name.pro { color: #00d4ff; }
  .plan-name.enterprise { color: #a78bfa; }
  .price { font-size: 2.5rem; font-weight: 800; line-height: 1; margin-bottom: .25rem; }
  .price sup { font-size: 1.2rem; vertical-align: top; margin-top: .4rem; color: #8baabb; }
  .price-period { font-size: .8rem; color: #4a6a80; margin-bottom: 1.25rem; }
  .plan-desc { font-size: .875rem; color: #4a6a80; margin-bottom: 1.5rem; line-height: 1.5; padding-bottom: 1.5rem; border-bottom: 1px solid #1a3050; }
  .features { list-style: none; margin-bottom: 2rem; display: flex; flex-direction: column; gap: .625rem; }
  .features li { display: flex; align-items: flex-start; gap: .6rem; font-size: .875rem; color: #8baabb; line-height: 1.4; }
  .features li.yes { color: #c8dff0; }
  .features li.no { color: #2a4060; }
  .check { font-size: .8rem; flex-shrink: 0; margin-top: 1px; }
  .cta-btn { width: 100%; padding: .75rem; border-radius: 8px; border: none; font-size: .9rem; font-weight: 700; cursor: pointer; transition: all .15s; }
  .cta-free { background: transparent; border: 1px solid #1f3d60; color: #8baabb; }
  .cta-free:hover { border-color: #00d4ff; color: #00d4ff; }
  .cta-pro { background: #00d4ff; color: #000; }
  .cta-pro:hover { background: #00f0ff; transform: translateY(-1px); }
  .cta-enterprise { background: transparent; border: 1px solid #a78bfa; color: #a78bfa; }
  .cta-enterprise:hover { background: rgba(167,139,250,.08); transform: translateY(-1px); }
  .faq { max-width: 680px; margin: 0 auto 5rem; padding: 0 1.5rem; }
  .faq h2 { font-size: 1.5rem; font-weight: 700; text-align: center; margin-bottom: 2rem; }
  .faq-item { border-bottom: 1px solid #0d1f35; }
  .faq-q { width: 100%; background: none; border: none; color: #e2f0ff; font-size: .95rem; font-weight: 500; text-align: left; padding: 1.1rem 0; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
  .faq-q:hover { color: #00d4ff; }
  .faq-a { font-size: .875rem; color: #4a6a80; line-height: 1.7; padding-bottom: 1rem; }
  .footer { text-align: center; padding: 2rem; font-size: .8rem; color: #2a4060; border-top: 1px solid #0d1f35; }
  .footer a { color: #4a6a80; text-decoration: none; }
  .footer a:hover { color: #00d4ff; }
`;

const PLANS = [
  {
    key: "free",
    name: "Free Trial",
    nameClass: "",
    monthlyPrice: 0,
    annualPrice: 0,
    desc: "Get started with AI signals on the most popular pairs. No credit card required.",
    cta: "Start free",
    ctaClass: "cta-free",
    featured: false,
    features: [
      { yes: true,  text: "2 trading pairs (EURUSD + BTCUSDT)" },
      { yes: true,  text: "1H timeframe only" },
      { yes: true,  text: "Up to 3 open trades" },
      { yes: true,  text: "Basic risk controls" },
      { yes: true,  text: "Email notifications" },
      { yes: false, text: "All 8 trading pairs" },
      { yes: false, text: "Multi-timeframe signals (M15 → D1)" },
      { yes: false, text: "AI signal explanations" },
      { yes: false, text: "Auto-trade execution" },
      { yes: false, text: "Telegram & push notifications" },
    ],
  },
  {
    key: "pro",
    name: "Pro",
    nameClass: "pro",
    monthlyPrice: 49,
    annualPrice: 39,
    desc: "Full access to all pairs, timeframes, and automated execution. Designed for active traders.",
    cta: "Upgrade to Pro",
    ctaClass: "cta-pro",
    featured: true,
    features: [
      { yes: true, text: "All 8 trading pairs (Forex + Crypto + Gold)" },
      { yes: true, text: "All timeframes — M15, H1, H4, D1" },
      { yes: true, text: "Up to 20 open trades" },
      { yes: true, text: "Advanced risk engine with hard blocks" },
      { yes: true, text: "AI signal explanations & sentiment" },
      { yes: true, text: "Auto-trade execution (MT5 + CCXT)" },
      { yes: true, text: "Telegram, email & browser push" },
      { yes: true, text: "Real-time WebSocket price feeds" },
      { yes: true, text: "Full trade history & PnL analytics" },
      { yes: false, text: "Dedicated account manager" },
    ],
  },
  {
    key: "enterprise",
    name: "Enterprise",
    nameClass: "enterprise",
    monthlyPrice: null,
    annualPrice: null,
    desc: "Custom limits, dedicated support, and white-label options for funds and prop firms.",
    cta: "Contact sales",
    ctaClass: "cta-enterprise",
    featured: false,
    features: [
      { yes: true, text: "Everything in Pro" },
      { yes: true, text: "Unlimited open trades" },
      { yes: true, text: "Dedicated account manager" },
      { yes: true, text: "Custom risk rule configuration" },
      { yes: true, text: "White-label & API access" },
      { yes: true, text: "SLA uptime guarantee" },
      { yes: true, text: "Priority signal processing" },
      { yes: true, text: "Team seats & permissions" },
      { yes: true, text: "On-boarding & strategy support" },
      { yes: true, text: "Custom integrations" },
    ],
  },
];

const FAQS = [
  {
    q: "Do I need a credit card for the free trial?",
    a: "No — the free trial is completely free with no card required. You get access to EURUSD and BTCUSDT signals on the 1H timeframe, up to 3 open trades, and basic risk controls.",
  },
  {
    q: "Which brokers and exchanges are supported?",
    a: "For Forex/CFD trading we integrate with any MT5-compatible broker. For crypto we support Binance, Bybit, OKX, Kraken, Coinbase Advanced, KuCoin, Gate.io, and MEXC via the CCXT library.",
  },
  {
    q: "How does auto-trade work? Is my money safe?",
    a: "Auto-trade sends orders to your connected broker/exchange on your behalf when a qualifying signal is generated. Your broker credentials are encrypted with AES-256-GCM before storage and are never logged in plaintext. The risk engine enforces hard limits (max loss, max spread, news filter) regardless of auto-trade status — trades that exceed your limits are blocked server-side.",
  },
  {
    q: "Can I cancel my Pro subscription at any time?",
    a: "Yes. Cancel any time from your account settings. You keep Pro access until the end of your billing period, then automatically revert to the free tier.",
  },
  {
    q: "What is the difference between monthly and annual billing?",
    a: "Annual billing is billed as one payment for the year and saves you ~20% compared to month-to-month pricing. You can switch between billing periods at renewal.",
  },
];

export default function PricingPage() {
  const [annual, setAnnual] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const isLoggedIn = typeof window !== "undefined" && !!token.access;

  const handleCta = (planKey: string) => {
    if (planKey === "free") {
      window.location.href = isLoggedIn ? "/dashboard" : "/register";
    } else if (planKey === "enterprise") {
      window.location.href = "mailto:sales@merittrade.ai?subject=Enterprise%20inquiry";
    } else {
      // Pro — redirect to billing (stub: replace with Stripe checkout URL)
      window.location.href = isLoggedIn ? "/dashboard?upgrade=pro" : "/register?plan=pro";
    }
  };

  return (
    <>
      <style>{STYLES}</style>

      {/* Nav */}
      <nav className="nav">
        <Link href="/" className="logo">
          <div className="logo-icon">M</div>
          <div className="logo-text">Merit<span>Trade</span> AI</div>
        </Link>
        <div className="nav-links">
          {isLoggedIn
            ? <Link href="/dashboard" className="btn btn-primary">Dashboard</Link>
            : <>
                <Link href="/login" className="btn btn-ghost">Sign in</Link>
                <Link href="/register" className="btn btn-primary">Get started free</Link>
              </>
          }
        </div>
      </nav>

      {/* Hero */}
      <div className="hero">
        <h1>Simple, transparent<br /><span>pricing for every trader</span></h1>
        <p>Start free. Upgrade when you&apos;re ready. No hidden fees, no lock-in.</p>
      </div>

      {/* Billing toggle */}
      <div className="toggle-wrap">
        <span>Monthly</span>
        <label className="toggle">
          <input type="checkbox" checked={annual} onChange={e => setAnnual(e.target.checked)} />
          <div className="toggle-slider" />
        </label>
        <span>Annual</span>
        {annual && <span className="save-badge">Save ~20%</span>}
      </div>

      {/* Plan cards */}
      <div className="grid">
        {PLANS.map(plan => {
          const price = plan.monthlyPrice === null
            ? null
            : annual ? plan.annualPrice : plan.monthlyPrice;

          return (
            <div key={plan.key} className={`card${plan.featured ? " featured" : ""}`}>
              {plan.featured && <div className="popular-badge">MOST POPULAR</div>}
              <div className={`plan-name ${plan.nameClass}`}>{plan.name}</div>

              <div className="price">
                {price === null
                  ? <span style={{ fontSize: "1.6rem" }}>Custom</span>
                  : price === 0
                    ? <span>Free</span>
                    : <><sup>$</sup>{price}</>
                }
              </div>
              <div className="price-period">
                {price === null ? "Contact us for a quote"
                  : price === 0 ? "no credit card required"
                  : annual ? "/ month, billed annually" : "/ month, billed monthly"}
              </div>

              <div className="plan-desc">{plan.desc}</div>

              <ul className="features">
                {plan.features.map((f, i) => (
                  <li key={i} className={f.yes ? "yes" : "no"}>
                    <span className="check">{f.yes ? "✓" : "✗"}</span>
                    {f.text}
                  </li>
                ))}
              </ul>

              <button className={`cta-btn ${plan.ctaClass}`} onClick={() => handleCta(plan.key)}>
                {plan.cta}
              </button>
            </div>
          );
        })}
      </div>

      {/* FAQ */}
      <div className="faq">
        <h2>Frequently asked questions</h2>
        {FAQS.map((faq, i) => (
          <div key={i} className="faq-item">
            <button className="faq-q" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
              {faq.q}
              <span style={{ color: "#4a6a80", flexShrink: 0 }}>{openFaq === i ? "−" : "+"}</span>
            </button>
            {openFaq === i && <div className="faq-a">{faq.a}</div>}
          </div>
        ))}
      </div>

      <div className="footer">
        <p>© {new Date().getFullYear()} Merit-Trade AI · <Link href="/login">Sign in</Link> · <Link href="/register">Register</Link></p>
      </div>
    </>
  );
}
