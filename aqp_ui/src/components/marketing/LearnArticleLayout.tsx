import Link from "next/link";
import { ArrowRight, BookOpen, Clock } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface RelatedArticle {
  href: string;
  title: string;
  category: string;
}

interface TocItem {
  /** Anchor `id` (without the `#`). */
  id: string;
  label: string;
  /** Optional nesting level. */
  level?: 2 | 3;
}

interface LearnArticleLayoutProps {
  eyebrow: string;
  title: string;
  /** Estimated reading time in minutes. */
  readMinutes: number;
  /** Optional "Published / updated" date string. */
  dateLine?: string;
  /** Right-rail anchor TOC. */
  toc: TocItem[];
  /** Right-rail related articles. */
  related?: RelatedArticle[];
  /** Optional "Try in AQP" call-to-action card. */
  cta?: { title: string; body: string; label: string; href: string };
  children: ReactNode;
  className?: string;
}

/**
 * Long-form article shell for /learn pages.
 *
 * Two-column layout: max-w-3xl prose body on the left, sticky TOC + related +
 * CTA card on the right. The body uses `.prose-article` typography from
 * globals.css.
 */
export function LearnArticleLayout({
  eyebrow,
  title,
  readMinutes,
  dateLine,
  toc,
  related,
  cta,
  children,
  className,
}: LearnArticleLayoutProps) {
  return (
    <article className={cn("relative mx-auto max-w-7xl px-6 py-12", className)}>
      <header className="mb-12 max-w-3xl">
        <div
          className="mb-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider"
          style={{
            borderColor: "var(--border-default)",
            color: "var(--accent-primary)",
            background: "var(--glass-bg)",
          }}
        >
          <BookOpen size={12} />
          {eyebrow}
        </div>
        <h1
          className="text-balance text-4xl font-bold tracking-tight md:text-5xl"
          style={{ color: "var(--text-primary)", lineHeight: 1.1 }}
        >
          {title}
        </h1>
        <div
          className="mt-5 flex items-center gap-4 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          <span className="inline-flex items-center gap-1.5">
            <Clock size={12} />
            {readMinutes} min read
          </span>
          {dateLine ? <span>·</span> : null}
          {dateLine ? <span>{dateLine}</span> : null}
        </div>
      </header>

      <div className="grid gap-12 lg:grid-cols-[1fr_240px]">
        <div className="prose-article max-w-3xl">{children}</div>

        <aside className="hidden lg:block">
          <div className="sticky top-24 space-y-6">
            <div>
              <div
                className="mb-3 text-xs font-bold uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                On this page
              </div>
              <ul className="space-y-2 text-sm">
                {toc.map((item) => (
                  <li
                    key={item.id}
                    style={{
                      paddingLeft: item.level === 3 ? "1rem" : 0,
                    }}
                  >
                    <a
                      href={`#${item.id}`}
                      className="block py-1 transition-colors hover:text-white"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {item.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>

            {related && related.length > 0 ? (
              <div>
                <div
                  className="mb-3 text-xs font-bold uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  Related
                </div>
                <ul className="space-y-3">
                  {related.map((r) => (
                    <li key={r.href}>
                      <Link href={r.href} className="group block">
                        <div
                          className="text-[10px] font-bold uppercase tracking-wider"
                          style={{ color: "var(--accent-primary)" }}
                        >
                          {r.category}
                        </div>
                        <div
                          className="mt-0.5 text-sm font-semibold leading-snug transition-colors group-hover:text-white"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {r.title}
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {cta ? (
              <div
                className="rounded-lg p-4"
                style={{
                  background: "var(--glass-bg-strong)",
                  border: "1px solid var(--accent-primary)",
                }}
              >
                <div
                  className="text-xs font-bold uppercase tracking-wider"
                  style={{ color: "var(--accent-primary)" }}
                >
                  {cta.title}
                </div>
                <p
                  className="mt-2 text-sm leading-relaxed"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {cta.body}
                </p>
                <Link
                  href={cta.href}
                  className="mt-3 inline-flex items-center gap-1 text-sm font-semibold"
                  style={{ color: "var(--accent-primary)" }}
                >
                  {cta.label}
                  <ArrowRight size={14} />
                </Link>
              </div>
            ) : null}
          </div>
        </aside>
      </div>
    </article>
  );
}
