"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";

interface FaqItem {
  question: string;
  answer: React.ReactNode;
}

interface FaqAccordionProps {
  items: FaqItem[];
  className?: string;
  /** Initially open index. */
  defaultOpen?: number;
}

export function FaqAccordion({
  items,
  className,
  defaultOpen,
}: FaqAccordionProps) {
  const [openIdx, setOpenIdx] = useState<number | null>(defaultOpen ?? null);

  return (
    <div className={cn("mx-auto max-w-3xl space-y-3", className)}>
      {items.map((item, i) => {
        const isOpen = openIdx === i;
        return (
          <div
            key={item.question}
            className="overflow-hidden rounded-lg"
            style={{
              background: "var(--glass-bg)",
              border: `1px solid ${
                isOpen ? "var(--accent-primary)" : "var(--glass-border)"
              }`,
              backdropFilter: "blur(var(--glass-blur))",
              transition: "border-color 0.2s",
            }}
          >
            <button
              type="button"
              onClick={() => setOpenIdx(isOpen ? null : i)}
              className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
              aria-expanded={isOpen}
            >
              <span
                className="text-base font-semibold"
                style={{ color: "var(--text-primary)" }}
              >
                {item.question}
              </span>
              <motion.div
                animate={{ rotate: isOpen ? 180 : 0 }}
                transition={{ duration: 0.2 }}
                style={{ color: "var(--text-muted)" }}
              >
                <ChevronDown size={18} />
              </motion.div>
            </button>
            <AnimatePresence initial={false}>
              {isOpen ? (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                >
                  <div
                    className="px-5 pb-4 text-sm leading-relaxed"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {item.answer}
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
