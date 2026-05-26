"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type FeatureCardTone = "primary" | "secondary" | "tertiary" | "warn";

interface FeatureCardClientProps {
  iconSlot: ReactNode;
  title: string;
  body: ReactNode;
  badge?: string;
  href?: string;
  tone?: FeatureCardTone;
  toneAccent: string;
  className?: string;
}

/**
 * Internal client component for FeatureCard.
 *
 * Receives the pre-rendered icon slot (icon + gradient circle) so that
 * lucide-react constructors never cross the server → client boundary.
 * Use `<FeatureCard />` from the server-side facade for marketing pages.
 */
export function FeatureCardClient({
  iconSlot,
  title,
  body,
  badge,
  href,
  toneAccent,
  className,
}: FeatureCardClientProps) {
  const inner = (
    <motion.div
      whileHover={{ y: -4 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "group relative h-full overflow-hidden rounded-xl p-6 transition-colors",
        className,
      )}
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(var(--glass-blur))",
        boxShadow: "var(--shadow-card)",
      }}
    >
      <div
        aria-hidden
        className="absolute inset-0 -z-10 opacity-0 transition-opacity duration-500 group-hover:opacity-100"
        style={{
          background: `radial-gradient(circle at 0% 0%, ${toneAccent}22, transparent 60%)`,
        }}
      />

      <div className="flex items-start justify-between">
        {iconSlot}
        {badge ? (
          <div
            className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
            style={{
              background: "var(--glass-bg-strong)",
              border: "1px solid var(--glass-border-strong)",
              color: "var(--accent-tertiary)",
            }}
          >
            {badge}
          </div>
        ) : null}
      </div>

      <h3
        className="mt-5 text-lg font-semibold tracking-tight"
        style={{ color: "var(--text-primary)" }}
      >
        {title}
      </h3>
      <div
        className="mt-2 text-sm leading-relaxed"
        style={{ color: "var(--text-secondary)" }}
      >
        {body}
      </div>

      {href ? (
        <div
          className="mt-5 inline-flex items-center gap-1 text-sm font-semibold"
          style={{ color: "var(--accent-primary)" }}
        >
          Learn more
          <ArrowUpRight
            size={14}
            className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
          />
        </div>
      ) : null}
    </motion.div>
  );

  if (!href) return inner;
  return (
    <Link href={href} className="block h-full no-underline">
      {inner}
    </Link>
  );
}
