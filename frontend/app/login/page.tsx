"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { auth, token } from "@/lib/api";

type Field = "email" | "password";

export default function LoginPage() {
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "" });
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [serverError, setServerError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);

  // Redirect if already logged in
  useEffect(() => {
    if (token.access) router.replace("/dashboard");
  }, [router]);

  const validate = (): boolean => {
    const errs: Partial<Record<Field, string>> = {};
    if (!form.email.trim()) errs.email = "Email is required";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = "Enter a valid email";
    if (!form.password) errs.password = "Password is required";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError("");
    if (!validate()) return;

    setLoading(true);
    const { data, error } = await auth.login(form.email, form.password);
    setLoading(false);

    if (error) {
      if (error.includes("423")) setServerError("Account temporarily locked due to too many failed attempts. Try again in 30 minutes.");
      else if (error.includes("401")) setServerError("Incorrect email or password.");
      else setServerError(error);
      return;
    }

    if (!data) {
      setServerError("Unexpected server response. Please try again.");
      return;
    }

    token.set(data.access_token, data.refresh_token);
    router.push("/dashboard");
  };

  const set = (field: Field) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm(p => ({ ...p, [field]: e.target.value }));
    if (errors[field]) setErrors(p => ({ ...p, [field]: undefined }));
    setServerError("");
  };

  return (
    <>
      <style>{`
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
        .forgot { display: block; text-align: right; font-size: .78rem; color: #4a6a80; text-decoration: none; margin-top: -.5rem; margin-bottom: 1.25rem; }
        .forgot:hover { color: #00d4ff; }
        .btn { width: 100%; padding: .8rem; border-radius: 8px; border: none; background: #00d4ff; color: #000; font-size: .95rem; font-weight: 700; cursor: pointer; transition: all .15s; display: flex; align-items: center; justify-content: center; gap: .5rem; }
        .btn:hover:not(:disabled) { background: #00f0ff; transform: translateY(-1px); }
        .btn:disabled { opacity: .6; cursor: not-allowed; }
        .divider { display: flex; align-items: center; gap: .75rem; margin: 1.25rem 0; }
        .divider hr { flex: 1; border: none; border-top: 1px solid #1a3050; }
        .divider span { font-size: .75rem; color: #4a6a80; }
        .register-link { text-align: center; font-size: .85rem; color: #4a6a80; }
        .register-link a { color: #00d4ff; text-decoration: none; font-weight: 600; }
        .register-link a:hover { text-decoration: underline; }
        .spinner { width: 16px; height: 16px; border: 2px solid rgba(0,0,0,.3); border-top-color: #000; border-radius: 50%; animation: spin .6s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>

      <div className="page">
        <div className="logo">
          <div className="logo-icon">M</div>
          <div className="logo-text">Merit<span>Trade</span> AI</div>
        </div>

        <div className="card">
          <h1>Welcome back</h1>
          <p className="subtitle">Sign in to your trading account</p>

          {serverError && <div className="server-error">{serverError}</div>}

          <form onSubmit={handleSubmit} noValidate>
            <div className="field">
              <label>Email</label>
              <input
                type="email" autoComplete="email" autoFocus
                value={form.email} onChange={set("email")}
                className={errors.email ? "err" : ""}
                placeholder="you@example.com"
              />
              {errors.email && <div className="field-error">{errors.email}</div>}
            </div>

            <div className="field">
              <label>Password</label>
              <div className="input-wrap">
                <input
                  type={showPw ? "text" : "password"} autoComplete="current-password"
                  value={form.password} onChange={set("password")}
                  className={errors.password ? "err" : ""}
                  placeholder="••••••••"
                />
                <button type="button" className="pw-toggle" onClick={() => setShowPw(p => !p)}>
                  {showPw ? "Hide" : "Show"}
                </button>
              </div>
              {errors.password && <div className="field-error">{errors.password}</div>}
            </div>

            <Link href="/forgot-password" className="forgot">Forgot password?</Link>

            <button type="submit" className="btn" disabled={loading}>
              {loading ? <><span className="spinner" /> Signing in…</> : "Sign in"}
            </button>
          </form>

          <div className="divider"><hr /><span>New here?</span><hr /></div>
          <div className="register-link">
            Don&apos;t have an account? <Link href="/register">Create one free</Link>
          </div>
        </div>
      </div>
    </>
  );
}
