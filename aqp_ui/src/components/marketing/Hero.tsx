"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface HeroCta {
  label: string;
  href: string;
  external?: boolean;
}

interface HeroProps {
  eyebrow?: string;
  eyebrowIcon?: LucideIcon;
  title: string;
  /** Words in the title rendered with the gradient effect. */
  titleHighlight?: string;
  subtitle: string;
  primaryCta?: HeroCta;
  secondaryCta?: HeroCta;
  /** Optional right-side illustration slot. */
  illustration?: ReactNode;
  /** Footer line under the CTAs (compliance / SOC2 / etc.). */
  meta?: string;
  /** Layout variant. */
  variant?: "split" | "centered";
}

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  }),
};

export function Hero({
  eyebrow,
  eyebrowIcon: EyebrowIcon = Sparkles,
  title,
  titleHighlight,
  subtitle,
  primaryCta,
  secondaryCta,
  illustration,
  meta,
  variant = illustration ? "split" : "centered",
}: HeroProps) {
  const renderTitle = () => {
    if (!titleHighlight || !title.includes(titleHighlight)) {
      return (
        <span style={{ color: "var(--text-primary)" }}>{title}</span>
      );
    }
    const [pre, post] = title.split(titleHighlight);
    return (
      <>
        <span style={{ color: "var(--text-primary)" }}>{pre}</span>
        <span className="heading-gradient">{titleHighlight}</span>
        <span style={{ color: "var(--text-primary)" }}>{post}</span>
      </>
    );
  };

  return (
    <section
      className={cn(
        "relative overflow-hidden",
        variant === "split"
          ? "px-6 py-20 md:py-28"
          : "px-6 py-24 md:py-32",
      )}
    >
      {/* Decorative glow */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{ background: "var(--gradient-mesh)" }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/4 -z-10 h-[400px] w-[400px] -translate-x-1/2 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(22,119,255,0.18), transparent 70%)",
          filter: "blur(60px)",
        }}
      />

      <div
        className={cn(
          "mx-auto max-w-7xl",
          variant === "split"
            ? "grid items-center gap-12 lg:grid-cols-[1.1fr_1fr]"
            : "flex flex-col items-center text-center",
        )}
      >
        <div className={variant === "centered" ? "max-w-4xl" : undefined}>
          {eyebrow ? (
            <motion.div
              custom={0}
              initial="hidden"
              animate="show"
              variants={fadeUp}
              className={cn(
                "mb-6 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium tracking-wide",
                variant === "centered" && "mx-auto",
              )}
              style={{
                borderColor: "var(--border-default)",
                color: "var(--text-secondary)",
                background: "var(--glass-bg)",
                backdropFilter: "blur(8px)",
              }}
            >
              <EyebrowIcon size={12} />
              {eyebrow}
            </motion.div>
          ) : null}

          <motion.h1
            custom={1}
            initial="hidden"
            animate="show"
            variants={fadeUp}
            className={cn(
              "text-balance text-4xl font-bold tracking-tight md:text-6xl",
              variant === "centered" && "mx-auto",
            )}
            style={{ lineHeight: 1.05 }}
          >
            {renderTitle()}
          </motion.h1>

          <motion.p
            custom={2}
            initial="hidden"
            animate="show"
            variants={fadeUp}
            className={cn(
              "mt-6 max-w-2xl text-base leading-relaxed md:text-lg",
              variant === "centered" && "mx-auto",
            )}
            style={{ color: "var(--text-secondary)" }}
          >
            {subtitle}
          </motion.p>

          {(primaryCta || secondaryCta) && (
            <motion.div
              custom={3}
              initial="hidden"
              animate="show"
              variants={fadeUp}
              className={cn(
                "mt-10 flex flex-col gap-3 sm:flex-row",
                variant === "centered" && "items-center justify-center",
              )}
            >
              {primaryCta && (
                <Link
                  href={primaryCta.href}
                  target={primaryCta.external ? "_blank" : undefined}
                  rel={primaryCta.external ? "noopener noreferrer" : undefined}
                  className="group inline-flex items-center gap-2 rounded-md px-6 py-3 text-base font-semibold transition-transform hover:scale-[1.02]"
                  style={{
                    background: "var(--accent-primary)",
                    color: "white",
                    boxShadow: "var(--shadow-glow-primary)",
                  }}
                >
                  {primaryCta.label}
                  <ArrowRight
                    size={16}
                    className="transition-transform group-hover:translate-x-0.5"
                  />
                </Link>
              )}
              {secondaryCta && (
                <Link
                  href={secondaryCta.href}
                  target={secondaryCta.external ? "_blank" : undefined}
                  rel={
                    secondaryCta.external ? "noopener noreferrer" : undefined
                  }
                  className="rounded-md border px-6 py-3 text-base font-semibold transition-colors hover:bg-white/5"
                  style={{
                    borderColor: "var(--border-default)",
                    color: "var(--text-primary)",
                  }}
                >
                  {secondaryCta.label}
                </Link>
              )}
            </motion.div>
          )}

          {meta ? (
            <motion.div
              custom={4}
              initial="hidden"
              animate="show"
              variants={fadeUp}
              className="mt-6 text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              {meta}
            </motion.div>
          ) : null}
        </div>

        {variant === "split" && illustration ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
            className="relative w-full"
          >
            {illustration}
          </motion.div>
        ) : null}
      </div>
    </section>
  );
}
