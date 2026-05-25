"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface FeatureGridProps {
  children: ReactNode;
  columns?: 2 | 3 | 4;
  className?: string;
}

/**
 * Responsive feature card grid with stagger animation on viewport entry.
 *
 * Wraps a list of `<FeatureCard />` children; each child becomes a grid item
 * that animates in with a 60ms stagger.
 */
export function FeatureGrid({
  children,
  columns = 3,
  className,
}: FeatureGridProps) {
  const colsClass =
    columns === 2
      ? "md:grid-cols-2"
      : columns === 4
        ? "md:grid-cols-2 lg:grid-cols-4"
        : "md:grid-cols-2 lg:grid-cols-3";

  return (
    <motion.div
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-80px" }}
      variants={{
        hidden: {},
        show: { transition: { staggerChildren: 0.08 } },
      }}
      className={cn("grid grid-cols-1 gap-6", colsClass, className)}
    >
      {Array.isArray(children)
        ? children.map((child, i) => (
            <motion.div
              // biome-ignore lint/suspicious/noArrayIndexKey: marketing copy is stable
              key={i}
              variants={{
                hidden: { opacity: 0, y: 16 },
                show: {
                  opacity: 1,
                  y: 0,
                  transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
                },
              }}
            >
              {child}
            </motion.div>
          ))
        : children}
    </motion.div>
  );
}
