"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface FeatureCardProps {
  icon: LucideIcon;
  title: string;
  body: ReactNode;
  /** Optional badge above the title (e.g. "new"). */
  badge?: string;
  /** Optional href turns the card into a link with hover affordance. */
  href?: string;
  /** Color of the icon glow ring. */
  tone?: "primary" | "secondary" | "tertiary" | "warn";
  className?: string;
}

const TONE_COLORS = {
  primary: { bg: "var(--accent-primary)", glow: "var(--shadow-glow-primary)" },
  secondary: {
    bg: "var(--accent-secondary)",
    glow: "var(--shadow-glow-secondary)",
  },
  tertiary: {
    bg: "var(--accent-tertiary)",
    glow: "var(--shadow-glow-success)",
  },
  warn: { bg: "var(--warn-fg)", glow: "0 0 60px -10px rgba(245,158,11,0.4)" },
} as const;

export function FeatureCard({
  icon: Icon,
  title,
  body,
  badge,
  href,
  tone = "primary",
  className,
}: FeatureCardProps) {
  const colors = TONE_COLORS[tone];
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
          background: `radial-gradient(circle at 0% 0%, ${colors.bg}22, transparent 60%)`,
        }}
      />

      <div className="flex items-start justify-between">
        <div
          className="inline-flex h-11 w-11 items-center justify-center rounded-lg"
          style={{
            background: `linear-gradient(135deg, ${colors.bg}, ${colors.bg}80)`,
            boxShadow: colors.glow,
          }}
        >
          <Icon size={20} color="white" strokeWidth={2} />
        </div>
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
