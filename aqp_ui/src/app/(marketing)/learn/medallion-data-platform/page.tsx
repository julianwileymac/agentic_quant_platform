import type { Metadata } from "next";

import { CodeBlock } from "@/components/marketing/CodeBlock";
import { LearnArticleLayout } from "@/components/marketing/LearnArticleLayout";
import { MedallionLayers } from "@/components/marketing/illustrations/MedallionLayers";

export const metadata: Metadata = {
  title: "The medallion data platform contract",
  description:
    "Bronze / Silver / Gold isn't just a naming convention. It is a contract about who writes what, with what business metadata, and how downstream consumers find it.",
};

export const dynamic = "force-static";
export const revalidate = 86400;

export default function MedallionDataPlatformPage() {
  return (
    <LearnArticleLayout
      eyebrow="Data · 9 min read"
      title="The medallion data platform contract"
      readMinutes={9}
      dateLine="Updated May 2026"
      toc={[
        { id: "naming-or-contract", label: "Naming convention or contract?" },
        { id: "the-three-layers", label: "The three layers" },
        { id: "bronze", label: "Bronze: raw, fast, append-only" },
        { id: "silver", label: "Silver: normalised, deduped, joined" },
        { id: "gold", label: "Gold: products, contracts, discoverable" },
        { id: "business-metadata", label: "Business metadata" },
        { id: "lineage", label: "Lineage as a query" },
        { id: "hudi-additive", label: "Hudi is additive, not a replacement" },
      ]}
      related={[
        {
          href: "/product/data-platform",
          title: "Data Platform product page",
          category: "Product",
        },
        {
          href: "/learn/agentops-in-finance",
          title: "AgentOps in finance",
          category: "Agentic",
        },
        {
          href: "/learn/hash-locked-specs",
          title: "Hash-locked specs",
          category: "Agentic",
        },
      ]}
      cta={{
        title: "Try the data plane",
        body: "Free tier includes 10 GB Iceberg and the active discovery service. Browse, promote, and query through the same dashboard your agents use.",
        label: "Start free",
        href: "/signup",
      }}
    >
      <p
        className="rounded-lg p-4 text-base"
        style={{
          background: "rgba(52,211,153,0.06)",
          border: "1px solid rgba(52,211,153,0.3)",
          color: "var(--text-primary)",
        }}
      >
        <strong>TL;DR.</strong> Most teams treat Bronze / Silver / Gold as a
        naming convention. AQP treats it as a contract: enforced at the
        wrapper layer, validated by namespace prefix, paired with business
        metadata, and dual-written into a bipartite lineage graph. The
        contract is what makes the data plane discoverable, audit-grade, and
        safe for agents to read.
      </p>

      <h2 id="naming-or-contract">Naming convention or contract?</h2>
      <p>
        The medallion architecture (Bronze / Silver / Gold) is famous as a
        naming convention from the lakehouse community. Most adoptions stop
        there: rename some Hive tables, write a wiki entry, move on. The
        team gets the cosmetic benefit and none of the structural one.
      </p>
      <p>
        AQP makes it a structural contract. Every Iceberg write goes through
        one wrapper —{" "}
        <code>iceberg_catalog.append_arrow</code> — which validates that the
        namespace prefix matches the declared{" "}
        <code>medallion_layer</code>. A Silver-layer write to an{" "}
        <code>aqp_bronze_*</code> namespace fails at runtime. A Bronze write
        to <code>aqp_gold_*</code> fails at runtime. The contract is
        unforgeable.
      </p>

      <div className="my-8">
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
      </div>

      <h2 id="the-three-layers">The three layers</h2>
      <p>
        Three layers, three contracts. Each one answers a different
        question:
      </p>
      <ul>
        <li>
          <strong>Bronze</strong> — "What did the source actually send us?"
        </li>
        <li>
          <strong>Silver</strong> — "What is the cleanest queryable form of
          this data?"
        </li>
        <li>
          <strong>Gold</strong> — "What are the products our consumers
          actually want?"
        </li>
      </ul>

      <h2 id="bronze">Bronze: raw, fast, append-only</h2>
      <p>
        Bronze captures the source data with as little transformation as
        possible. Schema = source schema. Encoding = source encoding (after
        Arrow conversion). Timestamps = source timestamps. The point is to
        preserve the ability to <em>reproduce</em> any downstream layer
        from Bronze; that means lossless ingestion.
      </p>
      <p>
        Bronze writes are append-only. If the source corrects a historic
        row, you append the correction with a corrected-at timestamp; you
        do not overwrite. Bronze is the immutable record of what the source
        told us, when, and what we did with it.
      </p>
      <p>
        Bronze namespaces in AQP are always prefixed with <code>aqp_bronze_</code>:{" "}
        <code>aqp_bronze_market_data</code>,{" "}
        <code>aqp_bronze_regulatory</code>,{" "}
        <code>aqp_bronze_research_papers</code>, and so on. The wrapper
        validates the prefix.
      </p>

      <h2 id="silver">Silver: normalised, deduped, joined</h2>
      <p>
        Silver is where the data becomes queryable in the way downstream
        consumers expect. Corporate-action adjustment for equities. Symbol
        normalisation (SAP vs SAP.SE vs SAP.DE all collapse to a canonical
        Symbol value). Deduplication. Cross-source joins (vendor-A's
        fundamentals joined to vendor-B's prices on a normalised key).
      </p>
      <p>
        Silver tables follow{" "}
        <code>aqp_silver_*</code> namespacing. The contract is: <em>any
        analyst can query this with confidence that it's been through the
        normalisation we agreed on</em>. The contract is enforceable
        because the wrapper validates the namespace prefix.
      </p>

      <h2 id="gold">Gold: products, contracts, discoverable</h2>
      <p>
        Gold is what consumers want. Alpha factor values per symbol per
        date. Analysis flow outputs. RL trajectory tables. Workflow audit
        rollups. These are the tables that show up in the operator UI's
        entity pickers, in agent tool surfaces, and in the analytics
        dashboard.
      </p>
      <p>
        Gold tables follow{" "}
        <code>aqp_gold_*</code> namespacing. They carry the strictest
        business metadata (data classification, retention policy, owner
        team, upstream lineage) because they are the most-consumed
        tables.
      </p>

      <CodeBlock
        filename="medallion_write.py"
        language="python"
        code={`from aqp.data.iceberg_catalog import append_arrow
from aqp.data.catalog import BusinessMetadata

# Bronze: lossless ingest from vendor.
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

# Silver: corporate-actions-adjusted, deduped.
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

# Gold: alpha factor product.
append_arrow(
    namespace="aqp_gold_factors",
    table="momentum_12_1",
    arrow_table=factor_values,
    medallion_layer="gold",
    business_metadata=BusinessMetadata(
        owner_team="alpha-research",
        upstream_datasets=["aqp_silver_market_data.us_equities_adjusted"],
        consumer_teams=["paper-trading", "research"],
        sla_freshness_minutes=60,
    ),
)`}
      />

      <h2 id="business-metadata">Business metadata as a first-class field</h2>
      <p>
        The <code>BusinessMetadata</code> field is not optional. It is what
        makes a Gold table discoverable to humans (who owns it? when does
        it refresh? what tier of SLA?) and to agents (who is the consumer
        community? is this PII? is it allowed in research contexts?).
      </p>
      <p>
        Concrete fields shipped: <code>owner_team</code>,{" "}
        <code>data_classification</code> (public / internal / confidential /
        regulated), <code>retention_days</code>,{" "}
        <code>upstream_datasets</code>, <code>consumer_teams</code>,{" "}
        <code>sla_freshness_minutes</code>,{" "}
        <code>data_contract_ref</code>. The business metadata lives next to
        the Iceberg table; it is queryable through DataMCP tools the same
        way agents query the actual rows.
      </p>

      <h2 id="lineage">Lineage as a queryable graph</h2>
      <p>
        Every <code>append_arrow</code> call writes a{" "}
        <code>LineageEvent</code> onto the <code>LineageBus</code>. When the{" "}
        <code>AQP_LINEAGE_GRAPH_ENABLED=true</code> flag is on, the{" "}
        <code>BipartiteGraphObserver</code> dual-writes into a bipartite
        graph: <code>lineage_dataset_vertex</code> rows for datasets,{" "}
        <code>lineage_transform_vertex</code> rows for the
        tasks/fetchers/sinks that produced them, and{" "}
        <code>lineage_edge</code> rows with typed relations (reads /
        writes / promoted / replaced).
      </p>
      <p>
        Iceberg-resident datasets record their snapshot id + manifest-list
        location via the{" "}
        <code>iceberg_snapshot_address</code> helper. That gives you{" "}
        content-addressed lineage — the lineage edge points at the exact
        snapshot that was read, not just "the latest at the time."
      </p>
      <p>
        Agents walk lineage via two DataMCP tools:{" "}
        <code>data.lineage.ancestry</code> ("what fed into this Gold
        table?") and <code>data.lineage.impact</code> ("what downstream
        products depend on this Silver table?"). The answers are
        deterministic given the snapshot ids.
      </p>

      <CodeBlock
        filename="lineage_walk.py"
        language="python"
        code={`from aqp.data.mcp.client import call_tool

# What datasets fed into this Gold factor?
ancestry = call_tool(
    "data.lineage.ancestry",
    {
        "dataset_namespace": "aqp_gold_factors",
        "table": "momentum_12_1",
    },
)

# What downstream products depend on this Silver dataset?
impact = call_tool(
    "data.lineage.impact",
    {
        "dataset_namespace": "aqp_silver_market_data",
        "table": "us_equities_adjusted",
    },
)`}
      />

      <h2 id="hudi-additive">Hudi is additive, not a replacement</h2>
      <p>
        Apache Hudi entered the AQP stack to handle one specific shape of
        data: upsert-heavy market-data partitions. Tick-by-tick corrections
        from a vendor land into a partition that needs row-level updates;
        Iceberg's append-only semantics make that wasteful.
      </p>
      <p>
        Hudi tables live under their own namespace prefix —{" "}
        <code>aqp_hudi_*</code> — and the{" "}
        <code>assert_not_iceberg</code> guard rejects Hudi writes against
        the medallion namespaces at runtime. The two stacks coexist; Hudi
        is additive, not a replacement.
      </p>
      <p>
        The contract is the same: declared layer, business metadata,
        lineage events emitted, DataMCP-readable. The wrapper differs; the
        contract does not.
      </p>

      <h2>What the medallion contract buys you</h2>
      <p>
        When the layers are a contract instead of a convention, you get:
      </p>
      <ul>
        <li>
          <strong>Discoverability.</strong> The active discovery service
          can list every dataset in the platform, classified by layer and
          lifecycle (ingested / pending / orphan / external_only).
        </li>
        <li>
          <strong>Safe agent reads.</strong> Agents read Gold (products)
          and (with permission) Silver (normalised). They typically never
          read Bronze. The naming makes the policy obvious.
        </li>
        <li>
          <strong>Audit-grade lineage.</strong> Content-addressed snapshot
          ids let you say "this trade was driven by this exact version of
          this exact factor."
        </li>
        <li>
          <strong>Reproducibility.</strong> Bronze is immutable; Silver is
          a deterministic transform of Bronze; Gold is a deterministic
          transform of Silver. You can reproduce any product end-to-end.
        </li>
      </ul>
      <p>
        That is the difference between a folder structure with cool names
        and a data platform.
      </p>
    </LearnArticleLayout>
  );
}
