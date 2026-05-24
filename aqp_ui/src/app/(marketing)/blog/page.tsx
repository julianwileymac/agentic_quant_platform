import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Blog",
  description: "Engineering and research posts from the AQP team.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

interface Post {
  slug: string;
  title: string;
  date: string;
  excerpt: string;
}

const POSTS: Post[] = [
  {
    slug: "agentic-quant-paradigm",
    title: "Why agentic quant is the next paradigm",
    date: "2026-05-12",
    excerpt:
      "Agentic loops produce better alpha than monolithic scripts. Here's why hash-locked specs are the bridge.",
  },
  {
    slug: "multi-tenancy-financial-platforms",
    title: "Multi-tenancy for financial platforms: bridge over silo",
    date: "2026-04-28",
    excerpt:
      "Pool the stateless layers, silo the high-risk stateful ones, never compromise on tenant data isolation.",
  },
];

export default function BlogPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-4xl font-bold" style={{ color: "var(--text-primary)" }}>
        Blog
      </h1>
      <p className="mt-4 text-base" style={{ color: "var(--text-secondary)" }}>
        Engineering and research notes from the AQP team. Long-form, technical, no fluff.
      </p>
      <div className="mt-10 space-y-6">
        {POSTS.map((post) => (
          <article
            key={post.slug}
            className="rounded-md border p-6"
            style={{ borderColor: "var(--border-default)", background: "var(--bg-elevated)" }}
          >
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              {new Date(post.date).toLocaleDateString("en-US", {
                year: "numeric",
                month: "long",
                day: "numeric",
              })}
            </div>
            <h2 className="mt-1 text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
              {post.title}
            </h2>
            <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
              {post.excerpt}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
