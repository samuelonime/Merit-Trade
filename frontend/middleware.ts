import { NextRequest, NextResponse } from "next/server";

// Routes that require authentication
const PROTECTED = ["/dashboard"];
// Routes only for unauthenticated users (redirect to /dashboard if already logged in)
const AUTH_ONLY = ["/login", "/register", "/forgot-password", "/reset-password"];
// Routes accessible to everyone (no redirect either way)
const PUBLIC_ONLY = ["/verify-email", "/pricing"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const token = req.cookies.get("access_token")?.value;

  // Check if this is a protected route
  const isProtected = PROTECTED.some(p => pathname.startsWith(p));
  const isAuthOnly = AUTH_ONLY.some(p => pathname.startsWith(p));

  if (isProtected && !token) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (isAuthOnly && token) {
    const url = req.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/register", "/forgot-password", "/reset-password", "/verify-email", "/pricing"],
};
