import Link from "next/link";
import {
  Github,
  TrendingUp,
  Twitter,
  Mail,
} from "lucide-react";

import { MarketingNav } from "@/components/marketing/MarketingNav";

export const dynamic = "force-static";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      className="mesh-bg"
      style={{ background: "var(--bg-app)", minHeight: "100vh" }}
    >
      <MarketingNav />
      <main>{children}</main>
      <MarketingFooter />
    </div>
  );
}

function MarketingFooter() {
  return (
    <footer
      className="mt-24 border-t"
      style={{
        background: "var(--bg-surface)",
        borderColor: "var(--border-default)",
        color: "var(--text-secondary)",
      }}
    >
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-12 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr]">
          <div>
            <Link
              href="/"
              className="flex items-center gap-2"
              style={{ color: "var(--text-primary)" }}
            >
              <span
                className="inline-flex h-7 w-7 items-center justify-center rounded-md"
                style={{
                  background: "var(--gradient-hero)",
                  boxShadow: "var(--shadow-glow-primary)",
                }}
              >
                <TrendingUp size={16} color="white" strokeWidth={2.5} />
              </span>
              <span className="text-base font-semibold tracking-tight">
                AQP
              </span>
            </Link>
            <p
              className="mt-4 max-w-sm text-sm leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              The Agentic Quant Platform. Hash-locked agent specs, deployment-consistent RL, twelve backtest engines, multi-tenant by default.
            </p>
            <div className="mt-6 flex items-center gap-3">
              <a
                href="https://github.com/aqp-fund"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="GitHub"
                className="rounded p-1.5 transition-colors hover:bg-white/5"
                style={{ color: "var(--text-secondary)" }}
              >
                <Github size={18} />
              </a>
              <a
                href="https://twitter.com/aqpfund"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Twitter"
                className="rounded p-1.5 transition-colors hover:bg-white/5"
                style={{ color: "var(--text-secondary)" }}
              >
                <Twitter size={18} />
              </a>
              <a
                href="mailto:hello@aqp.fund"
                aria-label="Email"
                className="rounded p-1.5 transition-colors hover:bg-white/5"
                style={{ color: "var(--text-secondary)" }}
              >
                <Mail size={18} />
              </a>
            </div>
          </div>

          <FooterCol
            title="Product"
            links={[
              { href: "/product/agentops", label: "AgentOps" },
              {
                href: "/product/reinforcement-learning",
                label: "Reinforcement Learning",
              },
              { href: "/product/data-platform", label: "Data Platform" },
              { href: "/product/backtesting", label: "Backtesting" },
              { href: "/cloud", label: "Cloud Platform" },
              { href: "/self-hosted", label: "Self-Hosted" },
            ]}
          />

          <FooterCol
            title="Resources"
            links={[
              { href: "/learn", label: "Learn" },
              { href: "/docs", label: "Documentation" },
              { href: "/blog", label: "Blog" },
              { href: "/changelog", label: "Changelog" },
              { href: "/pricing", label: "Pricing" },
            ]}
          />

          <FooterCol
            title="Company"
            links={[
              { href: "/about", label: "About" },
              { href: "/legal/contact", label: "Contact" },
              { href: "/legal/security", label: "Security" },
              { href: "https://status.aqp.fund", label: "Status", external: true },
            ]}
          />

          <FooterCol
            title="Legal"
            links={[
              { href: "/legal/terms", label: "Terms" },
              { href: "/legal/privacy", label: "Privacy" },
              { href: "/legal/dpa", label: "DPA" },
              { href: "/legal/security", label: "Security & SLA" },
            ]}
          />
        </div>

        <div
          className="mt-12 flex flex-col items-start justify-between gap-4 border-t pt-8 md:flex-row md:items-center"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            © {new Date().getFullYear()} Agentic Quant Platform. All rights reserved.
          </div>
          <div className="flex items-center gap-3 text-xs" style={{ color: "var(--text-muted)" }}>
            <span>SOC 2 in progress</span>
            <span aria-hidden>·</span>
            <span>GDPR-ready</span>
            <span aria-hidden>·</span>
            <span>BYOK for every brokerage</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({
  title,
  links,
}: {
  title: string;
  links: { href: string; label: string; external?: boolean }[];
}) {
  return (
    <div>
      <div
        className="mb-4 text-xs font-bold uppercase tracking-wider"
        style={{ color: "var(--text-muted)" }}
      >
        {title}
      </div>
      <ul className="space-y-2">
        {links.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              target={link.external ? "_blank" : undefined}
              rel={link.external ? "noopener noreferrer" : undefined}
              className="text-sm transition-colors hover:text-white"
              style={{ color: "var(--text-secondary)" }}
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
