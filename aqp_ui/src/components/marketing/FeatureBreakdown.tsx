"use client";

import { Check } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { MotionInView } from "./MotionInView";

interface FeatureBreakdownProps {
  eyebrow?: string;
  title: string;
  body: ReactNode;
  /** Bullet checklist of capabilities. */
  bullets?: string[];
  /** Optional inline learn-more link. */
  cta?: { label: string; href: string };
  /** Right-hand visual (illustration, code block, chart, etc.). */
  visual: ReactNode;
  /** When true, reverse the order so the visual is on the left. */
  reverse?: boolean;
  /** Tone for the eyebrow badge. */
  tone?: "primary" | "secondary" | "tertiary" | "warn";
}

const TONE_COLORS = {
  primary: "var(--accent-primary)",
  secondary: "var(--accent-secondary)",
  tertiary: "var(--accent-tertiary)",
  warn: "var(--warn-fg)",
} as const;

export function FeatureBreakdown({
  eyebrow,
  title,
  body,
  bullets,
  cta,
  visual,
  reverse = false,
  tone = "primary",
}: FeatureBreakdownProps) {
  const accent = TONE_COLORS[tone];
  return (
    <section className="py-16 md:py-24">
      <div
        className={cn(
          "mx-auto grid max-w-7xl items-center gap-12 px-6 lg:gap-16",
          "lg:grid-cols-2",
        )}
      >
        <MotionInView
          from={reverse ? "right" : "left"}
          className={cn("order-2", !reverse && "lg:order-1", reverse && "lg:order-2")}
        >
          {eyebrow ? (
            <div
              className="mb-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider"
              style={{
                borderColor: "var(--border-default)",
                color: accent,
                background: "var(--glass-bg)",
              }}
            >
              {eyebrow}
            </div>
          ) : null}
          <h2
            className="text-balance text-3xl font-bold tracking-tight md:text-4xl"
            style={{ color: "var(--text-primary)", lineHeight: 1.1 }}
          >
            {title}
          </h2>
          <div
            className="mt-5 text-base leading-relaxed md:text-lg"
            style={{ color: "var(--text-secondary)" }}
          >
            {body}
          </div>
          {bullets && bullets.length > 0 ? (
            <ul className="mt-6 space-y-3">
              {bullets.map((bullet) => (
                <li
                  key={bullet}
                  className="flex items-start gap-3 text-sm leading-relaxed md:text-base"
                  style={{ color: "var(--text-primary)" }}
                >
                  <span
                    className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full"
                    style={{
                      background: `${accent}22`,
                      color: accent,
                    }}
                  >
                    <Check size={12} strokeWidth={3} />
                  </span>
                  <span>{bullet}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {cta ? (
            <Link
              href={cta.href}
              className="mt-8 inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-semibold transition-colors hover:bg-white/5"
              style={{
                borderColor: "var(--border-default)",
                color: "var(--text-primary)",
              }}
            >
              {cta.label}
            </Link>
          ) : null}
        </MotionInView>

        <MotionInView
          from={reverse ? "left" : "right"}
          className={cn("order-1", !reverse && "lg:order-2", reverse && "lg:order-1")}
        >
          {visual}
        </MotionInView>
      </div>
    </section>
  );
}
