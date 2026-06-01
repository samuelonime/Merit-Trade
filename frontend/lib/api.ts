/**
 * Merit-Trade AI — centralised API client
 * All components import from here so auth logic lives in one place.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

// ── Token helpers ─────────────────────────────────────────────────

/**
 * Tokens are stored in two places:
 *  - localStorage  — read by client-side API calls (apiFetch)
 *  - document.cookie — read by Next.js middleware for server-side
 *    route protection (middleware cannot access localStorage)
 *
 * The access_token cookie is SameSite=Strict, no HttpOnly (must be
 * writable from JS). The refresh_token stays in localStorage only —
 * it is never sent automatically by the browser.
 */

function setCookie(name: string, value: string, maxAgeSec: number) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSec}; SameSite=Strict`;
}

function deleteCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; path=/; max-age=0; SameSite=Strict`;
}

// Access token expires in 15 min (900 s) — matches backend default.
// Adjust if JWT_ACCESS_TOKEN_EXPIRE_MINUTES differs in your config.
const ACCESS_TOKEN_MAX_AGE = 15 * 60;

export const token = {
  get access() { return typeof window !== "undefined" ? localStorage.getItem("access_token") : null; },
  get refresh() { return typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null; },
  set(access: string, refresh: string) {
    localStorage.setItem("access_token", access);
    localStorage.setItem("refresh_token", refresh);
    // Mirror access token into a cookie for middleware route-guards
    setCookie("access_token", access, ACCESS_TOKEN_MAX_AGE);
  },
  clear() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
    deleteCookie("access_token");
  },
};

// ── Refresh flow ──────────────────────────────────────────────────

let refreshInFlight: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const rt = token.refresh;
    if (!rt) return false;
    try {
      const res = await fetch(`${API}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) return false;
      const { access_token, refresh_token } = await res.json();
      // token.set also refreshes the cookie mirror
      token.set(access_token, refresh_token ?? rt);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

// ── Core fetch ────────────────────────────────────────────────────

export type ApiResult<T> = { data: T; error: null } | { data: null; error: string };

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token.access ? { Authorization: `Bearer ${token.access}` } : {}),
        ...(options.headers ?? {}),
      },
    });

    if (res.status === 401 && retry) {
      const ok = await refreshTokens();
      if (ok) return apiFetch(path, options, false);
      token.clear();
      window.location.href = "/login";
      return { data: null, error: "Session expired" };
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { data: null, error: body?.detail ?? `HTTP ${res.status}` };
    }

    const data: T = await res.json();
    return { data, error: null };
  } catch (err) {
    return { data: null, error: err instanceof Error ? err.message : "Network error" };
  }
}

// ── Auth ──────────────────────────────────────────────────────────

export const auth = {
  async register(email: string, username: string, password: string, full_name?: string) {
    return apiFetch<{ access_token: string; refresh_token: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, username, password, full_name }),
    });
  },

  async login(email: string, password: string) {
    return apiFetch<{ access_token: string; refresh_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  async logout() {
    await apiFetch("/api/auth/logout", { method: "POST" });
    token.clear();
    window.location.href = "/login";
  },
};

// ── Typed resource helpers ────────────────────────────────────────

export const users = {
  me: () => apiFetch<{ id: string; email: string; username: string; full_name?: string; plan: string }>("/api/users/me"),
  accounts: () => apiFetch<{ forex: unknown[]; crypto: unknown[] }>("/api/users/accounts"),
  addForex: (body: unknown) => apiFetch("/api/users/forex-accounts", { method: "POST", body: JSON.stringify(body) }),
  addCrypto: (body: unknown) => apiFetch("/api/users/crypto-accounts", { method: "POST", body: JSON.stringify(body) }),
};

export const risk = {
  get: (userId: string) => apiFetch<unknown>(`/api/risk/settings/${userId}`),
  save: (userId: string, body: unknown) => apiFetch(`/api/risk/settings/${userId}`, { method: "PUT", body: JSON.stringify(body) }),
};

export const notify = {
  get: (userId: string) => apiFetch<unknown>(`/api/notify/preferences/${userId}`),
  save: (userId: string, body: unknown) => apiFetch(`/api/notify/preferences/${userId}`, { method: "PUT", body: JSON.stringify(body) }),
};

export const signals = {
  list: () => apiFetch<unknown[]>("/api/signals"),
};

export const trades = {
  list: (status?: string) => apiFetch<unknown[]>(`/api/execute/trades${status ? `?status=${status}` : ""}`),
  execute: (body: unknown) => apiFetch<{ trade_id: string; status: string }>("/api/execute/trade", { method: "POST", body: JSON.stringify(body) }),
  close: (tradeId: string) => apiFetch(`/api/execute/close/${tradeId}`, { method: "POST" }),
};
