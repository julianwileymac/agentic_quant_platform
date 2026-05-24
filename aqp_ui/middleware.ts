import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const PUBLIC_PATHS = [
  "/",
  "/pricing",
  "/docs",
  "/legal",
  "/about",
  "/blog",
  "/changelog",
  "/signup",
  "/login",
  "/api/auth",
  "/api/healthz",
  "/_next",
  "/favicon",
];

function isPublic(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/**
 * Combined Auth0 + Entra session gate.
 *
 * AGENTS rule 11 (CVE-2025-29927): middleware MUST NOT be the only auth
 * check — every BFF route handler under src/app/api/* must re-call
 * `getSession()`. This middleware is a UX optimisation (early 302 to
 * /login) and a place to set the `x-aqp-tenant-id` request header for
 * downstream RSCs, NOT a security boundary.
 *
 * Resolves the session cookie in two steps:
 *   1. `@auth0/nextjs-auth0` cookie (handled by `auth0.middleware`).
 *   2. The unified `aqp_ui_session` JWE cookie (set by both providers).
 *
 * Both providers write to the unified cookie on callback, so this
 * middleware only needs to look for that single cookie.
 */
export async function middleware(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;

  if (isPublic(pathname)) {
    return NextResponse.next();
  }

  const sessionCookieName = process.env.AQP_UI_SESSION_COOKIE_NAME ?? "aqp_ui_session";
  const session = request.cookies.get(sessionCookieName);

  if (!session?.value) {
    const url = new URL("/login", request.url);
    url.searchParams.set("returnTo", pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|webp|gif|ico|css|js|woff2?)).*)",
  ],
};
