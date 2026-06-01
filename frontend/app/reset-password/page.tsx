"use client";

import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

const SHARED_STYLES = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #050a14; color: #e2f0ff; font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .page { width: 100%; max-width: 420px; padding: 2rem 1.5rem; }
  .logo { display: flex; align-items: center; gap: 10px; justify-content: center; margin-bottom: 2.5rem; }
  .logo-icon { width: 40px; height: 40px; background: linear-gradient(135deg, #00d4ff, #0095c8); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 20px; color: #000; }
  .logo-text { font-size: 1.2rem; font-weight: 700; }
  .logo-text span { color: #00d4ff; }
  .card { background: #0d1f35; border: 1px solid #1a3050; border-radius: 16px; padding: 2rem; }
  h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: .4rem; }
  .subtitle { font-size: .875rem; color: #4a6a80; margin-bottom: 1.75rem; }
  .field { margin-bottom: 1rem; }
  label { display: block; font-size: .8rem; color: #8baabb; margin-bottom: .4rem; text-transform: uppercase; letter-spacing: .06em; }
  .input-wrap { position: relative; }
  input { width: 100%; background: #0f2040; border: 1px solid #1f3d60; border-radius: 8px; padding: .7rem 1rem; color: #e2f0ff; font-size: .9rem; outline: none; transition: border-color .15s; }
  input:focus { border-color: #00d4ff; }
  input.err { border-color: #ff3d5a; }
  .pw-toggle { position: absolute; right: .75rem; top: 50%; transform: translateY(-50%); background: none; border: none; color: #4a6a80; cursor: pointer; font-size: .8rem; }
  .pw-toggle:hover { color: #8baabb; }
  .field-error { font-size: .75rem; color: #ff3d5a; margin-top: .3rem; }
  .server-error { background: rgba(255,61,90,.08); border: 1px solid rgba(255,61,90,.3); border-radius: 8px; padding: .75rem 1rem; font-size: .85rem; color: #ff3d5a; margin-bottom: 1rem; }
  .success-box { background: rgba(0,212,255,.06); border: 1px solid rgba(0,212,255,.25); border-radius: 12px; padding: 1.5rem; text-align: center; }
  .success-icon { font-size: 2rem; margin-bottom: .75rem; }
  .success-title { font-size: 1.1rem; font-weight: 700; margin-bottom: .4rem; }
  .success-sub { font-size: .875rem; color: #4a6a80; margin-bottom: 1.25rem; }
  .btn { width: 100%; padding: .8rem; border-radius: 8px; border: none; background: #00d4ff; color: #000; font-size: .95rem; font-weight: 700; cursor: pointer; transition: all .15s; display: flex; align-items: center; justify-content: center; gap: .5rem; }
  .btn:hover:not(:disabled) { background: #00f0ff; transform: translateY(-1px); }
  .btn:disabled { opacity: .6; cursor: not-allowed; }
  .strength-bar { height: 4px; border-radius: 2px; margin-top: .4rem; transition: all .2s; }
  .back-link { text-align: center; font-size: .85rem; color: #4a6a80; margin-top: 1.25rem; }
  .back-link a { color: #00d4ff; text-decoration: none; font-weight: 600; }
  .back-link a:hover { text-decoration: underline; }
  .hint { font-size: .75rem; color: #4a6a80; margin-top: .3rem; }
  .spinner { width: 16px; height: 16px; border: 2px solid rgba(0,0,0,.3); border-top-color: #000; border-radius: 50%; animation: spin .6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .invalid-token { text-align: center; padding: 1.5rem 0; }
  .invalid-icon { font-size: 2.5rem; margin-bottom: .75rem; }
  .invalid-title { font-size: 1.1rem; font-weight: 700; margin-bottom: .5rem; color: #ff3d5a; }
  .invalid-sub { font-size: .875rem; color: #4a6a80; margin-bottom: 1.25rem; }
`;

function passwordStrength(pw: string): { score: number; label: string; color: string } {
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (score <= 1) return { score, label: "Weak", color: "#ff3d5a" };
  if (score <= 2) return { score, label: "Fair", color: "#ffaa00" };
  if (score <= 3) return { score, label: "Good", color: "#00d4ff" };
  return { score, label: "Strong", color: "#00e676" };
}

function ResetForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const resetToken = searchParams.get("token");

  const [form, setForm] = useState({ password: "", confirm: "" });
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({});
  const [serverError, setServerError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const strength = passwordStrength(form.password);

  // No token in URL → show invalid state immediately
  if (!resetToken) {
    return (
      <div className="card">
        <div className="invalid-token">
          <div className="invalid-icon">🔗</div>
          <div className="invalid-title">Invalid reset link</div>
          <div className="invalid-sub">
            This link is missing a reset token. Please request a new one.
          </div>
          <Link href="/forgot-password">
            <button className="btn">Request new link</button>
          </Link>
        </div>
      </div>
    );
  }

  const validate = () => {
    const errs: { password?: string; confirm?: string } = {};
    if (!form.password) errs.password = "Password is required";
    else if (form.password.length < 8) errs.password = "Must be at least 8 characters";
    else if (!/[A-Z]/.test(form.password)) errs.password = "Must contain an uppercase letter";
    else if (!/[0-9]/.test(form.password)) errs.password = "Must contain a number";
    if (!form.confirm) errs.confirm = "Please confirm your password";
    else if (form.confirm !== form.password) errs.confirm = "Passwords do not match";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError("");
    if (!validate()) return;

    setLoading(true);
    const { error } = await apiFetch("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token: resetToken, new_password: form.password }),
    });
    setLoading(false);

    if (error) {
      if (error.includes("invalid") || error.includes("expired")) {
        setServerError("This reset link is invalid or has expired. Please request a new one.");
      } else {
        setServerError(error);
      }
      return;
    }

    setDone(true);
  };

  if (done) {
    return (
      <div className="card">
        <div className="success-box">
          <div className="success-icon">✅</div>
          <div className="success-title">Password updated!</div>
          <div className="success-sub">Your password has been changed successfully. You can now sign in.</div>
          <button className="btn" onClick={() => router.push("/login")}>Sign in</button>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <h1>Set new password</h1>
      <p className="subtitle">Choose a strong password for your account</p>

      {serverError && (
        <div className="server-error">
          {serverError}{" "}
          {serverError.includes("expired") && (
            <Link href="/forgot-password" style={{ color: "#ff3d5a", fontWeight: 600 }}>
              Request new link →
            </Link>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="field">
          <label>New password</label>
          <div className="input-wrap">
            <input
              type={showPw ? "text" : "password"}
              autoComplete="new-password"
              autoFocus
              value={form.password}
              onChange={e => {
                setForm(p => ({ ...p, password: e.target.value }));
                if (errors.password) setErrors(p => ({ ...p, password: undefined }));
              }}
              className={errors.password ? "err" : ""}
              placeholder="••••••••"
            />
            <button type="button" className="pw-toggle" onClick={() => setShowPw(p => !p)}>
              {showPw ? "Hide" : "Show"}
            </button>
          </div>
          {form.password && (
            <>
              <div
                className="strength-bar"
                style={{
                  width: `${(strength.score / 5) * 100}%`,
                  background: strength.color,
                }}
              />
              <div className="hint" style={{ color: strength.color }}>{strength.label}</div>
            </>
          )}
          {errors.password && <div className="field-error">{errors.password}</div>}
          <div className="hint">Min 8 chars · one uppercase · one number</div>
        </div>

        <div className="field">
          <label>Confirm password</label>
          <div className="input-wrap">
            <input
              type={showConfirm ? "text" : "password"}
              autoComplete="new-password"
              value={form.confirm}
              onChange={e => {
                setForm(p => ({ ...p, confirm: e.target.value }));
                if (errors.confirm) setErrors(p => ({ ...p, confirm: undefined }));
              }}
              className={errors.confirm ? "err" : ""}
              placeholder="••••••••"
            />
            <button type="button" className="pw-toggle" onClick={() => setShowConfirm(p => !p)}>
              {showConfirm ? "Hide" : "Show"}
            </button>
          </div>
          {errors.confirm && <div className="field-error">{errors.confirm}</div>}
        </div>

        <button type="submit" className="btn" disabled={loading}>
          {loading ? <><span className="spinner" /> Updating…</> : "Update password"}
        </button>
      </form>

      <div className="back-link">
        <Link href="/login">← Back to sign in</Link>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <>
      <style>{SHARED_STYLES}</style>
      <div className="page">
        <div className="logo">
          <div className="logo-icon">M</div>
          <div className="logo-text">Merit<span>Trade</span> AI</div>
        </div>
        {/* Suspense required because useSearchParams() is used inside */}
        <Suspense fallback={<div className="card" style={{ textAlign: "center", padding: "2rem", color: "#4a6a80" }}>Loading…</div>}>
          <ResetForm />
        </Suspense>
      </div>
    </>
  );
}
