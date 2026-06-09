"use client";

import Link from "next/link";

export default function TermsOfServicePage() {
  return (
    <main className="doc-page">
      <div className="doc-header">
        <div>
          <p className="eyebrow">Legal</p>
          <h1>Terms of Service</h1>
          <p className="doc-sub">The terms that govern your use of Merit-Trade AI.</p>
        </div>
        <Link href="/" className="btn btn--outline">Back to home</Link>
      </div>

      <section>
        <h2>Acceptance of terms</h2>
        <p>By accessing or using Merit-Trade AI, you agree to these Terms of Service and any updates we publish.</p>
      </section>

      <section>
        <h2>Platform use</h2>
        <p>Merit-Trade AI provides technology for viewing trading signals, analytics, and broker connectivity. It does not provide investment advice. You are responsible for your trading decisions and compliance with applicable law.</p>
      </section>

      <section>
        <h2>Accounts</h2>
        <p>You must provide accurate information and keep your login credentials secure. You are responsible for all activity on your account.</p>
      </section>

      <section>
        <h2>Intellectual property</h2>
        <p>All platform content, software, models, and documentation are the property of Merit-Trade AI or its licensors and are protected by intellectual property laws.</p>
      </section>

      <section>
        <h2>No financial advice</h2>
        <p>All information and signals are for educational and informational purposes only. Merit-Trade AI is not a financial advisor and does not recommend specific trades.</p>
      </section>

      <section>
        <h2>Termination</h2>
        <p>We may suspend or terminate accounts for violation of these terms or illegal activity. You may also close your account at any time.</p>
      </section>

      <section>
        <h2>Limitation of liability</h2>
        <p>To the fullest extent permitted by law, Merit-Trade AI is not liable for losses or damages resulting from your use of the platform, including trading outcomes or service interruptions.</p>
      </section>

      <section>
        <h2>Changes</h2>
        <p>We may update these Terms of Service. Continued use of the platform after changes means you accept the new terms.</p>
      </section>

      <style jsx>{`
        .doc-page { max-width: 900px; margin: 0 auto; padding: 4rem 1.5rem; color: #e2e8f0; }
        .doc-header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 2.5rem; }
        .eyebrow { text-transform: uppercase; letter-spacing: 0.2em; color: #7dd3fc; font-size: 0.78rem; margin-bottom: 0.75rem; }
        h1 { font-size: clamp(2.2rem, 4vw, 3rem); margin-bottom: 1rem; }
        .doc-sub { max-width: 620px; color: #94a3b8; line-height: 1.8; }
        section { margin-bottom: 2rem; }
        h2 { font-size: 1.25rem; margin-bottom: 0.75rem; }
        p { color: #cbd5e1; line-height: 1.8; }
        .btn { display: inline-flex; align-items: center; justify-content: center; padding: 0.8rem 1.25rem; border-radius: 10px; border: 1px solid rgba(99,179,237,0.4); color: #63b3ed; background: transparent; text-decoration: none; transition: background 0.2s; }
        .btn:hover { background: rgba(99,179,237,0.12); }
      `}</style>
    </main>
  );
}
