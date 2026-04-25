import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Antd v5 + React 19: enable the styled-components/cssinjs registry
  // via @ant-design/nextjs-registry (wired in app/layout.tsx).
  transpilePackages: ["@ant-design/icons", "antd", "rc-util", "rc-pagination", "rc-picker"],
  experimental: {
    optimizePackageImports: ["antd", "@ant-design/icons", "lodash"],
  },
  // Dev convenience: proxy /api/* to FastAPI so cookies / WebSockets stay
  // same-origin during local development. Production should terminate at
  // a proper reverse proxy or use the OpenAPI proxy route handler.
  async rewrites() {
    return [
      {
        source: "/aqp-api/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
