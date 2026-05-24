import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DOCS_INDEX, getDocBySlug } from "@/lib/docs/index";

interface PageProps {
  params: Promise<{ slug?: string[] }>;
}

export async function generateStaticParams(): Promise<{ slug: string[] }[]> {
  return DOCS_INDEX.map((doc) => ({ slug: doc.slug.split("/") }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const path = slug?.join("/") ?? "";
  const doc = getDocBySlug(path);
  if (!doc) return { title: "Docs" };
  return {
    title: doc.title,
    description: doc.description,
  };
}

export const dynamic = "force-static";
export const revalidate = 3600;

export default async function DocsPage({ params }: PageProps) {
  const { slug } = await params;
  const path = slug?.join("/") ?? "";
  if (path === "") {
    return <DocsIndex />;
  }
  const doc = getDocBySlug(path);
  if (!doc) notFound();

  return (
    <div className="mx-auto flex max-w-7xl gap-8 px-6 py-12">
      <DocsSidebar activeSlug={path} />
      <article className="flex-1 max-w-3xl">
        <h1 className="text-3xl font-bold" style={{ color: "var(--text-primary)" }}>
          {doc.title}
        </h1>
        <p className="mt-2 text-base" style={{ color: "var(--text-secondary)" }}>
          {doc.description}
        </p>
        <div
          className="prose prose-invert mt-8 max-w-none text-sm leading-relaxed"
          style={{ color: "var(--text-primary)" }}
        >
          {doc.body}
        </div>
      </article>
    </div>
  );
}

function DocsIndex() {
  return (
    <div className="mx-auto max-w-7xl px-6 py-12">
      <h1 className="text-3xl font-bold" style={{ color: "var(--text-primary)" }}>
        Documentation
      </h1>
      <p className="mt-2 text-base" style={{ color: "var(--text-secondary)" }}>
        Start here to learn the AQP architecture, identity model, multi-tenancy strategies, and how to ship your first strategy.
      </p>
      <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-2">
        {DOCS_INDEX.map((doc) => (
          <Link
            key={doc.slug}
            href={`/docs/${doc.slug}`}
            className="rounded-md border p-5 transition-colors hover:bg-white/5"
            style={{ borderColor: "var(--border-default)", background: "var(--bg-elevated)" }}
          >
            <div className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {doc.title}
            </div>
            <div className="mt-1 text-xs" style={{ color: "var(--text-secondary)" }}>
              {doc.description}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function DocsSidebar({ activeSlug }: { activeSlug: string }) {
  return (
    <aside className="hidden w-56 flex-shrink-0 md:block">
      <div className="sticky top-6">
        <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
          Docs
        </div>
        <nav className="mt-3 flex flex-col gap-1">
          {DOCS_INDEX.map((doc) => {
            const active = doc.slug === activeSlug;
            return (
              <Link
                key={doc.slug}
                href={`/docs/${doc.slug}`}
                className="rounded px-2 py-1.5 text-sm"
                style={{
                  background: active ? "var(--bg-elevated)" : "transparent",
                  color: active ? "var(--text-primary)" : "var(--text-secondary)",
                }}
              >
                {doc.title}
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}
