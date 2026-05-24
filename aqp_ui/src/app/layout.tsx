import type { Metadata, Viewport } from "next";
import { AntdRegistry } from "@ant-design/nextjs-registry";

import { AntdProvider } from "@/providers/AntdProvider";
import { QueryProvider } from "@/providers/QueryProvider";
import { AuthClientProvider } from "@/providers/AuthClientProvider";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.AQP_UI_BASE_URL ?? "https://aqp.fund"),
  title: {
    default: "AQP — Agentic Quant Platform",
    template: "%s — AQP",
  },
  description:
    "AgenticOps and data management for quantitative finance. Cloud-hosted, multi-tenant, built on the same engine that powers the AQP open-source platform.",
  applicationName: "Agentic Quant Platform",
  authors: [{ name: "AQP Platform Team" }],
  openGraph: {
    type: "website",
    siteName: "Agentic Quant Platform",
    title: "AQP — Agentic Quant Platform",
    description:
      "Cloud-hosted AgenticOps for quants. Strategies, paper trading, RL, agents, and a hierarchical data plane.",
    url: process.env.AQP_UI_BASE_URL ?? "https://aqp.fund",
  },
  twitter: {
    card: "summary_large_image",
    title: "AQP — Agentic Quant Platform",
    description: "AgenticOps and data management for quantitative finance.",
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: "#0F172A",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body>
        <AntdRegistry>
          <AntdProvider>
            <QueryProvider>
              <AuthClientProvider>{children}</AuthClientProvider>
            </QueryProvider>
          </AntdProvider>
        </AntdRegistry>
      </body>
    </html>
  );
}
