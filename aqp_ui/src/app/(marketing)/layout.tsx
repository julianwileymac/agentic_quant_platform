import Link from "next/link";
import { TrendingUp } from "lucide-react";

import { cn } from "@/lib/cn";

export const dynamic = "force-static";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div style={{ background: "var(--bg-app)", minHeight: "100vh" }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 24px",
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border-default)",
        }}
      >
        <Link
          href="/"
          className="flex items-center gap-2"
          style={{ color: "var(--text-primary)" }}
        >
          <TrendingUp size={20} />
          <span className="text-lg font-semibold tracking-tight">AQP</span>
        </Link>
        <nav className="flex items-center gap-1">
          <MarketingLink href="/">Home</MarketingLink>
          <MarketingLink href="/pricing">Pricing</MarketingLink>
          <MarketingLink href="/docs">Docs</MarketingLink>
          <MarketingLink href="/about">About</MarketingLink>
          <MarketingLink href="/blog">Blog</MarketingLink>
          <MarketingLink href="/changelog">Changelog</MarketingLink>
          <div className="ml-4 flex items-center gap-2">
            <Link
              href="/login"
              className="rounded px-3 py-1.5 text-sm font-medium hover:bg-white/5"
              style={{ color: "var(--text-secondary)" }}
            >
              Log in
            </Link>
            <Link
              href="/signup"
              className="rounded px-3 py-1.5 text-sm font-semibold"
              style={{
                color: "white",
                background: "var(--accent-primary)",
              }}
            >
              Sign up
            </Link>
          </div>
        </nav>
      </header>

      <main style={{ padding: "0", minHeight: "calc(100vh - 128px)" }}>
        {children}
      </main>

      <footer
        style={{
          background: "var(--bg-surface)",
          borderTop: "1px solid var(--border-default)",
          color: "var(--text-secondary)",
        }}
      >
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 md:flex-row">
          <div className="text-sm">
            © {new Date().getFullYear()} Agentic Quant Platform. All rights
            reserved.
          </div>
          <div className="flex items-center gap-4 text-sm">
            <Link href="/legal/terms" className="hover:underline">
              Terms
            </Link>
            <Link href="/legal/privacy" className="hover:underline">
              Privacy
            </Link>
            <Link href="/legal/security" className="hover:underline">
              Security
            </Link>
            <Link href="/legal/dpa" className="hover:underline">
              DPA
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function MarketingLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded px-3 py-1.5 text-sm transition-colors",
        "hover:bg-white/5",
      )}
      style={{ color: "var(--text-secondary)" }}
    >
      {children}
    </Link>
  );
}
