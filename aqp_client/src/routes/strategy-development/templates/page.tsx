import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useApiMutation, useApiQuery } from "@/lib/api/hooks";

interface TemplateSummary {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  uri: string | null;
  tags: string[];
  asset_classes: string[];
  indicators: string[];
  framework: string;
  class_name?: string | null;
  source_path?: string | null;
}

interface TemplateDetail extends TemplateSummary {
  raw_source: string | null;
}

interface CloneResponse {
  id: string;
  slug: string;
  translated: boolean;
  source_id: string | null;
}

const ASSET_CLASSES = [
  "equities",
  "options",
  "futures",
  "crypto",
  "forex",
  "indices",
];

const TAGS = [
  "machine_learning",
  "multi_leg",
  "momentum",
  "mean_reversion",
  "microstructure",
  "alpha",
];

/**
 * ``/strategy-development/templates`` — Phase 7 LEAN template browser.
 *
 * Renders the catalog ingested by ``scripts/ingest_lean_templates.py``
 * as a filterable grid. Selecting a template loads the source code
 * into the right pane; "Clone to my workspace" forks it into the
 * user's :class:`Resource` row, optionally with the AST translator
 * applied so the strategy is immediately runnable on AQP's engines.
 */
export function StrategyTemplatesPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [assetClass, setAssetClass] = useState<string | null>(null);
  const [tag, setTag] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [translate, setTranslate] = useState(true);

  const list = useApiQuery<TemplateSummary[]>({
    queryKey: ["strategy-templates", search, assetClass, tag],
    path: "/strategies/templates",
    query: {
      search,
      asset_class: assetClass ?? undefined,
      tag: tag ?? undefined,
      limit: 200,
    },
  });

  const detail = useApiQuery<TemplateDetail>({
    queryKey: ["strategy-template", selectedId],
    path: selectedId ? `/strategies/templates/${selectedId}` : "/strategies/templates",
    enabled: Boolean(selectedId),
  });

  const clone = useApiMutation<CloneResponse, { template_id: string; translate: boolean }>({
    path: "/strategies/templates/clone",
    method: "POST",
    mutationKey: ["strategy-templates", "clone"],
  });

  const grouped = useMemo(() => {
    const buckets = new Map<string, TemplateSummary[]>();
    for (const item of list.data ?? []) {
      const primary = item.asset_classes?.[0] ?? "other";
      const arr = buckets.get(primary) ?? [];
      arr.push(item);
      buckets.set(primary, arr);
    }
    return Array.from(buckets.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [list.data]);

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search templates (name + description)..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-md"
        />
        <FilterBar
          label="Asset"
          options={ASSET_CLASSES}
          value={assetClass}
          onChange={setAssetClass}
        />
        <FilterBar label="Tag" options={TAGS} value={tag} onChange={setTag} />
        <span className="ml-auto text-xs text-[var(--text-muted)]">
          {list.data?.length ?? 0} templates
        </span>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[420px_1fr]">
        {/* Catalog list */}
        <div className="min-h-0 overflow-auto rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] p-2">
          {grouped.map(([bucket, items]) => (
            <div key={bucket} className="mb-3">
              <div className="mb-1 text-[10px] font-mono uppercase text-[var(--text-muted)]">
                {bucket}
              </div>
              <div className="space-y-1">
                {items.map((tpl) => (
                  <button
                    key={tpl.id}
                    onClick={() => setSelectedId(tpl.id)}
                    className={`flex w-full items-start gap-2 rounded border px-2 py-1.5 text-left text-sm hover:bg-[var(--bg-app)] ${
                      selectedId === tpl.id
                        ? "border-[var(--info-fg)] bg-[var(--bg-app)]"
                        : "border-transparent"
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="truncate font-medium">{tpl.name}</div>
                      <div className="truncate font-mono text-[10px] text-[var(--text-muted)]">
                        {tpl.uri}
                      </div>
                    </div>
                    <div className="flex flex-shrink-0 flex-wrap gap-1">
                      {tpl.tags.slice(0, 2).map((t) => (
                        <Badge key={t} variant="outline" className="text-[9px]">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
          {!list.isLoading && (list.data?.length ?? 0) === 0 ? (
            <div className="p-4 text-xs text-[var(--text-muted)]">
              No templates ingested yet. Run{" "}
              <code>python -m scripts.ingest_lean_templates --clone</code>
              {" "}on the backend to populate the catalog.
            </div>
          ) : null}
        </div>

        {/* Preview pane */}
        <Card className="flex min-h-0 flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {detail.data?.name ?? "Select a template"}
            </CardTitle>
            <CardDescription>{detail.data?.description ?? null}</CardDescription>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
            {detail.data ? (
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {detail.data.asset_classes.map((c) => (
                  <Badge key={c} variant="outline">
                    {c}
                  </Badge>
                ))}
                {detail.data.indicators.map((c) => (
                  <Badge key={c} variant="outline">
                    {c}
                  </Badge>
                ))}
                {detail.data.tags.map((c) => (
                  <Badge key={c}>{c}</Badge>
                ))}
              </div>
            ) : null}
            <pre className="min-h-0 flex-1 overflow-auto rounded border border-[var(--border)] bg-[var(--bg-app)] p-2 font-mono text-xs">
              {detail.data?.raw_source ?? "// Select a template to preview"}
            </pre>
            {detail.data ? (
              <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border)] pt-3">
                <label className="flex items-center gap-2 text-xs">
                  <Switch
                    checked={translate}
                    onCheckedChange={(checked: boolean) => setTranslate(checked)}
                  />
                  Translate LEAN -&gt; FrameworkAlgorithm on clone
                </label>
                <Button
                  size="sm"
                  disabled={clone.isPending}
                  onClick={() => {
                    if (!detail.data) return;
                    clone.mutateAsync({
                      template_id: detail.data.id,
                      translate,
                    }).then((res) => {
                      navigate(`/resources/${res.id}`);
                    });
                  }}
                >
                  {clone.isPending ? "Cloning..." : "Clone to my workspace"}
                </Button>
                {clone.isSuccess ? (
                  <span className="text-xs text-[var(--pos-fg)]">
                    Cloned as {clone.data?.slug}
                  </span>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

interface FilterBarProps {
  label: string;
  options: string[];
  value: string | null;
  onChange: (v: string | null) => void;
}

function FilterBar({ label, options, value, onChange }: FilterBarProps) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-[10px] font-mono uppercase text-[var(--text-muted)]">
        {label}
      </span>
      <Button
        variant={value === null ? "default" : "outline"}
        size="sm"
        onClick={() => onChange(null)}
      >
        all
      </Button>
      {options.map((opt) => (
        <Button
          key={opt}
          variant={value === opt ? "default" : "outline"}
          size="sm"
          onClick={() => onChange(opt)}
        >
          {opt}
        </Button>
      ))}
    </div>
  );
}
