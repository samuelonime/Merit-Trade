"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { auth, token } from "@/lib/api";

type Field = "full_name" | "username" | "email" | "password" | "confirm";

const STRENGTH_LABELS = ["", "Weak", "Fair", "Good", "Strong"];
const STRENGTH_COLORS = ["", "#ff3d5a", "#ffd740", "#00d4ff", "#00e676"];

function passwordStrength(pw: string): number {
  if (!pw) return 0;
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^a-zA-Z0-9]/.test(pw)) score++;
  return score;
}

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", username: "", email: "", password: "", confirm: "" });
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [serverError, setServerError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const strength = passwordStrength(form.password);

  useEffect(() => {
    if (token.access) router.replace("/dashboard");
  }, [router]);

  const validate = (): boolean => {
    const errs: Partial<Record<Field, string>> = {};
    if (!form.full_name.trim()) errs.full_name = "Full name is required";
    if (!form.username.trim()) errs.username = "Username is required";
    else if (form.username.length < 3 || form.username.length > 50) errs.username = "Username must be 3–50 characters";
    else if (!/^[a-zA-Z0-9_]+$/.test(form.username)) errs.username = "Only letters, numbers, and underscores";
    if (!form.email.trim()) errs.email = "Email is required";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = "Enter a valid email";
    if (!form.password) errs.password = "Password is required";
    else if (form.password.length < 8) errs.password = "At least 8 characters";
    else if (!/[A-Z]/.test(form.password)) errs.password = "At least one uppercase letter";
    else if (!/[0-9]/.test(form.password)) errs.password = "At least one number";
    if (!form.confirm) errs.confirm = "Please confirm your password";
    else if (form.confirm !== form.password) errs.confirm = "Passwords do not match";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError("");
    if (!validate()) return;
    if (!agreed) { setServerError("You must accept the terms to continue."); return; }

    setLoading(true);
    const { data, error } = await auth.register(form.email, form.username.toLowerCase(), form.password, form.full_name);
    setLoading(false);

    if (error) {
      if (error.includes("409")) setServerError("That email or username is already registered.");
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
        body { background: #050a14; color: #e2f0ff; font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 2rem 1rem; }
        .page { width: 100%; max-width: 460px; }
        .logo { display: flex; align-items: center; gap: 10px; justify-content: center; margin-bottom: 2rem; }
        .logo-icon { width: 40px; height: 40px; background: linear-gradient(135deg, #00d4ff, #0095c8); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 20px; color: #000; }
        .logo-text { font-size: 1.2rem; font-weight: 700; }
        .logo-text span { color: #00d4ff; }
        .card { background: #0d1f35; border: 1px solid #1a3050; border-radius: 16px; padding: 2rem; }
        h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: .4rem; }
        .subtitle { font-size: .875rem; color: #4a6a80; margin-bottom: 1.75rem; }
        .row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .field { margin-bottom: 1rem; }
        label { display: block; font-size: .78rem; color: #8baabb; margin-bottom: .4rem; text-transform: uppercase; letter-spacing: .06em; }
        .input-wrap { position: relative; }
        input[type=text], input[type=email], input[type=password] { width: 100%; background: #0f2040; border: 1px solid #1f3d60; border-radius: 8px; padding: .7rem 1rem; color: #e2f0ff; font-size: .9rem; outline: none; transition: border-color .15s; }
        input:focus { border-color: #00d4ff; }
        input.err { border-color: #ff3d5a; }
        .pw-toggle { position: absolute; right: .75rem; top: 50%; transform: translateY(-50%); background: none; border: none; color: #4a6a80; cursor: pointer; font-size: .78rem; }
        .pw-toggle:hover { color: #8baabb; }
        .field-error { font-size: .73rem; color: #ff3d5a; margin-top: .3rem; }
        .server-error { background: rgba(255,61,90,.08); border: 1px solid rgba(255,61,90,.3); border-radius: 8px; padding: .75rem 1rem; font-size: .85rem; color: #ff3d5a; margin-bottom: 1rem; }
        .strength-bar { display: flex; gap: 3px; margin-top: .4rem; }
        .strength-seg { flex: 1; height: 3px; border-radius: 2px; background: #1a3050; transition: background .2s; }
        .strength-label { font-size: .7rem; margin-top: .25rem; }
        .agree { display: flex; align-items: flex-start; gap: .6rem; margin-bottom: 1.25rem; cursor: pointer; }
        .agree input[type=checkbox] { margin-top: 2px; accent-color: #00d4ff; flex-shrink: 0; width: 15px; height: 15px; }
        .agree-text { font-size: .8rem; color: #8baabb; line-height: 1.5; }
        .agree-text a { color: #00d4ff; text-decoration: none; }
        .btn { width: 100%; padding: .8rem; border-radius: 8px; border: none; background: #00d4ff; color: #000; font-size: .95rem; font-weight: 700; cursor: pointer; transition: all .15s; display: flex; align-items: center; justify-content: center; gap: .5rem; }
        .btn:hover:not(:disabled) { background: #00f0ff; transform: translateY(-1px); }
        .btn:disabled { opacity: .6; cursor: not-allowed; }
        .login-link { text-align: center; font-size: .85rem; color: #4a6a80; margin-top: 1.25rem; }
        .login-link a { color: #00d4ff; text-decoration: none; font-weight: 600; }
        .login-link a:hover { text-decoration: underline; }
        .spinner { width: 16px; height: 16px; border: 2px solid rgba(0,0,0,.3); border-top-color: #000; border-radius: 50%; animation: spin .6s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (max-width: 480px) { .row { grid-template-columns: 1fr; } }
      `}</style>

      <div className="page">
        <div className="logo">
          <div className="logo-icon">M</div>
          <div className="logo-text">Merit<span>Trade</span> AI</div>
        </div>

        <div className="card">
          <h1>Create your account</h1>
          <p className="subtitle">Free forever · No credit card required</p>

          {serverError && <div className="server-error">{serverError}</div>}

          <form onSubmit={handleSubmit} noValidate>
            <div className="row">
              <div className="field">
                <label>Full Name</label>
                <input type="text" autoComplete="name" autoFocus
                  value={form.full_name} onChange={set("full_name")}
                  className={errors.full_name ? "err" : ""}
                  placeholder="John Doe" />
                {errors.full_name && <div className="field-error">{errors.full_name}</div>}
              </div>
              <div className="field">
                <label>Username</label>
                <input type="text" autoComplete="username"
                  value={form.username} onChange={set("username")}
                  className={errors.username ? "err" : ""}
                  placeholder="johndoe" />
                {errors.username && <div className="field-error">{errors.username}</div>}
              </div>
            </div>

            <div className="field">
              <label>Email</label>
              <input type="email" autoComplete="email"
                value={form.email} onChange={set("email")}
                className={errors.email ? "err" : ""}
                placeholder="you@example.com" />
              {errors.email && <div className="field-error">{errors.email}</div>}
            </div>

            <div className="field">
              <label>Password</label>
              <div className="input-wrap">
                <input type={showPw ? "text" : "password"} autoComplete="new-password"
                  value={form.password} onChange={set("password")}
                  className={errors.password ? "err" : ""}
                  placeholder="Min. 8 chars, 1 uppercase, 1 number" />
                <button type="button" className="pw-toggle" onClick={() => setShowPw(p => !p)}>
                  {showPw ? "Hide" : "Show"}
                </button>
              </div>
              {form.password && (
                <>
                  <div className="strength-bar">
                    {[1, 2, 3, 4].map(i => (
                      <div key={i} className="strength-seg"
                        style={{ background: i <= strength ? STRENGTH_COLORS[strength] : "#1a3050" }} />
                    ))}
                  </div>
                  <div className="strength-label" style={{ color: STRENGTH_COLORS[strength] }}>
                    {STRENGTH_LABELS[strength]}
                  </div>
                </>
              )}
              {errors.password && <div className="field-error">{errors.password}</div>}
            </div>

            <div className="field">
              <label>Confirm Password</label>
              <input type="password" autoComplete="new-password"
                value={form.confirm} onChange={set("confirm")}
                className={errors.confirm ? "err" : ""}
                placeholder="••••••••" />
              {errors.confirm && <div className="field-error">{errors.confirm}</div>}
            </div>

            <label className="agree">
              <input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} />
              <span className="agree-text">
                I agree to the <a href="#" tabIndex={-1}>Terms of Service</a> and <a href="#" tabIndex={-1}>Privacy Policy</a>.
                I understand this platform is not financial advice and trading involves substantial risk.
              </span>
            </label>

            <button type="submit" className="btn" disabled={loading || !agreed}>
              {loading ? <><span className="spinner" /> Creating account…</> : "Create account →"}
            </button>
          </form>

          <div className="login-link">
            Already have an account? <Link href="/login">Sign in</Link>
          </div>
        </div>
      </div>
    </>
  );
}
