import { cn } from "@/lib/cn";
import { MotionInView } from "./MotionInView";

interface SectionHeaderProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  align?: "center" | "left";
  className?: string;
  /** When true, render the title with the accent gradient. */
  gradient?: boolean;
}

export function SectionHeader({
  eyebrow,
  title,
  subtitle,
  align = "center",
  className,
  gradient = false,
}: SectionHeaderProps) {
  return (
    <div
      className={cn(
        "mb-12",
        align === "center" && "text-center",
        className,
      )}
    >
      <MotionInView from="up">
        {eyebrow ? (
          <div
            className={cn(
              "mb-3 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider",
            )}
            style={{
              borderColor: "var(--border-default)",
              color: "var(--accent-primary)",
              background: "var(--glass-bg)",
              backdropFilter: "blur(8px)",
            }}
          >
            {eyebrow}
          </div>
        ) : null}
        <h2
          className={cn(
            "max-w-3xl text-balance text-3xl font-bold tracking-tight md:text-4xl",
            align === "center" && "mx-auto",
            gradient && "heading-gradient",
          )}
          style={!gradient ? { color: "var(--text-primary)" } : undefined}
        >
          {title}
        </h2>
        {subtitle ? (
          <p
            className={cn(
              "mt-4 max-w-2xl text-base leading-relaxed md:text-lg",
              align === "center" && "mx-auto",
            )}
            style={{ color: "var(--text-secondary)" }}
          >
            {subtitle}
          </p>
        ) : null}
      </MotionInView>
    </div>
  );
}
