import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUpRight, BookOpen, Calendar, Clock, Rss } from "lucide-react";

import { Hero } from "@/components/marketing/Hero";
import { MotionInView } from "@/components/marketing/MotionInView";
import { SectionHeader } from "@/components/marketing/SectionHeader";

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
  category: "Engineering" | "Research" | "Product";
  readMinutes: number;
  /** When true, the post is published; we link to /learn instead until the
   *  individual /blog/[slug] route lands. */
  published?: boolean;
  /** Optional cross-link target for already-shipped long-form articles. */
  href?: string;
}

const POSTS: Post[] = [
  {
    slug: "agentic-quant-paradigm",
    title: "Why agentic quant is the next paradigm",
    date: "2026-05-12",
    excerpt:
      "Agentic loops produce better alpha than monolithic scripts. Here's why hash-locked specs are the bridge.",
    category: "Engineering",
    readMinutes: 10,
    published: true,
    href: "/learn/agentops-in-finance",
  },
  {
    slug: "multi-tenancy-financial-platforms",
    title: "Multi-tenancy for financial platforms: bridge over silo",
    date: "2026-04-28",
    excerpt:
      "Pool the stateless layers, silo the high-risk stateful ones, never compromise on tenant data isolation.",
    category: "Engineering",
    readMinutes: 9,
  },
  {
    slug: "finrl-x-deployment-consistent-rl",
    title: "Deployment-consistent RL: the FinRL-X pipeline",
    date: "2026-04-15",
    excerpt:
      "The offline-online drift problem in finance RL and the four-stage pipeline that solves it structurally.",
    category: "Research",
    readMinutes: 12,
    published: true,
    href: "/learn/finrl-x-portfolio-pipeline",
  },
  {
    slug: "hash-locked-specs-against-self-modifying-agents",
    title: "Hash-locked specs: the case against self-modifying agents",
    date: "2026-04-02",
    excerpt:
      "Why AQP rejects skill rewriting and what it does instead — immutable snapshots, deterministic replay, append-only audit ledgers.",
    category: "Engineering",
    readMinutes: 8,
    published: true,
    href: "/learn/hash-locked-specs",
  },
  {
    slug: "medallion-as-contract-not-convention",
    title: "Medallion as contract, not naming convention",
    date: "2026-03-20",
    excerpt:
      "Bronze / Silver / Gold deserves more respect than 'rename some Hive tables.' Here is what the contract should enforce.",
    category: "Engineering",
    readMinutes: 9,
    published: true,
    href: "/learn/medallion-data-platform",
  },
  {
    slug: "five-multi-agent-patterns",
    title: "Five multi-agent patterns in production",
    date: "2026-03-08",
    excerpt:
      "Sequential, parallel, debate, coordinator, ReAct. When each topology earns its keep, and the failure modes you should plan for.",
    category: "Research",
    readMinutes: 11,
    published: true,
    href: "/learn/multi-agent-patterns",
  },
];

const CATEGORY_COLORS: Record<Post["category"], string> = {
  Engineering: "#60a5fa",
  Research: "#a78bfa",
  Product: "#34d399",
};

export default function BlogPage() {
  return (
    <>
      <Hero
        eyebrow="Blog"
        eyebrowIcon={BookOpen}
        title="Engineering and research notes from the AQP team."
        titleHighlight="research notes"
        subtitle="Long-form, technical, no fluff. Most posts are companion essays to features in the platform — read them alongside the docs."
        primaryCta={{ label: "Read the latest", href: "#posts" }}
        secondaryCta={{ label: "Subscribe to RSS", href: "/rss.xml" }}
      />

      <section id="posts" className="px-6 py-16">
        <div className="mx-auto max-w-5xl">
          <SectionHeader
            eyebrow="All posts"
            title="Latest first"
            align="left"
          />
          <div className="mt-6 space-y-4">
            {POSTS.map((post, i) => (
              <MotionInView key={post.slug} delay={i * 0.05} from="up">
                <BlogCard post={post} />
              </MotionInView>
            ))}
          </div>

          <div
            className="mt-12 rounded-xl p-6 text-center"
            style={{
              background: "var(--glass-bg)",
              border: "1px solid var(--glass-border)",
              backdropFilter: "blur(var(--glass-blur))",
            }}
          >
            <Rss
              size={20}
              className="mx-auto"
              style={{ color: "var(--accent-primary)" }}
            />
            <h3
              className="mt-3 text-lg font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              Never miss a post
            </h3>
            <p
              className="mx-auto mt-2 max-w-xl text-sm leading-relaxed"
              style={{ color: "var(--text-secondary)" }}
            >
              Subscribe via RSS or follow{" "}
              <a
                href="https://twitter.com/aqpfund"
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-2"
                style={{ color: "var(--accent-primary)" }}
              >
                @aqpfund
              </a>{" "}
              on Twitter. We do not run an email newsletter.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}

function BlogCard({ post }: { post: Post }) {
  const formattedDate = new Date(post.date).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const accent = CATEGORY_COLORS[post.category];
  const inner = (
    <article
      className="group rounded-xl p-6 transition-all hover:-translate-y-0.5"
      style={{
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        backdropFilter: "blur(var(--glass-blur))",
      }}
    >
      <div className="flex items-center gap-3 text-xs">
        <span
          className="rounded-full px-2 py-0.5 font-bold uppercase tracking-wider"
          style={{
            background: `${accent}22`,
            color: accent,
          }}
        >
          {post.category}
        </span>
        <span
          className="inline-flex items-center gap-1"
          style={{ color: "var(--text-muted)" }}
        >
          <Calendar size={11} />
          {formattedDate}
        </span>
        <span
          className="inline-flex items-center gap-1"
          style={{ color: "var(--text-muted)" }}
        >
          <Clock size={11} />
          {post.readMinutes} min
        </span>
        {!post.published ? (
          <span
            className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
            style={{
              background: "rgba(245,158,11,0.15)",
              color: "var(--warn-fg)",
            }}
          >
            Draft
          </span>
        ) : null}
      </div>
      <h3
        className="mt-3 text-xl font-semibold transition-colors group-hover:text-white"
        style={{ color: "var(--text-primary)", lineHeight: 1.3 }}
      >
        {post.title}
      </h3>
      <p
        className="mt-2 text-sm leading-relaxed"
        style={{ color: "var(--text-secondary)" }}
      >
        {post.excerpt}
      </p>
      {post.published && post.href ? (
        <div
          className="mt-4 inline-flex items-center gap-1 text-sm font-semibold"
          style={{ color: "var(--accent-primary)" }}
        >
          Read the article
          <ArrowUpRight
            size={14}
            className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
          />
        </div>
      ) : null}
    </article>
  );

  if (post.published && post.href) {
    return <Link href={post.href}>{inner}</Link>;
  }
  return <div aria-disabled="true">{inner}</div>;
}
