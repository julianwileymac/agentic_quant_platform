import { ExternalLink, Plus, Quote, Search, Sparkles, Tag, Upload } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";
import {
  type LabRagHit,
  createLabNote,
  ragQuery,
} from "@/lib/api/lab";
import { useLabStore } from "@/features/data-lab/state/labStore";

interface PaperRagDrawerProps {
  /** Optional target binding for the "Cite to notes" button —
   *  defaults to the active draft graph id when present. */
  bindTarget?: { kind: "graph" | "run"; id: string } | null;
}

/**
 * Hybrid retrieval drawer (BM25 + pgvector + MMR) over the lab's
 * paper corpora. Each result has a Cite button that POSTs to
 * ``/lab/notes`` with ``target_kind='paper_chunk'`` and the chunk id
 * in ``citations[0]`` — completing the blueprint's "drag a paper
 * snippet into the active graph" flow.
 */
export function PaperRagDrawer({ bindTarget = null }: PaperRagDrawerProps) {
  const labId = useLabStore((s) => s.labId);
  const draftGraph = useLabStore((s) => s.draftGraph);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<LabRagHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [pendingTag, setPendingTag] = useState("");
  const [uploadUri, setUploadUri] = useState("");
  const [uploading, setUploading] = useState(false);
  const [useHyde, setUseHyde] = useState(false);

  const submit = async () => {
    if (!labId || !q.trim()) return;
    setLoading(true);
    try {
      const query = useHyde
        ? `Hypothetical answer to: ${q.trim()}. Cite the relevant passages.`
        : q.trim();
      const res = await ragQuery({
        lab_id: labId,
        query,
        k: 10,
        tags: tags.length ? tags : undefined,
      });
      setHits(res.hits);
    } catch (err) {
      toast.error(`Hybrid query failed: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const uploadPaper = async () => {
    if (!labId) {
      toast.error("Select a lab first.");
      return;
    }
    if (!uploadUri.trim()) {
      toast.warning("Paste an arxiv URL, DOI, or HTTPS link.");
      return;
    }
    setUploading(true);
    try {
      const reply = await apiFetch<{ task_id: string }>("/lab/rag/upload", {
        method: "POST",
        body: JSON.stringify({
          lab_id: labId,
          source_uri: uploadUri.trim(),
          tags: tags.length ? tags : undefined,
        }),
      });
      toast.success(
        `Paper ingest queued — task ${reply.task_id.slice(0, 8)}…`,
      );
      setUploadUri("");
    } catch (err) {
      toast.error(`Upload failed: ${(err as Error).message}`);
    } finally {
      setUploading(false);
    }
  };

  const addTag = () => {
    const t = pendingTag.trim();
    if (!t) return;
    if (tags.includes(t)) return;
    setTags([...tags, t]);
    setPendingTag("");
  };
  const removeTag = (t: string) => setTags(tags.filter((x) => x !== t));

  const cite = async (hit: LabRagHit) => {
    if (!labId) {
      toast.error("Select or create a lab before citing.");
      return;
    }
    const target = bindTarget ?? (draftGraph ? { kind: "graph" as const, id: draftGraph.id } : null);
    if (!target) {
      toast.warning("No active graph or run to cite into.");
      return;
    }
    try {
      await createLabNote({
        lab_id: labId,
        target_kind: target.kind,
        target_id: target.id,
        body_md: `> ${hit.text.slice(0, 280)}…\n\n— ${hit.paper_title ?? "untitled"}`,
        citations: [
          {
            chunk_id: hit.chunk_id,
            paper_title: hit.paper_title,
            source_uri: hit.source_uri,
            score: hit.score,
          },
        ],
      });
      toast.success(`Cited into ${target.kind} ${target.id.slice(0, 8)}…`);
    } catch (err) {
      toast.error(`Cite failed: ${(err as Error).message}`);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-amber-400" />
        <span className="text-sm font-medium">Research papers (hybrid)</span>
        <label className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground">
          <input
            type="checkbox"
            checked={useHyde}
            onChange={(e) => setUseHyde(e.target.checked)}
            className="h-3 w-3"
          />
          HyDE
        </label>
      </div>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Upload className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="arxiv / DOI / https URL — ingest"
            value={uploadUri}
            onChange={(e) => setUploadUri(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void uploadPaper();
            }}
            className="pl-8"
          />
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={uploadPaper}
          disabled={uploading || !uploadUri.trim()}
        >
          Ingest
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {tags.map((t) => (
          <Badge
            key={t}
            variant="secondary"
            className="cursor-pointer gap-1"
            onClick={() => removeTag(t)}
            title="Click to remove"
          >
            <Tag className="h-3 w-3" />
            {t} ×
          </Badge>
        ))}
        <div className="relative flex items-center">
          <Input
            placeholder="add tag"
            value={pendingTag}
            onChange={(e) => setPendingTag(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") addTag();
            }}
            className="h-6 w-24 px-1.5 text-[11px]"
          />
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-1 text-[11px]"
            onClick={addTag}
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={useHyde ? "Hypothetical-doc query…" : "Ask the corpus…"}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void submit();
            }}
            className="pl-8"
          />
        </div>
        <Button size="sm" onClick={submit} disabled={loading || !q.trim()}>
          Query
        </Button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
        {loading ? (
          <div className="text-xs text-muted-foreground">Retrieving…</div>
        ) : hits.length === 0 ? (
          <div className="text-xs text-muted-foreground">
            BM25 + pgvector dense retrieval + MMR rerank over the lab's
            paper corpora. Hits will appear here.
          </div>
        ) : (
          hits.map((hit) => (
            <Card key={hit.chunk_id} className="border-l-2">
              <CardContent className="space-y-1 py-2">
                <div className="flex items-center gap-2 text-xs">
                  <span className="truncate font-medium">
                    {hit.paper_title ?? "Untitled paper"}
                  </span>
                  <Badge variant="outline" className="ml-auto">
                    {hit.score.toFixed(3)}
                  </Badge>
                </div>
                <p className="line-clamp-4 text-[11px] text-muted-foreground">
                  {hit.text}
                </p>
                <div className="flex items-center gap-1 pt-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-[11px] gap-1"
                    onClick={() => cite(hit)}
                  >
                    <Quote className="h-3 w-3" />
                    Cite to notes
                  </Button>
                  {hit.source_uri ? (
                    <a
                      href={hit.source_uri}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-auto inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                    >
                      <ExternalLink className="h-3 w-3" />
                      Source
                    </a>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}

export default PaperRagDrawer;
