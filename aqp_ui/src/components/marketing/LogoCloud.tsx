"use client";

import { motion } from "framer-motion";

import { cn } from "@/lib/cn";

interface LogoCloudProps {
  title?: string;
  /**
   * Items show as text-only chips (no logo files needed). Mirrors the existing
   * "Built on/with" pattern; for real customer logos, swap for `<img>` later.
   */
  items: string[];
  className?: string;
}

export function LogoCloud({ title, items, className }: LogoCloudProps) {
  return (
    <section
      className={cn(
        "border-y px-6 py-12",
        className,
      )}
      style={{
        borderColor: "var(--border-default)",
        background: "var(--glass-bg)",
      }}
    >
      <div className="mx-auto max-w-7xl">
        {title ? (
          <div
            className="mb-6 text-center text-xs font-semibold uppercase tracking-wider"
            style={{ color: "var(--text-muted)" }}
          >
            {title}
          </div>
        ) : null}
        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-50px" }}
          variants={{
            hidden: {},
            show: { transition: { staggerChildren: 0.05 } },
          }}
          className="flex flex-wrap items-center justify-center gap-3"
        >
          {items.map((item) => (
            <motion.div
              key={item}
              variants={{
                hidden: { opacity: 0, y: 8 },
                show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
              }}
              className="rounded-md border px-4 py-2 text-sm font-medium"
              style={{
                borderColor: "var(--border-default)",
                background: "var(--bg-elevated)",
                color: "var(--text-secondary)",
              }}
            >
              {item}
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
