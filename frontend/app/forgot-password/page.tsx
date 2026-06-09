"use client";

import { useState } from "react";
import Link from "next/link";
import Logo from "@/components/Logo";
import { apiFetch } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError("Enter a valid email address");
      return;
    }
    setLoading(true);
    // Backend endpoint: POST /api/auth/forgot-password { email }
    // Currently a stub in auth-service — always returns 200 to prevent enumeration
    await apiFetch("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    setLoading(false);
    setSent(true); // Always show success (prevents email enumeration)
  };

  return (
    <>
      <style>{`
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #050a14; color: #e2f0ff; font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .page { width: 100%; max-width: 400px; padding: 2rem 1.5rem; }
        .logo { display: flex; align-items: center; gap: 10px; justify-content: center; margin-bottom: 2.5rem; }
        .logo-icon { width: 40px; height: 40px; background: linear-gradient(135deg, #00d4ff, #0095c8); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 20px; color: #000; }
        .logo-text { font-size: 1.2rem; font-weight: 700; }
        .logo-text span { color: #00d4ff; }
        .card { background: #0d1f35; border: 1px solid #1a3050; border-radius: 16px; padding: 2rem; }
        h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: .4rem; }
        .subtitle { font-size: .875rem; color: #4a6a80; margin-bottom: 1.75rem; line-height: 1.5; }
        .field { margin-bottom: 1rem; }
        label { display: block; font-size: .78rem; color: #8baabb; margin-bottom: .4rem; text-transform: uppercase; letter-spacing: .06em; }
        input { width: 100%; background: #0f2040; border: 1px solid #1f3d60; border-radius: 8px; padding: .7rem 1rem; color: #e2f0ff; font-size: .9rem; outline: none; transition: border-color .15s; }
        input:focus { border-color: #00d4ff; }
        input.err { border-color: #ff3d5a; }
        .field-error { font-size: .73rem; color: #ff3d5a; margin-top: .3rem; }
        .btn { width: 100%; padding: .8rem; border-radius: 8px; border: none; background: #00d4ff; color: #000; font-size: .95rem; font-weight: 700; cursor: pointer; transition: all .15s; display: flex; align-items: center; justify-content: center; gap: .5rem; margin-top: 1.25rem; }
        .btn:hover:not(:disabled) { background: #00f0ff; transform: translateY(-1px); }
        .btn:disabled { opacity: .6; cursor: not-allowed; }
        .back { display: flex; align-items: center; gap: .4rem; font-size: .85rem; color: #4a6a80; text-decoration: none; justify-content: center; margin-top: 1.25rem; }
        .back:hover { color: #00d4ff; }
        .success-box { text-align: center; padding: 1rem 0; }
        .success-icon { font-size: 3rem; margin-bottom: 1rem; }
        .success-title { font-size: 1.1rem; font-weight: 700; margin-bottom: .5rem; }
        .success-sub { font-size: .85rem; color: #4a6a80; line-height: 1.6; }
        .spinner { width: 16px; height: 16px; border: 2px solid rgba(0,0,0,.3); border-top-color: #000; border-radius: 50%; animation: spin .6s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>

      <div className="page">
        <Logo href="/" />

        <div className="card">
          {sent ? (
            <div className="success-box">
              <div className="success-icon">📧</div>
              <div className="success-title">Check your inbox</div>
              <p className="success-sub">
                If <strong style={{ color: "#8baabb" }}>{email}</strong> is registered, you&apos;ll receive a password reset link within a few minutes. Check your spam folder if it doesn&apos;t arrive.
              </p>
              <Link href="/login" className="btn" style={{ marginTop: "1.5rem", textDecoration: "none", display: "flex", justifyContent: "center" }}>
                Back to sign in
              </Link>
            </div>
          ) : (
            <>
              <h1>Reset password</h1>
              <p className="subtitle">Enter the email address associated with your account and we&apos;ll send you a reset link.</p>

              <form onSubmit={handleSubmit} noValidate>
                <div className="field">
                  <label>Email address</label>
                  <input
                    type="email" autoFocus autoComplete="email"
                    value={email} onChange={e => { setEmail(e.target.value); setError(""); }}
                    className={error ? "err" : ""}
                    placeholder="you@example.com"
                  />
                  {error && <div className="field-error">{error}</div>}
                </div>

                <button type="submit" className="btn" disabled={loading}>
                  {loading ? <><span className="spinner" /> Sending…</> : "Send reset link"}
                </button>
              </form>

              <Link href="/login" className="back">← Back to sign in</Link>
            </>
          )}
        </div>
      </div>
    </>
  );
}
