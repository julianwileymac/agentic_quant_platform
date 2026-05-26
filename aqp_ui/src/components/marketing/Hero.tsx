import type { LucideIcon } from "lucide-react";
import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { HeroClient, type HeroCta } from "./HeroClient";

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

/**
 * Server-side facade for the marketing hero.
 *
 * Pre-renders the eyebrow icon (a lucide-react ForwardRef constructor)
 * into a ReactNode slot, then delegates animation + layout to
 * `HeroClient`. This pattern keeps every marketing page callable from a
 * Server Component without violating the App Router serialization
 * boundary.
 */
export function Hero({
  eyebrow,
  eyebrowIcon: EyebrowIcon = Sparkles,
  ...rest
}: HeroProps) {
  const eyebrowSlot = eyebrow ? (
    <>
      <EyebrowIcon size={12} />
      {eyebrow}
    </>
  ) : null;
  return <HeroClient eyebrowSlot={eyebrowSlot} {...rest} />;
}

export type { HeroCta };
