"use client";

import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

const SHARED_STYLES = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #050a14; color: #e2f0ff; font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .page { width: 100%; max-width: 420px; padding: 2rem 1.5rem; }
  .logo { display: flex; align-items: center; gap: 10px; justify-content: center; margin-bottom: 2.5rem; }
  .logo-icon { width: 40px; height: 40px; background: linear-gradient(135deg, #00d4ff, #0095c8); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 20px; color: #000; }
  .logo-text { font-size: 1.2rem; font-weight: 700; }
  .logo-text span { color: #00d4ff; }
  .card { background: #0d1f35; border: 1px solid #1a3050; border-radius: 16px; padding: 2rem; text-align: center; }
  h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: .4rem; }
  .subtitle { font-size: .875rem; color: #4a6a80; margin-bottom: 1.75rem; }
  .icon { font-size: 3rem; margin-bottom: 1rem; }
  .success-box { background: rgba(0,230,118,.06); border: 1px solid rgba(0,230,118,.2); border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem; }
  .success-text { font-size: .9rem; color: #00e676; }
  .error-box { background: rgba(255,61,90,.08); border: 1px solid rgba(255,61,90,.3); border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem; }
  .error-text { font-size: .9rem; color: #ff3d5a; }
  .info-box { background: rgba(0,212,255,.06); border: 1px solid rgba(0,212,255,.2); border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem; }
  .info-text { font-size: .875rem; color: #4a6a80; line-height: 1.6; }
  .btn { width: 100%; padding: .8rem; border-radius: 8px; border: none; background: #00d4ff; color: #000; font-size: .95rem; font-weight: 700; cursor: pointer; transition: all .15s; display: flex; align-items: center; justify-content: center; gap: .5rem; margin-bottom: .75rem; }
  .btn:hover:not(:disabled) { background: #00f0ff; transform: translateY(-1px); }
  .btn:disabled { opacity: .6; cursor: not-allowed; }
  .btn-outline { background: transparent; border: 1px solid #1f3d60; color: #8baabb; }
  .btn-outline:hover:not(:disabled) { border-color: #00d4ff; color: #00d4ff; transform: translateY(-1px); }
  .field { margin-bottom: 1rem; text-align: left; }
  label { display: block; font-size: .8rem; color: #8baabb; margin-bottom: .4rem; text-transform: uppercase; letter-spacing: .06em; }
  input { width: 100%; background: #0f2040; border: 1px solid #1f3d60; border-radius: 8px; padding: .7rem 1rem; color: #e2f0ff; font-size: .9rem; outline: none; transition: border-color .15s; }
  input:focus { border-color: #00d4ff; }
  .back-link { font-size: .85rem; color: #4a6a80; margin-top: .5rem; }
  .back-link a { color: #00d4ff; text-decoration: none; font-weight: 600; }
  .back-link a:hover { text-decoration: underline; }
  .spinner { width: 18px; height: 18px; border: 2px solid rgba(0,0,0,.25); border-top-color: #000; border-radius: 50%; animation: spin .6s linear infinite; }
  .spinner-dark { border: 2px solid rgba(0,212,255,.2); border-top-color: #00d4ff; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-wrap { padding: 2rem 0; display: flex; flex-direction: column; align-items: center; gap: 1rem; color: #4a6a80; font-size: .9rem; }
`;

type State = "verifying" | "success" | "expired" | "invalid" | "no_token";

function VerifyContent() {
  const searchParams = useSearchParams();
  const verifyToken = searchParams.get("token");

  const [state, setState] = useState<State>(verifyToken ? "verifying" : "no_token");
  const [resendEmail, setResendEmail] = useState("");
  const [resendSent, setResendSent] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);

  useEffect(() => {
    if (!verifyToken) return;
    (async () => {
      const { error } = await apiFetch("/api/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ token: verifyToken }),
      });
      if (!error) {
        setState("success");
      } else if (error.toLowerCase().includes("expired")) {
        setState("expired");
      } else {
        setState("invalid");
      }
    })();
  }, [verifyToken]);

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resendEmail.trim()) return;
    setResendLoading(true);
    // Always returns 200 — anti-enumeration (same pattern as forgot-password)
    await apiFetch("/api/auth/resend-verification", {
      method: "POST",
      body: JSON.stringify({ email: resendEmail }),
    });
    setResendLoading(false);
    setResendSent(true);
  };

  if (state === "verifying") {
    return (
      <div className="card">
        <div className="loading-wrap">
          <div className="spinner spinner-dark" style={{ width: 28, height: 28 }} />
          Verifying your email…
        </div>
      </div>
    );
  }

  if (state === "success") {
    return (
      <div className="card">
        <div className="icon">🎉</div>
        <h1>Email verified!</h1>
        <p className="subtitle">Your account is now fully activated.</p>
        <div className="success-box">
          <div className="success-text">All features are now unlocked. You&apos;re good to go.</div>
        </div>
        <Link href="/dashboard">
          <button className="btn">Go to dashboard</button>
        </Link>
      </div>
    );
  }

  if (state === "expired") {
    return (
      <div className="card">
        <div className="icon">⏱️</div>
        <h1>Link expired</h1>
        <p className="subtitle">Verification links expire after 24 hours.</p>
        {resendSent ? (
          <div className="info-box">
            <div className="info-text">A new verification link has been sent if that email is registered with us.</div>
          </div>
        ) : (
          <form onSubmit={handleResend}>
            <div className="field">
              <label>Your email</label>
              <input
                type="email"
                autoFocus
                placeholder="you@example.com"
                value={resendEmail}
                onChange={e => setResendEmail(e.target.value)}
              />
            </div>
            <button type="submit" className="btn" disabled={resendLoading || !resendEmail.trim()}>
              {resendLoading ? <><span className="spinner" /> Sending…</> : "Resend verification email"}
            </button>
          </form>
        )}
        <div className="back-link"><Link href="/login">← Back to sign in</Link></div>
      </div>
    );
  }

  if (state === "no_token") {
    return (
      <div className="card">
        <div className="icon">📧</div>
        <h1>Check your email</h1>
        <p className="subtitle">We sent a verification link to your inbox.</p>
        <div className="info-box">
          <div className="info-text">
            Click the link in the email to verify your account. It expires after 24 hours.<br /><br />
            Don&apos;t see it? Check your spam folder.
          </div>
        </div>
        {resendSent ? (
          <div className="success-box" style={{ marginBottom: ".75rem" }}>
            <div className="success-text">New link sent! Check your inbox.</div>
          </div>
        ) : (
          <form onSubmit={handleResend} style={{ marginBottom: ".75rem" }}>
            <div className="field">
              <label>Resend to</label>
              <input
                type="email"
                placeholder="you@example.com"
                value={resendEmail}
                onChange={e => setResendEmail(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-outline" disabled={resendLoading || !resendEmail.trim()}>
              {resendLoading ? <><span className="spinner spinner-dark" /> Sending…</> : "Resend verification email"}
            </button>
          </form>
        )}
        <div className="back-link"><Link href="/login">← Back to sign in</Link></div>
      </div>
    );
  }

  // invalid
  return (
    <div className="card">
      <div className="icon">🔗</div>
      <h1>Invalid link</h1>
      <p className="subtitle">This verification link is not valid.</p>
      <div className="error-box">
        <div className="error-text">The link may have already been used or is malformed. Request a new one below.</div>
      </div>
      {resendSent ? (
        <div className="info-box">
          <div className="info-text">A new verification link has been sent if that email is registered.</div>
        </div>
      ) : (
        <form onSubmit={handleResend}>
          <div className="field">
            <label>Your email</label>
            <input
              type="email"
              autoFocus
              placeholder="you@example.com"
              value={resendEmail}
              onChange={e => setResendEmail(e.target.value)}
            />
          </div>
          <button type="submit" className="btn" disabled={resendLoading || !resendEmail.trim()}>
            {resendLoading ? <><span className="spinner" /> Sending…</> : "Resend verification email"}
          </button>
        </form>
      )}
      <div className="back-link"><Link href="/login">← Back to sign in</Link></div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <>
      <style>{SHARED_STYLES}</style>
      <div className="page">
        <div className="logo">
          <div className="logo-icon">M</div>
          <div className="logo-text">Merit<span>Trade</span> AI</div>
        </div>
        <Suspense fallback={
          <div className="card">
            <div className="loading-wrap">
              <div className="spinner spinner-dark" style={{ width: 28, height: 28 }} />
              Loading…
            </div>
          </div>
        }>
          <VerifyContent />
        </Suspense>
      </div>
    </>
  );
}
