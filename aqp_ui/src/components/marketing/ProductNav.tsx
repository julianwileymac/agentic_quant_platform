"use client";

import { motion, useScroll, useTransform } from "framer-motion";

import { cn } from "@/lib/cn";

interface NavItem {
  id: string;
  label: string;
}

interface ProductNavProps {
  items: NavItem[];
  className?: string;
}

/**
 * Sticky in-page anchor nav for long product pages.
 *
 * The background becomes opaque as the user scrolls past the hero.
 */
export function ProductNav({ items, className }: ProductNavProps) {
  const { scrollY } = useScroll();
  const bgOpacity = useTransform(scrollY, [0, 300], [0, 1]);
  const borderOpacity = useTransform(scrollY, [0, 300], [0, 1]);

  return (
    <motion.nav
      className={cn(
        "sticky top-[57px] z-40 w-full transition-shadow",
        className,
      )}
      style={{
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
      }}
    >
      <motion.div
        aria-hidden
        className="absolute inset-0 -z-10"
        style={{
          background: useTransform(
            bgOpacity,
            (o) => `rgba(15, 23, 42, ${0.85 * o})`,
          ),
          borderBottom: "1px solid",
          borderBottomColor: useTransform(
            borderOpacity,
            (o) => `rgba(51, 65, 85, ${o})`,
          ),
        }}
      />
      <div className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto px-6 py-2">
        {items.map((item) => (
          <a
            key={item.id}
            href={`#${item.id}`}
            className="whitespace-nowrap rounded px-3 py-1.5 text-sm font-medium transition-colors hover:bg-white/5"
            style={{ color: "var(--text-secondary)" }}
          >
            {item.label}
          </a>
        ))}
      </div>
    </motion.nav>
  );
}
