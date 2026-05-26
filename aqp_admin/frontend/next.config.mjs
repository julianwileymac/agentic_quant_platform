// @ts-check

/**
 * Next.js 15 App Router config for the admin surface.
 *
 * Notes:
 * - The admin frontend talks to the FastAPI backend over its origin
 *   only (default http://localhost:8900). For dev we proxy /admin/*
 *   straight through so the SPA can call same-origin and skip CORS
 *   pre-flights entirely.
 * - CVE-2025-29927 (`x-middleware-subrequest` middleware bypass) is
 *   patched in Next.js 14.2.25 / 15.2.3+. We pin >=15.1.0 in
 *   `package.json`; CI runs `npm audit --omit=dev` to catch any
 *   downstream regressions.
 */
const ADMIN_API = process.env.AQP_ADMIN_API_URL || "http://localhost:8900";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  typedRoutes: true,
  // Pin the workspace root so Next.js stops complaining about the
  // user-home `package-lock.json` it sees on Windows.
  outputFileTracingRoot: new URL("./", import.meta.url).pathname.replace(/^\//, ""),
  async rewrites() {
    return [
      {
        source: "/admin/:path*",
        destination: `${ADMIN_API}/admin/:path*`,
      },
      {
        source: "/openapi.json",
        destination: `${ADMIN_API}/openapi.json`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
