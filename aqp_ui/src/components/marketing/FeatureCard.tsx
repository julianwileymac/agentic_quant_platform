import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import {
  FeatureCardClient,
  type FeatureCardTone,
} from "./FeatureCardClient";

interface FeatureCardProps {
  icon: LucideIcon;
  title: string;
  body: ReactNode;
  /** Optional badge above the title (e.g. "new"). */
  badge?: string;
  /** Optional href turns the card into a link with hover affordance. */
  href?: string;
  /** Color of the icon glow ring. */
  tone?: FeatureCardTone;
  className?: string;
}

const TONE_COLORS = {
  primary: {
    bg: "var(--accent-primary)",
    accent: "#1677ff",
    glow: "var(--shadow-glow-primary)",
  },
  secondary: {
    bg: "var(--accent-secondary)",
    accent: "#722ed1",
    glow: "var(--shadow-glow-secondary)",
  },
  tertiary: {
    bg: "var(--accent-tertiary)",
    accent: "#10b981",
    glow: "var(--shadow-glow-success)",
  },
  warn: {
    bg: "var(--warn-fg)",
    accent: "#f59e0b",
    glow: "0 0 60px -10px rgba(245,158,11,0.4)",
  },
} as const;

/**
 * Server-side facade for the feature card.
 *
 * Pre-renders the icon inside a gradient-tinted circle so the icon
 * constructor never crosses the React Server Component → Client
 * Component boundary. The actual animated card body lives in
 * `FeatureCardClient`.
 */
export function FeatureCard({
  icon: Icon,
  title,
  body,
  badge,
  href,
  tone = "primary",
  className,
}: FeatureCardProps) {
  const colors = TONE_COLORS[tone];
  const iconSlot = (
    <div
      className="inline-flex h-11 w-11 items-center justify-center rounded-lg"
      style={{
        background: `linear-gradient(135deg, ${colors.bg}, ${colors.bg}80)`,
        boxShadow: colors.glow,
      }}
    >
      <Icon size={20} color="white" strokeWidth={2} />
    </div>
  );
  return (
    <FeatureCardClient
      iconSlot={iconSlot}
      title={title}
      body={body}
      badge={badge}
      href={href}
      tone={tone}
      toneAccent={colors.accent}
      className={className}
    />
  );
}
