"use client";

import { motion, useInView, useMotionValue, useTransform, animate } from "framer-motion";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/cn";

interface Stat {
  /** Numeric portion (e.g. 9, 17, 5). */
  value: number;
  /** Optional suffix appended to the value (e.g. "+", "x", "%"). */
  suffix?: string;
  /** Optional prefix prepended to the value (e.g. "$"). */
  prefix?: string;
  /** Label shown below the number. */
  label: string;
  /** Tone for the number color. */
  tone?: "primary" | "secondary" | "tertiary" | "warn";
}

interface StatStripProps {
  stats: Stat[];
  className?: string;
}

const TONE_COLORS = {
  primary: "var(--accent-primary)",
  secondary: "var(--accent-secondary)",
  tertiary: "var(--accent-tertiary)",
  warn: "var(--warn-fg)",
} as const;

function AnimatedNumber({
  value,
  prefix = "",
  suffix = "",
  tone = "primary",
}: {
  value: number;
  prefix?: string;
  suffix?: string;
  tone?: keyof typeof TONE_COLORS;
}) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const inView = useInView(ref, { once: true, margin: "-50px" });
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (latest) => Math.round(latest));

  useEffect(() => {
    if (!inView) return;
    const controls = animate(mv, value, {
      duration: 1.4,
      ease: [0.22, 1, 0.36, 1],
    });
    return controls.stop;
  }, [inView, mv, value]);

  useEffect(() => {
    return rounded.on("change", (latest) => {
      if (ref.current) ref.current.textContent = `${prefix}${latest}${suffix}`;
    });
  }, [prefix, suffix, rounded]);

  return (
    <span
      ref={ref}
      className="tabular"
      style={{ color: TONE_COLORS[tone] }}
    >
      {prefix}0{suffix}
    </span>
  );
}

export function StatStrip({ stats, className }: StatStripProps) {
  return (
    <section
      className={cn(
        "border-y",
        className,
      )}
      style={{
        borderColor: "var(--border-default)",
        background: "var(--glass-bg)",
        backdropFilter: "blur(var(--glass-blur))",
      }}
    >
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-6 px-6 py-10 md:grid-cols-4">
        {stats.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-50px" }}
            transition={{ delay: i * 0.08, duration: 0.5 }}
            className="text-center"
          >
            <div className="text-3xl font-bold tracking-tight md:text-4xl">
              <AnimatedNumber
                value={stat.value}
                prefix={stat.prefix}
                suffix={stat.suffix}
                tone={stat.tone}
              />
            </div>
            <div
              className="mt-2 text-xs font-medium uppercase tracking-wider md:text-sm"
              style={{ color: "var(--text-muted)" }}
            >
              {stat.label}
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
