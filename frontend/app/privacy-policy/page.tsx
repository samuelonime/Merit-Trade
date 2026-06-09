"use client";

import Link from "next/link";

export default function PrivacyPolicyPage() {
  return (
    <main className="doc-page">
      <div className="doc-header">
        <div>
          <p className="eyebrow">Legal & Privacy</p>
          <h1>Privacy Policy</h1>
          <p className="doc-sub">How Merit-Trade AI collects, uses, protects, and shares your personal information.</p>
        </div>
        <Link href="/" className="btn btn--outline">Back to home</Link>
      </div>

      <section>
        <h2>Information We Collect</h2>
        <ul>
          <li><strong>Account data:</strong> name, email, username, hashed password, and profile settings.</li>
          <li><strong>Authentication data:</strong> tokens, login timestamps, IP address, and browser headers.</li>
          <li><strong>Trading activity:</strong> signals, trade execution data, risk settings, and account preferences.</li>
          <li><strong>Broker/exchange connections:</strong> account labels, server details, and encrypted API credentials.</li>
          <li><strong>Usage data:</strong> page views, feature usage, performance telemetry, and error reports.</li>
          <li><strong>Notification preferences:</strong> Telegram IDs, email preferences, and push subscription metadata.</li>
        </ul>
      </section>

      <section>
        <h2>How We Use Your Information</h2>
        <p>We use your data to operate and improve the platform, authenticate accounts, deliver trading signals, manage execution workflows, enforce risk rules, and communicate with you.</p>
      </section>

      <section>
        <h2>Data Sharing</h2>
        <p>We do not sell personal data. We may share information with service providers to operate the platform, with connected brokers/exchanges to execute trades, and with authorities when required by law.</p>
      </section>

      <section>
        <h2>Security</h2>
        <p>We protect sensitive information using strong security controls including encryption for broker credentials, secure password hashing, token-based authentication, and monitoring for suspicious activity.</p>
      </section>

      <section>
        <h2>Cookies and Tracking</h2>
        <p>The platform may use cookies and similar technologies for session management, functional preferences, and analytics. Disabling cookies may reduce available features.</p>
      </section>

      <section>
        <h2>Your Rights</h2>
        <p>You may have rights to access, update, delete, or restrict personal data depending on your jurisdiction. Contact us if you wish to exercise these rights.</p>
      </section>

      <section>
        <h2>Updates</h2>
        <p>We may update this policy over time. Continued use of the platform after changes indicates your acceptance.</p>
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
