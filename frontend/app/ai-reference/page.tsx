"use client";

import Link from "next/link";

export default function AIReferencePage() {
  return (
    <main className="doc-page">
      <div className="doc-header">
        <div>
          <p className="eyebrow">AI Reference</p>
          <h1>How AI powers Merit-Trade AI</h1>
          <p className="doc-sub">A technical overview of signal generation, model ensembles, and explainability in the platform.</p>
        </div>
        <Link href="/" className="btn btn--outline">Back to home</Link>
      </div>

      <section>
        <h2>Signal generation workflow</h2>
        <p>Merit-Trade AI combines live market data, feature engineering, and machine learning to generate trading signals with confidence scores and supporting rationale.</p>
      </section>

      <section>
        <h2>Model ensemble</h2>
        <p>The platform uses three primary models:</p>
        <ul>
          <li><strong>XGBoost:</strong> gradient-boosted decision trees that score potential BUY/SELL/HOLD outcomes based on engineered market features.</li>
          <li><strong>LSTM:</strong> recurrent network that captures sequential price behavior and signal persistence over time.</li>
          <li><strong>Transformer:</strong> attention-based model that analyzes multi-timeframe context and structural market patterns.</li>
        </ul>
        <p>Each model contributes to a final ensemble score used to rank signals and determine whether a trade candidate passes the risk gate.</p>
      </section>

      <section>
        <h2>AI explanations</h2>
        <p>For each signal, the system generates a plain-language explanation to describe the market rationale. Explanations are intended for educational and interpretive purposes only, not as financial advice.</p>
      </section>

      <section>
        <h2>Risk engine</h2>
        <p>The risk engine is a deterministic layer that evaluates every trade candidate against hard rules before execution. It is separate from the AI ensemble and cannot be bypassed.</p>
        <ul>
          <li>Minimum confidence threshold</li>
          <li>Spread limit</li>
          <li>News filter and trade window checks</li>
          <li>Daily loss and drawdown caps</li>
          <li>Maximum open trades</li>
          <li>Valid stop loss / take profit sizing</li>
          <li>Risk/reward minimum requirement</li>
        </ul>
      </section>

      <section>
        <h2>Interpretation guidance</h2>
        <p>AI signals are designed to support informed trading activity. Always use them alongside your own analysis, market knowledge, and risk management. The platform explicitly disclaims any investment advice.</p>
      </section>

      <style jsx>{`
        .doc-page { max-width: 900px; margin: 0 auto; padding: 4rem 1.5rem; color: #e2e8f0; }
        .doc-header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 2.5rem; }
        .eyebrow { text-transform: uppercase; letter-spacing: 0.2em; color: #7dd3fc; font-size: 0.78rem; margin-bottom: 0.75rem; }
        h1 { font-size: clamp(2.2rem, 4vw, 3rem); margin-bottom: 1rem; }
        .doc-sub { max-width: 620px; color: #94a3b8; line-height: 1.8; }
        section { margin-bottom: 2rem; }
        h2 { font-size: 1.25rem; margin-bottom: 0.75rem; }
        p, li { color: #cbd5e1; line-height: 1.8; }
        ul { list-style: disc inside; margin-left: 0; padding-left: 0; }
        li { margin-bottom: 0.75rem; }
        .btn { display: inline-flex; align-items: center; justify-content: center; padding: 0.8rem 1.25rem; border-radius: 10px; border: 1px solid rgba(99,179,237,0.4); color: #63b3ed; background: transparent; text-decoration: none; transition: background 0.2s; }
        .btn:hover { background: rgba(99,179,237,0.12); }
      `}</style>
    </main>
  );
}
