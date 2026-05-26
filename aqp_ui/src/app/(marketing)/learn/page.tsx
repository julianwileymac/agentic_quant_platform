import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  BookOpen,
  BrainCircuit,
  Database,
  GitBranch,
  Sparkles,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { CallToActionBlock } from "@/components/marketing/CallToActionBlock";
import { FeatureCard } from "@/components/marketing/FeatureCard";
import { Hero } from "@/components/marketing/Hero";
import { MotionInView } from "@/components/marketing/MotionInView";
import { SectionHeader } from "@/components/marketing/SectionHeader";

export const metadata: Metadata = {
  title: "Learn",
  description:
    "Long-form articles on AgentOps in finance, reinforcement learning for portfolio allocation, hash-locked specs, multi-agent patterns, and the medallion data plane.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

interface Article {
  slug: string;
  title: string;
  description: string;
  category: "Agentic" | "RL" | "Data" | "Platform";
  readMinutes: number;
  icon: LucideIcon;
  tone: "primary" | "secondary" | "tertiary" | "warn";
}

const ARTICLES: Article[] = [
  {
    slug: "agentops-in-finance",
    title: "AgentOps in finance",
    description:
      "Why agentic loops produce better alpha than monolithic scripts, and how hash-locked specs bridge the audit gap that financial systems demand.",
    category: "Agentic",
    readMinutes: 10,
    icon: BrainCircuit,
    tone: "primary",
  },
  {
    slug: "multi-agent-patterns",
    title: "Five multi-agent patterns in production",
    description:
      "Sequential, parallel, debate, coordinator, ReAct — when each topology earns its keep, and the failure modes you should plan for.",
    category: "Agentic",
    readMinutes: 11,
    icon: Workflow,
    tone: "primary",
  },
  {
    slug: "hash-locked-specs",
    title: "Hash-locked specs: the case against self-modifying agents",
    description:
      "Why AQP rejects skill rewriting and what it does instead: immutable snapshots, deterministic replay, append-only audit ledgers.",
    category: "Agentic",
    readMinutes: 8,
    icon: GitBranch,
    tone: "primary",
  },
  {
    slug: "reinforcement-learning-in-finance",
    title: "Reinforcement learning in finance",
    description:
      "From the Markowitz objective to deployment-consistent weight pipelines. Why offline-online drift is the boss-fight, and how FinRL-X closes it.",
    category: "RL",
    readMinutes: 12,
    icon: Sparkles,
    tone: "secondary",
  },
  {
    slug: "finrl-x-portfolio-pipeline",
    title: "FinRL-X four-stage portfolio pipeline",
    description:
      "Selector → Allocator → Timing → Risk overlay. The four pure functions that close the offline-to-live RL gap.",
    category: "RL",
    readMinutes: 9,
    icon: Activity,
    tone: "secondary",
  },
  {
    slug: "medallion-data-platform",
    title: "The medallion data platform contract",
    description:
      "Bronze / Silver / Gold isn't just a naming convention. It is a contract about who writes what, with what business metadata, and how downstream consumers find it.",
    category: "Data",
    readMinutes: 9,
    icon: Database,
    tone: "tertiary",
  },
];

const CATEGORY_COLORS: Record<Article["category"], string> = {
  Agentic: "#60a5fa",
  RL: "#a78bfa",
  Data: "#34d399",
  Platform: "#fbbf24",
};

export default function LearnHubPage() {
  const byCategory = ARTICLES.reduce(
    (acc, article) => {
      const bucket = acc[article.category] ?? [];
      bucket.push(article);
      acc[article.category] = bucket;
      return acc;
    },
    {} as Record<Article["category"], Article[]>,
  );

  return (
    <>
      <Hero
        eyebrow="Learn"
        eyebrowIcon={BookOpen}
        title="The quant ops literature, written for engineers."
        titleHighlight="written for engineers"
        subtitle="Long-form, technical, no fluff. Six deep dives on AgentOps, reinforcement learning, hash-locked specs, multi-agent patterns, the FinRL-X pipeline, and the medallion data plane — all paraphrased from the AQP architecture sources."
        primaryCta={{ label: "Start with AgentOps", href: "/learn/agentops-in-finance" }}
        secondaryCta={{ label: "Architecture overview", href: "/docs/architecture" }}
      />

      {/* Categories */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-7xl space-y-16">
          {(Object.keys(byCategory) as Article["category"][]).map((cat, ci) => (
            <MotionInView key={cat} delay={ci * 0.05}>
              <div>
                <div className="mb-6 flex items-center gap-3">
                  <span
                    className="inline-block h-2 w-12 rounded-full"
                    style={{ background: CATEGORY_COLORS[cat] }}
                  />
                  <h2
                    className="text-2xl font-bold tracking-tight"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {cat}
                  </h2>
                  <span
                    className="text-xs font-medium uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {byCategory[cat].length}{" "}
                    {byCategory[cat].length === 1 ? "article" : "articles"}
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                  {byCategory[cat].map((article) => (
                    <Link
                      key={article.slug}
                      href={`/learn/${article.slug}`}
                      className="group block h-full"
                    >
                      <ArticleCard article={article} />
                    </Link>
                  ))}
                </div>
              </div>
            </MotionInView>
          ))}
        </div>
      </section>

      {/* Roadmap teaser */}
      <section className="px-6 py-20" style={{ background: "rgba(255,255,255,0.02)" }}>
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Coming soon"
            title="More deep dives on the roadmap"
            subtitle="The Learn hub is growing. Subscribe to the changelog RSS or follow @aqpfund for new posts."
          />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {COMING_SOON.map((item) => (
              <div
                key={item.title}
                className="rounded-lg p-5"
                style={{
                  background: "var(--glass-bg)",
                  border: "1px dashed var(--glass-border-strong)",
                  backdropFilter: "blur(var(--glass-blur))",
                }}
              >
                <div
                  className="mb-1 text-xs font-bold uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  {item.category}
                </div>
                <div
                  className="text-base font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  {item.title}
                </div>
                <div
                  className="mt-2 text-sm leading-snug"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {item.body}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Get started"
        title="Try the concepts in the platform."
        subtitle="Sign up free and author your first hash-locked AgentSpec or RLExperimentSpec — the Learn articles map 1:1 to features you can use today."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "See architecture", href: "/docs/architecture" }}
      />
    </>
  );
}

function ArticleCard({ article }: { article: Article }) {
  return (
    <FeatureCard
      icon={article.icon}
      tone={article.tone}
      title={article.title}
      body={
        <>
          <div
            className="mb-2 inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider"
            style={{ color: CATEGORY_COLORS[article.category] }}
          >
            <BookOpen size={10} />
            {article.category} · {article.readMinutes} min read
          </div>
          <div>{article.description}</div>
        </>
      }
      href={`/learn/${article.slug}`}
    />
  );
}

const COMING_SOON = [
  {
    category: "Platform",
    title: "Multi-tenant data isolation playbook",
    body: "When to choose shared+RLS vs schema-per-tenant vs database-per-enterprise — with migration runbooks.",
  },
  {
    category: "Agentic",
    title: "Step-up MFA design patterns (RFC 9470)",
    body: "How AQP implements step-up across BFF handlers, kill-switches, and broker BYOK CRUD.",
  },
  {
    category: "RL",
    title: "PRUDEX-Compass in practice",
    body: "Reading the 17 measures across six axes — and what they mean for capital allocation decisions.",
  },
  {
    category: "Data",
    title: "Building MCP tools that agents can trust",
    body: "RFC 8707 audience, no-token-passthrough, OpenTelemetry spans, and the lessons we learned the hard way.",
  },
  {
    category: "Platform",
    title: "TerraformRuntime + OPA policy gates",
    body: "Why we made provisioning a managed runtime — and how the policy gate stops most outages.",
  },
  {
    category: "Agentic",
    title: "Building the Alpha Researcher agent",
    body: "From symbolic factor mining to the AST sandbox DSL — the engineering behind AQP's flagship research agent.",
  },
];
