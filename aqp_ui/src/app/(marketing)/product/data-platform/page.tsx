import type { Metadata } from "next";
import {
  Boxes,
  BookOpen,
  Database,
  Filter,
  GitBranch,
  Layers,
  Library,
  Network,
  RefreshCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Workflow,
  Zap,
} from "lucide-react";

import { CallToActionBlock } from "@/components/marketing/CallToActionBlock";
import { CodeBlock } from "@/components/marketing/CodeBlock";
import { FaqAccordion } from "@/components/marketing/FaqAccordion";
import { FeatureBreakdown } from "@/components/marketing/FeatureBreakdown";
import { FeatureCard } from "@/components/marketing/FeatureCard";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { Hero } from "@/components/marketing/Hero";
import { MedallionLayers } from "@/components/marketing/illustrations/MedallionLayers";
import { ProductNav } from "@/components/marketing/ProductNav";
import { SectionHeader } from "@/components/marketing/SectionHeader";
import { StatStrip } from "@/components/marketing/StatStrip";

export const metadata: Metadata = {
  title: "Data Platform",
  description:
    "Medallion Iceberg lakehouse, HierarchicalRAG, DataMCP boundary, bipartite lineage graph, pgvector + Redis hybrid. The data plane that powers your AQP agents.",
};

export const dynamic = "force-static";
export const revalidate = 3600;

const NAV_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "medallion", label: "Medallion lakehouse" },
  { id: "discovery", label: "Active discovery" },
  { id: "rag", label: "HierarchicalRAG" },
  { id: "lineage", label: "Lineage graph" },
  { id: "datamcp", label: "DataMCP" },
  { id: "faq", label: "FAQ" },
];

export default function DataPlatformPage() {
  return (
    <>
      <Hero
        eyebrow="Product · Data Platform"
        eyebrowIcon={Database}
        title="A medallion data plane your agents can browse."
        titleHighlight="medallion data plane"
        subtitle="Bronze for raw, Silver for normalised, Gold for products. Every Iceberg write goes through one wrapper with declared layer and business metadata. HierarchicalRAG over your alpha library, papers, and regulatory corpora. Bipartite lineage graph dual-written from every dataset event."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "Data plane docs", href: "/docs/data" }}
        illustration={
          <div
            className="overflow-hidden rounded-xl p-2"
            style={{
              background: "var(--glass-bg)",
              border: "1px solid var(--glass-border)",
              backdropFilter: "blur(var(--glass-blur))",
            }}
          >
            <MedallionLayers />
          </div>
        }
      />

      <ProductNav items={NAV_ITEMS} />

      <StatStrip
        stats={[
          { value: 3, label: "Medallion layers", tone: "tertiary" },
          { value: 56, label: "Cache categories", tone: "primary" },
          { value: 9, label: "Backtest engines fed", tone: "secondary" },
          { value: 4, label: "RAG corpora levels", tone: "primary" },
        ]}
      />

      {/* Overview */}
      <section id="overview" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Overview"
            title="Lakehouse, RAG, and lineage as one platform"
            subtitle="The data plane is the surface your agents see. AQP makes it auditable, typed, and discoverable — no agent gets to bypass it."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={Layers}
              tone="tertiary"
              title="Medallion Iceberg lakehouse"
              body="Bronze (raw), Silver (normalised), Gold (products). Namespace prefix validation enforces the layer convention at the wrapper level."
            />
            <FeatureCard
              icon={Search}
              tone="primary"
              title="Active discovery service"
              body="One catalog browser over Iceberg, Airbyte connections, Polaris, Hudi. Lifecycle classification: ingested / pending / orphan / external_only."
            />
            <FeatureCard
              icon={Library}
              tone="secondary"
              title="HierarchicalRAG"
              body="L0 alpha base, papers, regulatory corpora, code knowledge. Hybrid retrieval: Redis vector + BM25 + pgvector control plane."
            />
            <FeatureCard
              icon={Network}
              tone="warn"
              title="Bipartite lineage graph"
              body="Every LineageEvent dual-writes to lineage_dataset_vertex + lineage_transform_vertex + lineage_edge with content-addressed snapshot ids."
            />
            <FeatureCard
              icon={Filter}
              tone="tertiary"
              title="Cache prefetch + write-through"
              body="56 cache categories (datasets, namespaces, sinks, projects, credentials, ...) feed every entity dropdown via /api/cache/{kind}."
            />
            <FeatureCard
              icon={ShieldCheck}
              tone="primary"
              title="DataMCP boundary"
              body="Agents read through registered DataMCPTool instances — never raw ORM. The catalog is exposed via FastAPI + stdio MCP servers."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* Medallion lakehouse */}
      <section
        id="medallion"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="Medallion lakehouse"
          tone="tertiary"
          title="Bronze, Silver, Gold — enforced at the wrapper layer."
          body="Every Iceberg write goes through iceberg_catalog.append_arrow with a declared medallion_layer and BusinessMetadata. The wrapper validates that the namespace prefix matches the declared layer. Bronze namespaces are aqp_bronze_*, Silver aqp_silver_*, Gold aqp_gold_*. No accidental layer drift."
          bullets={[
            "Bronze = raw ingest (Airbyte, Hudi upserts, manual upload)",
            "Silver = normalised + deduped, often joined across sources",
            "Gold = products (alpha factors, analysis outputs, RL trajectories)",
            "Active metadata via register_dataset() or @dataset decorator",
          ]}
          cta={{
            label: "Medallion data plane deep-dive",
            href: "/learn/medallion-data-platform",
          }}
          visual={
            <CodeBlock
              filename="medallion_write.py"
              language="python"
              code={`from aqp.data.iceberg_catalog import append_arrow
from aqp.data.catalog import BusinessMetadata

# Bronze: raw daily bars from a vendor
append_arrow(
    namespace="aqp_bronze_market_data",
    table="us_equities_daily",
    arrow_table=raw_bars,
    medallion_layer="bronze",
    business_metadata=BusinessMetadata(
        owner_team="market-data",
        data_classification="public",
        retention_days=3650,
    ),
)

# Silver: normalised + corporate-actions-adjusted
append_arrow(
    namespace="aqp_silver_market_data",
    table="us_equities_adjusted",
    arrow_table=adjusted,
    medallion_layer="silver",
    business_metadata=BusinessMetadata(
        owner_team="market-data",
        upstream_datasets=["aqp_bronze_market_data.us_equities_daily"],
    ),
)

# Gold: alpha factor product
append_arrow(
    namespace="aqp_gold_factors",
    table="momentum_12_1",
    arrow_table=factor_values,
    medallion_layer="gold",
)`}
            />
          }
        />
      </section>

      {/* Active discovery */}
      <section id="discovery" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Active discovery"
            title="One browser. Every catalog. Every lifecycle state."
            subtitle="The DiscoveryService unifies DatasetCatalog + SourceLibraryEntry + Iceberg orphans + Airbyte connections — and classifies every entry as ingested / pending / orphan / external_only."
          />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {LIFECYCLE_STATES.map((s) => (
              <div
                key={s.label}
                className="rounded-lg p-5"
                style={{
                  background: "var(--glass-bg)",
                  border: `1px solid ${s.color}66`,
                  backdropFilter: "blur(var(--glass-blur))",
                }}
              >
                <div
                  className="text-xs font-bold uppercase tracking-wider"
                  style={{ color: s.color }}
                >
                  {s.label}
                </div>
                <div
                  className="mt-2 text-base font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  {s.title}
                </div>
                <div
                  className="mt-1 text-sm leading-snug"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {s.body}
                </div>
              </div>
            ))}
          </div>
          <div
            className="mt-6 rounded-lg p-4 text-sm leading-relaxed"
            style={{
              background: "rgba(22,119,255,0.06)",
              border: "1px solid rgba(22,119,255,0.25)",
              color: "var(--text-primary)",
            }}
          >
            <strong style={{ color: "var(--accent-primary)" }}>
              Promotion writes lineage.
            </strong>{" "}
            Promoting an uningested entry emits LineageEvent(transform_kind="discovery.promoted")
            and deep-links you into the Airbyte builder.
          </div>
        </div>
      </section>

      {/* HierarchicalRAG */}
      <section
        id="rag"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="HierarchicalRAG"
          tone="secondary"
          title="Hybrid retrieval across alpha, papers, and regulation."
          body="HierarchicalRAG is the single sanctioned read-and-write surface for agent retrieval. Adding a new corpus = a new indexer + a new entry in OrderCatalog. Hybrid query combines Redis vector + BM25 + pgvector for higher recall than any single backend."
          bullets={[
            "L0 alpha base, research papers, regulatory corpora, code knowledge",
            "Math-aware paper ingestion (Marker / Nougat / MathPix / PyPDF chain)",
            "pgvector control plane alongside Redis hybrid (3 allow-listed tables)",
            "Agents query via data.research_papers.* / data.vector.search MCP tools",
          ]}
          cta={{ label: "RAG architecture docs", href: "/docs/rag" }}
          reverse
          visual={
            <div className="space-y-4">
              {RAG_LAYERS.map((layer) => (
                <div
                  key={layer.name}
                  className="rounded-lg p-4"
                  style={{
                    background: "var(--glass-bg)",
                    border: "1px solid var(--glass-border)",
                    backdropFilter: "blur(var(--glass-blur))",
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Sparkles
                        size={14}
                        style={{ color: "var(--accent-secondary)" }}
                      />
                      <span
                        className="text-sm font-bold"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {layer.name}
                      </span>
                    </div>
                    <code
                      className="rounded px-2 py-0.5 text-xs"
                      style={{
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border-default)",
                        color: "var(--text-muted)",
                      }}
                    >
                      {layer.namespace}
                    </code>
                  </div>
                  <div
                    className="mt-2 text-xs leading-relaxed"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {layer.body}
                  </div>
                </div>
              ))}
            </div>
          }
        />
      </section>

      {/* Bipartite lineage graph */}
      <section id="lineage" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Lineage graph"
            title="Walk any dataset's ancestry or impact in one query."
            subtitle="Workstream A of the Data Layer enhancement adds a bipartite lineage graph alongside the flat data_lineage_events log. Every LineageEvent flowing through LineageBus is dual-written by BipartiteGraphObserver when AQP_LINEAGE_GRAPH_ENABLED=true."
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={GitBranch}
              tone="primary"
              title="lineage_dataset_vertex"
              body="One row per Iceberg / parquet / API-backed dataset, with snapshot id + manifest-list location for content addressing."
            />
            <FeatureCard
              icon={Workflow}
              tone="secondary"
              title="lineage_transform_vertex"
              body="One row per Celery task / fetcher / ingestion pipeline / sink that produced a downstream dataset."
            />
            <FeatureCard
              icon={Boxes}
              tone="tertiary"
              title="lineage_edge"
              body="Typed edges (reads / writes / promoted / replaced) between dataset and transform vertices."
            />
          </FeatureGrid>
          <div className="mt-10">
            <CodeBlock
              filename="lineage_walk.py"
              language="python"
              code={`from aqp.data.mcp.client import call_tool

# Walk ancestry: what datasets fed into this gold factor?
ancestry = call_tool(
    "data.lineage.ancestry",
    {"dataset_namespace": "aqp_gold_factors", "table": "momentum_12_1"},
)

# Walk impact: what downstream products depend on this silver dataset?
impact = call_tool(
    "data.lineage.impact",
    {"dataset_namespace": "aqp_silver_market_data", "table": "us_equities_adjusted"},
)

print(f"momentum_12_1 has {len(ancestry)} ancestors")
print(f"us_equities_adjusted feeds {len(impact)} downstream products")`}
            />
          </div>
        </div>
      </section>

      {/* DataMCP */}
      <section
        id="datamcp"
        className="px-6"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <FeatureBreakdown
          eyebrow="DataMCP boundary"
          tone="primary"
          title="The single read surface for every agent in the platform."
          body="No agent imports aqp.persistence.models or calls iceberg_catalog.append_arrow. Every read goes through a registered DataMCPTool. The same catalog is exposed externally via FastAPI /mcp/data and the aqp-data-mcp stdio binary — RFC 9728 + RFC 8707 conformant."
          bullets={[
            "Per-tool audience aud claim validated against the deployment canonical URI",
            "Source linter fails CI on direct ORM imports inside agent bodies",
            "Bridge auto-installs every DataMCPTool into AgentRuntime's TOOL_REGISTRY",
            "Reads emit OTEL spans + per-tool token-exchange audit rows",
          ]}
          cta={{ label: "DataMCP docs", href: "/product/agentops#datamcp" }}
          visual={
            <div
              className="rounded-xl p-6"
              style={{
                background: "var(--glass-bg-strong)",
                border: "1px solid var(--glass-border-strong)",
                backdropFilter: "blur(var(--glass-blur))",
              }}
            >
              <div
                className="text-xs font-bold uppercase tracking-wider"
                style={{ color: "var(--accent-primary)" }}
              >
                Shipped DataMCP tool families
              </div>
              <ul className="mt-4 grid grid-cols-2 gap-2 text-sm">
                {[
                  "data.bars.*",
                  "data.indicators.*",
                  "data.discovery.*",
                  "data.lineage.*",
                  "data.vector.*",
                  "data.research_papers.*",
                  "data.regulatory.*",
                  "data.entities.*",
                  "data.strategies.*",
                  "data.workflows.*",
                  "data.kubernetes.*",
                  "data.terraform.*",
                ].map((t) => (
                  <li
                    key={t}
                    className="flex items-center gap-2 font-mono"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ background: "var(--accent-primary)" }}
                    />
                    {t}
                  </li>
                ))}
              </ul>
              <div
                className="mt-4 border-t pt-4 text-xs leading-relaxed"
                style={{
                  borderColor: "var(--border-default)",
                  color: "var(--text-muted)",
                }}
              >
                Adding a new tool: subclass DataMCPTool, decorate with
                @register_data_mcp_tool. Bridge auto-installs it everywhere.
              </div>
            </div>
          }
        />
      </section>

      {/* Wrap-up */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Operator ergonomics"
            title="Browse, prefetch, write-through"
          />
          <FeatureGrid columns={3}>
            <FeatureCard
              icon={Filter}
              tone="primary"
              title="EntityPicker everywhere"
              body="Free-text inputs are reserved for descriptions and queries. Names of datasets, namespaces, sinks, projects, credentials all flow through whitelist-only pickers bound to the metadata cache."
            />
            <FeatureCard
              icon={RefreshCcw}
              tone="tertiary"
              title="Cache write-through"
              body="Mutation routes call cache_write_through after commit. The aqp:cache:* Redis namespace is owned by aqp/cache/ — no silent staleness."
            />
            <FeatureCard
              icon={Zap}
              tone="warn"
              title="Sandbox isolation"
              body="Dagster sandbox sessions live under aqp:sandbox:<session_id>:* — never touching the production cache. Auto-expiring via the SandboxRuntime janitor."
            />
          </FeatureGrid>
        </div>
      </section>

      {/* FAQ */}
      <section
        id="faq"
        className="px-6 py-20"
        style={{ background: "rgba(255,255,255,0.02)" }}
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="FAQ"
            title="Data platform questions"
          />
          <FaqAccordion items={FAQ_ITEMS} />
        </div>
      </section>

      <CallToActionBlock
        eyebrow="Ready to load data"
        title="Plug in a source. Browse. Promote. Cache."
        subtitle="Free tier ships with 10 GB Iceberg + 1 GB cache. The Airbyte builder + active discovery surface get you from raw vendor to bronze in minutes."
        primaryCta={{ label: "Start free", href: "/signup" }}
        secondaryCta={{ label: "Read the deep-dive", href: "/learn/medallion-data-platform" }}
      />
    </>
  );
}

const LIFECYCLE_STATES = [
  {
    label: "ingested",
    color: "#10b981",
    title: "Fully managed",
    body: "Live Iceberg dataset with active metadata, cache prefetch, and lineage edges.",
  },
  {
    label: "pending",
    color: "#f59e0b",
    title: "Promotion ready",
    body: "Catalog row exists with is_ingested=False; can be promoted via /discovery/entries/{id}/promote.",
  },
  {
    label: "orphan",
    color: "#f87171",
    title: "Drift detected",
    body: "Iceberg table exists with no matching DatasetCatalog row. Reconcile or delete.",
  },
  {
    label: "external_only",
    color: "#60a5fa",
    title: "Reference",
    body: "Airbyte source / external API surfaced for browsing but not ingested. Promote when ready.",
  },
];

const RAG_LAYERS = [
  {
    name: "L0 — Alpha base",
    namespace: "alpha_l0",
    body: "Per-tenant alpha factor library, normalised forms, formulas. Indexed daily by the alpha indexer.",
  },
  {
    name: "L1 — Research papers",
    namespace: "research_papers",
    body: "Math-aware extraction via Marker / Nougat / MathPix / PyPDF chain. Hybrid retrieval covers prose + equations.",
  },
  {
    name: "L2 — Regulatory corpora",
    namespace: "regulatory_*",
    body: "CFPB / FDA / USPTO / SEC EDGAR adapters. Auto-refresh via Celery beat. RAG-queryable through data.regulatory.*",
  },
  {
    name: "L3 — Code knowledge",
    namespace: "code_*",
    body: "AQP source tree + curated externals (extractions/, inspiration/, aqp_snippets/). Queryable via codebase.search MCP tool.",
  },
];

const FAQ_ITEMS = [
  {
    question: "Can I bring my own Iceberg catalog?",
    answer:
      "Yes. The wrapper supports SQL, REST, Hive, and Glue catalogs. Configure via Settings; the wrapper still enforces the medallion namespace prefix validation regardless of backend.",
  },
  {
    question: "What's the difference between the cache and Iceberg?",
    answer:
      "Iceberg is the source of truth for bars, factors, trajectories, and analysis outputs. The Redis metadata cache (aqp:cache:*) is for fast entity-dropdown reads only — dataset names, namespace names, sink kinds, projects, credentials. Mutations call cache_write_through after commit so the cache is never stale.",
  },
  {
    question: "How do I add a new RAG corpus?",
    answer:
      "Two steps: (1) implement an indexer under aqp/rag/indexers/ that knows how to chunk and embed your source format; (2) add a new entry in aqp/rag/orders.py OrderCatalog with the corpus namespace and retrieval order. HierarchicalRAG picks it up automatically.",
  },
  {
    question: "Is Apache Hudi a replacement for Iceberg?",
    answer:
      "No — additive. Iceberg remains the single canonical lakehouse write path. Hudi tables live under their own aqp_hudi_* namespace prefix and serve upsert-heavy market-data partitions. The assert_not_iceberg guard rejects Hudi writes against the medallion namespaces at runtime.",
  },
  {
    question: "Do agents see only my tenant's data?",
    answer:
      "Yes. The DataMCP layer + Postgres RLS + Iceberg path-prefix isolation all enforce the active RequestContext's org_id / workspace_id. Cross-tenant queries fail at the DB level before they ever reach the agent.",
  },
];
