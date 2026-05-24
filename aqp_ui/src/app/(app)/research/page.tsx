import { Card } from "antd";

export const dynamic = "force-dynamic";

export default function ResearchPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Research
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Hierarchical RAG over first-, second-, and third-order corpora.
        </p>
      </header>
      <Card>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Paper ingestion through Marker / Nougat / MathPix / PyPDF chain.
          Hybrid retrieval (BM25 + vector) backs every research-paper RAG
          query the AlphaResearcher agent makes.
        </p>
      </Card>
    </div>
  );
}
