/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,

  experimental: {
    typedRoutes: false,
    serverActions: { bodySizeLimit: "2mb" },
  },

  transpilePackages: [
    "antd",
    "@ant-design/icons",
    "@ant-design/nextjs-registry",
    "@rjsf/antd",
    "rc-util",
    "rc-pagination",
    "rc-picker",
  ],

  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [
      { protocol: "https", hostname: "*.aqp.fund" },
      { protocol: "https", hostname: "cdn.aqp.fund" },
    ],
  },

  async headers() {
    const securityHeaders = [
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      {
        key: "Strict-Transport-Security",
        value: "max-age=63072000; includeSubDomains; preload",
      },
    ];
    return [{ source: "/:path*", headers: securityHeaders }];
  },

  async rewrites() {
    return [
      {
        source: "/.well-known/oauth-protected-resource/:path*",
        destination: `${process.env.AQP_API_BASE ?? "http://localhost:8000"}/.well-known/oauth-protected-resource/:path*`,
      },
    ];
  },
};

export default nextConfig;
