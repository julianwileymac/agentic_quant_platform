import { cva, type VariantProps } from "class-variance-authority";
import { type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold tracking-wide transition-colors",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-[var(--info-bg)] text-[var(--info-fg)]",
        secondary:
          "border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]",
        positive:
          "border-transparent bg-[var(--pos-bg)] text-[var(--pos-fg)]",
        negative:
          "border-transparent bg-[var(--neg-bg)] text-[var(--neg-fg)]",
        warn:
          "border-transparent bg-[var(--warn-bg)] text-[var(--warn-fg)]",
        outline:
          "border-[var(--border-default)] text-[var(--text-secondary)]",
        sandbox:
          "border-[var(--sandbox-border)] bg-[var(--sandbox-bg)] text-[var(--sandbox-fg)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
