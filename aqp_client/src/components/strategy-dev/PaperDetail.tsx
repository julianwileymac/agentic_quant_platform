import "katex/dist/katex.min.css";
import { Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { CodeEditor } from "@/components/common/CodeEditor";
import { useStrategyDev } from "@/components/strategy-dev/StrategyDevLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

interface PaperDetailProps {
  paperId: string;
}

interface PaperChunk {
  chunk_id: string;
  text: string;
  contains_mathematics?: boolean;
  equation_count?: number;
  section?: string | null;
}

interface PaperDetailResp {
  id: string;
  title: string;
  authors?: string[];
  author_institution?: string | null;
  publication_year?: number | null;
  asset_class?: string[];
  strategy_family?: string | null;
  contains_mathematics?: boolean;
  equation_count?: number;
  chunk_count?: number;
  parser_used?: string | null;
  meta?: Record<string, unknown>;
  abstract?: string | null;
  chunks?: PaperChunk[];
}

interface SynthesisResp {
  yaml: string;
  rationale?: string;
}

export function PaperDetail({ paperId }: PaperDetailProps) {
  const navigate = useNavigate();
  const { setSelection } = useStrategyDev();
  const [synthBusy, setSynthBusy] = useState(false);
  const [synthesis, setSynthesis] = useState<SynthesisResp | null>(null);

  const detail = useApiQuery<PaperDetailResp>({
    queryKey: ["rag", "papers", paperId],
    path: `/rag/papers/${encodeURIComponent(paperId)}`,
  });

  const synthesize = async () => {
    setSynthBusy(true);
    try {
      const res = await apiFetch<SynthesisResp>(
        `/rag/papers/${encodeURIComponent(paperId)}/synthesize`,
        { method: "POST", body: JSON.stringify({}) },
      );
      setSynthesis(res);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setSynthBusy(false);
    }
  };

  const openInComposer = () => {
    if (!synthesis?.yaml) return;
    setSelection({ composerYaml: synthesis.yaml });
    toast.success("Loaded into composer");
    navigate("/strategy-development/composer");
  };

  if (detail.isLoading) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-xs text-[var(--text-secondary)]">
          Loading paper…
        </CardContent>
      </Card>
    );
  }
  const paper = detail.data;
  if (!paper) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-xs text-[var(--text-secondary)]">
          Paper not found.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>
            <div className="flex flex-col gap-1">
              <span>{paper.title || paperId}</span>
              <div className="flex flex-wrap gap-1 text-[10px] font-normal text-[var(--text-secondary)]">
                {paper.authors?.length ? <span>{paper.authors.join(", ")}</span> : null}
                {paper.author_institution ? <span>· {paper.author_institution}</span> : null}
                {paper.publication_year ? <span>· {paper.publication_year}</span> : null}
              </div>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-1">
            {(paper.asset_class ?? []).map((ac) => (
              <Badge key={ac} variant="outline" className="text-[10px]">
                {ac}
              </Badge>
            ))}
            {paper.strategy_family ? (
              <Badge variant="secondary" className="text-[10px]">
                {paper.strategy_family}
              </Badge>
            ) : null}
            {paper.contains_mathematics ? (
              <Badge variant="default" className="text-[10px]">
                {paper.equation_count ?? 0} equations
              </Badge>
            ) : null}
            {paper.parser_used ? (
              <Badge variant="outline" className="text-[10px]">
                parser: {paper.parser_used}
              </Badge>
            ) : null}
          </div>
          {paper.abstract ? (
            <div className="prose prose-invert max-w-none rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 text-xs leading-relaxed">
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
              >
                {paper.abstract}
              </ReactMarkdown>
            </div>
          ) : null}
          {paper.chunks?.length ? (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
                Chunks ({paper.chunks.length})
              </h3>
              <div className="space-y-2">
                {paper.chunks.slice(0, 20).map((c) => (
                  <div
                    key={c.chunk_id}
                    className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2"
                  >
                    <div className="mb-1 flex items-center justify-between gap-2 text-[10px]">
                      <span className="font-mono text-[var(--text-secondary)]">
                        {c.section ?? c.chunk_id.slice(0, 8)}
                      </span>
                      {c.contains_mathematics ? (
                        <Badge variant="outline" className="text-[9px]">
                          {c.equation_count ?? 0} eq.
                        </Badge>
                      ) : null}
                    </div>
                    <div className="prose prose-invert max-w-none text-[11px]">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                      >
                        {c.text}
                      </ReactMarkdown>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4" />
              Synthesise strategy
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-[var(--text-secondary)]">
            Ask the LLM (via{" "}
            <code className="rounded bg-[var(--bg-app)] px-1">router_complete</code>) to draft an AQP
            strategy YAML from the paper's contents.
          </p>
          <Button onClick={synthesize} disabled={synthBusy}>
            {synthBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Synthesise
          </Button>
          {synthesis ? (
            <div className="space-y-3">
              {synthesis.rationale ? (
                <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2 text-[10px]">
                  {synthesis.rationale}
                </div>
              ) : null}
              <div className="h-72 overflow-hidden rounded-md">
                <CodeEditor language="json" value={synthesis.yaml} readOnly />
              </div>
              <Button onClick={openInComposer} variant="outline">
                <Sparkles className="h-3.5 w-3.5" />
                Open in composer
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
