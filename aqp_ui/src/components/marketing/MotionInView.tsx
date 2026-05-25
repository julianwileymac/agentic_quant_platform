"use client";

import { type HTMLMotionProps, motion } from "framer-motion";
import type { ReactNode } from "react";

interface MotionInViewProps extends HTMLMotionProps<"div"> {
  /** Stagger delay in seconds. */
  delay?: number;
  /** Direction of the entry slide. */
  from?: "up" | "down" | "left" | "right" | "scale" | "fade";
  /** Children. */
  children: ReactNode;
}

const FROM_OFFSETS = {
  up: { y: 24, x: 0, scale: 1 },
  down: { y: -24, x: 0, scale: 1 },
  left: { y: 0, x: 24, scale: 1 },
  right: { y: 0, x: -24, scale: 1 },
  scale: { y: 0, x: 0, scale: 0.96 },
  fade: { y: 0, x: 0, scale: 1 },
} as const;

/**
 * Tiny framer-motion wrapper for in-viewport reveal animations.
 *
 * Use everywhere a section, card, or row should animate in once on scroll.
 * Honours `prefers-reduced-motion` automatically via framer-motion.
 */
export function MotionInView({
  children,
  delay = 0,
  from = "up",
  className,
  ...rest
}: MotionInViewProps) {
  const offset = FROM_OFFSETS[from];
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, ...offset }}
      whileInView={{ opacity: 1, x: 0, y: 0, scale: 1 }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      viewport={{ once: true, margin: "-80px" }}
      {...rest}
    >
      {children}
    </motion.div>
  );
}
