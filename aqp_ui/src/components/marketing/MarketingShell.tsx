import { cn } from "@/lib/cn";
import type { ReactNode } from "react";

interface MarketingShellProps {
  children: ReactNode;
  /** Adds the gradient mesh background. */
  mesh?: boolean;
  className?: string;
}

/**
 * Page-level wrapper for marketing pages.
 *
 * Provides the optional `mesh-bg` background and full viewport min-height.
 * Pages compose `MarketingShell` > sections directly.
 */
export function MarketingShell({
  children,
  mesh = true,
  className,
}: MarketingShellProps) {
  return (
    <div
      className={cn(
        "relative w-full",
        mesh && "mesh-bg",
        className,
      )}
      style={{ minHeight: "calc(100vh - 128px)" }}
    >
      {children}
    </div>
  );
}

interface ContainerProps {
  children: ReactNode;
  size?: "narrow" | "default" | "wide";
  className?: string;
}

/**
 * Reusable max-width container with marketing padding.
 *
 * - `narrow` = 56rem (prose / single-column)
 * - `default` = 80rem (most marketing sections)
 * - `wide` = 96rem (hero + edge-to-edge feature breakdowns)
 */
export function Container({
  children,
  size = "default",
  className,
}: ContainerProps) {
  const maxW =
    size === "narrow"
      ? "max-w-3xl"
      : size === "wide"
        ? "max-w-screen-2xl"
        : "max-w-7xl";
  return (
    <div className={cn("mx-auto px-6", maxW, className)}>{children}</div>
  );
}
