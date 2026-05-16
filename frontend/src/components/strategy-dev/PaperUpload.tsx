import { Loader2, Upload as UploadIcon } from "lucide-react";
import { useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

interface PaperUploadProps {
  onUploaded?: (paperId: string) => void;
}

interface UploadResp {
  paper_id: string;
  task_id?: string;
}

const ASSET_CLASSES = ["equities", "options", "fixed_income", "cryptocurrencies", "futures", "fx"];
const STRATEGY_FAMILIES = [
  "mean_reversion",
  "momentum",
  "statistical_arbitrage",
  "volatility",
  "microstructure",
  "execution",
  "machine_learning",
  "sentiment",
];

/**
 * Drag-drop PDF uploader for the research-paper RAG. Posts multipart
 * to `POST /rag/papers/upload`. Metadata (asset class, strategy family,
 * institution) is captured client-side and stuffed into form fields the
 * backend stores on the `ResearchPaperRow`.
 */
export function PaperUpload({ onUploaded }: PaperUploadProps) {
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [authors, setAuthors] = useState("");
  const [institution, setInstitution] = useState("");
  const [year, setYear] = useState<string>("");
  const [assetClass, setAssetClass] = useState<string[]>([]);
  const [strategyFamily, setStrategyFamily] = useState<string>("");
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("title", title);
    if (authors) form.append("authors", authors);
    if (institution) form.append("author_institution", institution);
    if (year) form.append("publication_year", year);
    if (assetClass.length) form.append("asset_class", assetClass.join(","));
    if (strategyFamily) form.append("strategy_family", strategyFamily);

    setBusy(true);
    try {
      const res = await apiFetch<UploadResp>("/rag/papers/upload", {
        method: "POST",
        body: form,
      });
      toast.success(`Uploaded ${file.name} (paper ${res.paper_id.slice(0, 8)}…). Ingest queued.`);
      onUploaded?.(res.paper_id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void upload(file);
        }}
        className={`flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed p-6 text-center text-xs transition-colors ${
          dragging
            ? "border-[var(--info-fg)] bg-[var(--info-bg)]/40"
            : "border-[var(--border-default)] bg-[var(--bg-app)]"
        }`}
      >
        <UploadIcon className="h-6 w-6 text-[var(--text-secondary)]" />
        <p className="text-[var(--text-secondary)]">
          Drag a PDF here, or click to browse. Math-aware parsing preserves equations.
        </p>
        <Button
          variant="outline"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          size="sm"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UploadIcon className="h-3.5 w-3.5" />}
          Choose file
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
            e.target.value = "";
          }}
        />
      </div>

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="paper-title">Title</Label>
          <Input
            id="paper-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="(auto-detected if blank)"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="paper-authors">Authors</Label>
          <Input
            id="paper-authors"
            value={authors}
            onChange={(e) => setAuthors(e.target.value)}
            placeholder="Comma-separated"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="paper-institution">Institution</Label>
          <Input
            id="paper-institution"
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            placeholder="MIT, Stanford, …"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="paper-year">Year</Label>
          <Input
            id="paper-year"
            type="number"
            value={year}
            onChange={(e) => setYear(e.target.value)}
            placeholder="2024"
          />
        </div>
        <div className="space-y-1 md:col-span-2">
          <Label>Asset classes</Label>
          <div className="flex flex-wrap gap-1">
            {ASSET_CLASSES.map((ac) => (
              <button
                key={ac}
                type="button"
                onClick={() =>
                  setAssetClass((cur) =>
                    cur.includes(ac) ? cur.filter((c) => c !== ac) : [...cur, ac],
                  )
                }
              >
                <Badge variant={assetClass.includes(ac) ? "default" : "outline"} className="text-[10px]">
                  {ac}
                </Badge>
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1 md:col-span-2">
          <Label htmlFor="paper-family">Strategy family</Label>
          <select
            id="paper-family"
            className="h-9 w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
            value={strategyFamily}
            onChange={(e) => setStrategyFamily(e.target.value)}
          >
            <option value="">(unknown)</option>
            {STRATEGY_FAMILIES.map((sf) => (
              <option key={sf} value={sf}>
                {sf.replace("_", " ")}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
