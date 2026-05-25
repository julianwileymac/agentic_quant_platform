"use client";

import { AnimatePresence, motion, useScroll, useTransform } from "framer-motion";
import {
  Activity,
  BookOpen,
  BrainCircuit,
  ChevronDown,
  Cloud,
  Cpu,
  Database,
  Layers,
  Menu,
  Sparkles,
  TrendingUp,
  Workflow,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

interface ProductLink {
  href: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

const PRODUCTS: ProductLink[] = [
  {
    href: "/product/agentops",
    label: "AgentOps",
    description: "Hash-locked specs, multi-agent patterns, Workflow Studio.",
    icon: BrainCircuit,
  },
  {
    href: "/product/reinforcement-learning",
    label: "Reinforcement Learning",
    description: "RLRuntime, FinRL-X pipeline, PRUDEX-Compass eval.",
    icon: Sparkles,
  },
  {
    href: "/product/data-platform",
    label: "Data Platform",
    description: "Medallion Iceberg, HierarchicalRAG, lineage graph.",
    icon: Database,
  },
  {
    href: "/product/backtesting",
    label: "Backtesting",
    description: "9 engines, capability dispatch, optimal control.",
    icon: Activity,
  },
  {
    href: "/cloud",
    label: "Cloud Platform",
    description: "Multi-tenant PaaS at app.aqp.fund.",
    icon: Cloud,
  },
  {
    href: "/self-hosted",
    label: "Self-Hosted",
    description: "Local-first AQP engine, K8s, AQP IDE.",
    icon: Cpu,
  },
];

const TOP_LINKS: { href: string; label: string; icon?: React.ComponentType<{ size?: number }> }[] = [
  { href: "/learn", label: "Learn", icon: BookOpen },
  { href: "/pricing", label: "Pricing" },
  { href: "/docs", label: "Docs" },
  { href: "/about", label: "About" },
  { href: "/blog", label: "Blog" },
  { href: "/changelog", label: "Changelog" },
];

export function MarketingNav() {
  const [productsOpen, setProductsOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { scrollY } = useScroll();
  const bgAlpha = useTransform(scrollY, [0, 80], [0.5, 0.85]);
  const borderAlpha = useTransform(scrollY, [0, 80], [0.4, 1]);

  // Close on route change / escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setProductsOpen(false);
        setMobileOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <motion.header
      className="sticky top-0 z-50 w-full"
      style={{
        backdropFilter: "blur(16px) saturate(160%)",
        WebkitBackdropFilter: "blur(16px) saturate(160%)",
      }}
    >
      <motion.div
        aria-hidden
        className="absolute inset-0 -z-10"
        style={{
          background: useTransform(
            bgAlpha,
            (v) => `rgba(15, 23, 42, ${v})`,
          ),
          borderBottom: "1px solid",
          borderBottomColor: useTransform(
            borderAlpha,
            (v) => `rgba(51, 65, 85, ${v})`,
          ),
        }}
      />

      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <Link
          href="/"
          className="flex items-center gap-2 transition-opacity hover:opacity-90"
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
          <span className="text-base font-semibold tracking-tight">AQP</span>
        </Link>

        <nav className="hidden items-center gap-1 lg:flex">
          <ProductsDropdown
            open={productsOpen}
            onOpenChange={setProductsOpen}
          />
          {TOP_LINKS.map((link) => (
            <NavLink key={link.href} href={link.href}>
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="hidden items-center gap-2 lg:flex">
          <Link
            href="/login"
            className="rounded-md px-3 py-1.5 text-sm font-medium transition-colors hover:bg-white/5"
            style={{ color: "var(--text-secondary)" }}
          >
            Log in
          </Link>
          <Link
            href="/signup"
            className="rounded-md px-3 py-1.5 text-sm font-semibold transition-transform hover:scale-[1.03]"
            style={{
              color: "white",
              background: "var(--accent-primary)",
              boxShadow: "0 0 0 1px rgba(22,119,255,0.4)",
            }}
          >
            Sign up
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setMobileOpen((p) => !p)}
          className="rounded p-2 lg:hidden"
          style={{ color: "var(--text-primary)" }}
          aria-label="Toggle navigation"
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      <AnimatePresence>
        {mobileOpen ? (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            className="lg:hidden"
            style={{
              background: "rgba(15,23,42,0.95)",
              borderBottom: "1px solid var(--border-default)",
            }}
          >
            <div className="space-y-4 px-6 pb-6 pt-2">
              <div>
                <div
                  className="mb-2 text-xs font-bold uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  Products
                </div>
                <div className="grid grid-cols-1 gap-1">
                  {PRODUCTS.map((p) => (
                    <Link
                      key={p.href}
                      href={p.href}
                      onClick={() => setMobileOpen(false)}
                      className="flex items-center gap-3 rounded-md px-3 py-2 transition-colors hover:bg-white/5"
                    >
                      <p.icon size={16} className="text-[var(--accent-primary)]" />
                      <span
                        className="text-sm font-semibold"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {p.label}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
              <div>
                <div
                  className="mb-2 text-xs font-bold uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  Resources
                </div>
                <div className="grid grid-cols-2 gap-1">
                  {TOP_LINKS.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      onClick={() => setMobileOpen(false)}
                      className="rounded-md px-3 py-2 text-sm transition-colors hover:bg-white/5"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {link.label}
                    </Link>
                  ))}
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                <Link
                  href="/login"
                  onClick={() => setMobileOpen(false)}
                  className="flex-1 rounded-md border px-3 py-2 text-center text-sm font-medium"
                  style={{
                    borderColor: "var(--border-default)",
                    color: "var(--text-primary)",
                  }}
                >
                  Log in
                </Link>
                <Link
                  href="/signup"
                  onClick={() => setMobileOpen(false)}
                  className="flex-1 rounded-md px-3 py-2 text-center text-sm font-semibold"
                  style={{
                    background: "var(--accent-primary)",
                    color: "white",
                  }}
                >
                  Sign up
                </Link>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.header>
  );
}

function NavLink({
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
        "rounded px-3 py-1.5 text-sm font-medium transition-colors hover:bg-white/5",
      )}
      style={{ color: "var(--text-secondary)" }}
    >
      {children}
    </Link>
  );
}

function ProductsDropdown({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  return (
    <div
      className="relative"
      onMouseEnter={() => onOpenChange(true)}
      onMouseLeave={() => onOpenChange(false)}
    >
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-expanded={open}
        className={cn(
          "inline-flex items-center gap-1 rounded px-3 py-1.5 text-sm font-medium transition-colors hover:bg-white/5",
        )}
        style={{ color: "var(--text-secondary)" }}
      >
        Products
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown size={14} />
        </motion.span>
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="absolute left-1/2 top-full mt-1 w-[640px] -translate-x-1/2 rounded-xl p-3"
            style={{
              background: "rgba(15,23,42,0.95)",
              border: "1px solid var(--glass-border-strong)",
              backdropFilter: "blur(20px) saturate(180%)",
              boxShadow: "var(--shadow-elevated)",
            }}
          >
            <div className="grid grid-cols-2 gap-1">
              {PRODUCTS.map((p) => (
                <Link
                  key={p.href}
                  href={p.href}
                  onClick={() => onOpenChange(false)}
                  className="group flex items-start gap-3 rounded-lg p-3 transition-colors hover:bg-white/5"
                >
                  <span
                    className="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md"
                    style={{
                      background: "rgba(22,119,255,0.12)",
                      color: "var(--accent-primary)",
                    }}
                  >
                    <p.icon size={18} />
                  </span>
                  <div>
                    <div
                      className="text-sm font-semibold"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {p.label}
                    </div>
                    <div
                      className="mt-0.5 text-xs leading-snug"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {p.description}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
            <div
              className="mt-2 flex items-center justify-between rounded-lg px-3 py-2"
              style={{
                background: "rgba(22,119,255,0.06)",
                border: "1px solid rgba(22,119,255,0.2)",
              }}
            >
              <div className="flex items-center gap-2">
                <Workflow
                  size={14}
                  style={{ color: "var(--accent-primary)" }}
                />
                <span
                  className="text-xs font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  Architecture overview
                </span>
              </div>
              <Link
                href="/about#architecture"
                onClick={() => onOpenChange(false)}
                className="text-xs font-semibold"
                style={{ color: "var(--accent-primary)" }}
              >
                See the full system →
              </Link>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

// Keep the Layers icon as a re-export so callers can import nav helpers from
// one place if needed (e.g. footer-with-icons in future). Not used directly
// here but reserved so the file owns the marketing-nav vocabulary.
export const __NAV_ICONS__ = { Layers };
