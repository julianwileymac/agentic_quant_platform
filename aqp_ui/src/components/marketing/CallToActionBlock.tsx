import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/cn";
import { MotionInView } from "./MotionInView";

interface Cta {
  label: string;
  href: string;
  external?: boolean;
}

interface CallToActionBlockProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  primaryCta: Cta;
  secondaryCta?: Cta;
  className?: string;
}

export function CallToActionBlock({
  eyebrow,
  title,
  subtitle,
  primaryCta,
  secondaryCta,
  className,
}: CallToActionBlockProps) {
  return (
    <section className={cn("px-6 py-24", className)}>
      <MotionInView from="up">
        <div
          className="relative mx-auto max-w-4xl overflow-hidden rounded-2xl p-12 text-center md:p-16"
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border-default)",
            boxShadow: "var(--shadow-elevated)",
          }}
        >
          {/* Decorative gradient blobs */}
          <div
            aria-hidden
            className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full"
            style={{
              background:
                "radial-gradient(circle, rgba(22,119,255,0.22), transparent 70%)",
              filter: "blur(40px)",
            }}
          />
          <div
            aria-hidden
            className="pointer-events-none absolute -bottom-24 -right-24 h-72 w-72 rounded-full"
            style={{
              background:
                "radial-gradient(circle, rgba(114,46,209,0.22), transparent 70%)",
              filter: "blur(40px)",
            }}
          />

          <div className="relative">
            {eyebrow ? (
              <div
                className="mb-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider"
                style={{
                  borderColor: "var(--border-default)",
                  color: "var(--accent-primary)",
                  background: "var(--glass-bg)",
                }}
              >
                {eyebrow}
              </div>
            ) : null}
            <h2
              className="text-balance text-3xl font-bold tracking-tight md:text-4xl"
              style={{ color: "var(--text-primary)" }}
            >
              {title}
            </h2>
            {subtitle ? (
              <p
                className="mx-auto mt-4 max-w-2xl text-base leading-relaxed md:text-lg"
                style={{ color: "var(--text-secondary)" }}
              >
                {subtitle}
              </p>
            ) : null}
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                href={primaryCta.href}
                target={primaryCta.external ? "_blank" : undefined}
                rel={primaryCta.external ? "noopener noreferrer" : undefined}
                className="group inline-flex items-center gap-2 rounded-md px-6 py-3 text-base font-semibold transition-transform hover:scale-[1.02]"
                style={{
                  background: "var(--accent-primary)",
                  color: "white",
                  boxShadow: "var(--shadow-glow-primary)",
                }}
              >
                {primaryCta.label}
                <ArrowRight
                  size={16}
                  className="transition-transform group-hover:translate-x-0.5"
                />
              </Link>
              {secondaryCta ? (
                <Link
                  href={secondaryCta.href}
                  target={secondaryCta.external ? "_blank" : undefined}
                  rel={
                    secondaryCta.external ? "noopener noreferrer" : undefined
                  }
                  className="rounded-md border px-6 py-3 text-base font-semibold transition-colors hover:bg-white/5"
                  style={{
                    borderColor: "var(--border-default)",
                    color: "var(--text-primary)",
                  }}
                >
                  {secondaryCta.label}
                </Link>
              ) : null}
            </div>
          </div>
        </div>
      </MotionInView>
    </section>
  );
}
