import { Loader2, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";

interface StrategyEditorProps {
  /** Strategy id when editing an existing entry; undefined for create. */
  strategyId?: string;
  /** Optional initial YAML / kwargs (e.g. dropped from composer). */
  initialYaml?: string;
  /** Callback invoked with the new / updated strategy id. */
  onSaved?: (id: string) => void;
}

interface StrategyDetail {
  id: string;
  name: string;
  class?: string | null;
  module_path?: string | null;
  kwargs?: Record<string, unknown>;
  description?: string | null;
  tags?: string[];
}

const DEFAULT_YAML = `# Strategy YAML
class: FrameworkAlgorithm
module_path: aqp.strategies.framework
kwargs: {}
`;

/**
 * CodeMirror 6 port of the webui `StrategyEditor` Monaco component.
 * Lets researchers author / edit a strategy YAML, persist via
 * `POST/PUT /strategies`, and switch to JSON view for inspection.
 *
 * Hard-rule alignment: never touches Iceberg or LLM directly. Pure
 * REST wrap around `/strategies`.
 */
export function StrategyEditor({ strategyId, initialYaml, onSaved }: StrategyEditorProps) {
  const [yaml, setYaml] = useState(initialYaml ?? DEFAULT_YAML);
  const [name, setName] = useState("");
  const [tags, setTags] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [view, setView] = useState<"yaml" | "json">("yaml");
  const [json, setJson] = useState("{}");

  useEffect(() => {
    if (!strategyId) return;
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiFetch<StrategyDetail>(`/strategies/${encodeURIComponent(strategyId)}`);
        if (cancelled) return;
        setName(res.name ?? "");
        setTags((res.tags ?? []).join(", "));
        setDescription(res.description ?? "");
        const k = res.kwargs as { yaml?: string } | undefined;
        if (k?.yaml && typeof k.yaml === "string") {
          setYaml(k.yaml);
        } else {
          setJson(JSON.stringify(res, null, 2));
        }
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : (err as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [strategyId]);

  const submit = async () => {
    if (!name.trim()) {
      toast.warning("Strategy name is required");
      return;
    }
    const lines = yaml.split(/\r?\n/);
    let cls = "";
    let modulePath = "";
    for (const line of lines) {
      const mClass = /^class:\s*([\w.]+)\s*$/.exec(line);
      if (mClass) cls = mClass[1]!;
      const mModule = /^module_path:\s*([\w./]+)\s*$/.exec(line);
      if (mModule) modulePath = mModule[1]!;
    }
    if (!cls || !modulePath) {
      toast.error("YAML must declare top-level `class` and `module_path`");
      return;
    }
    const body = {
      name: name.trim(),
      class: cls,
      module_path: modulePath,
      kwargs: { yaml },
      description: description.trim() || undefined,
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    };
    setSubmitting(true);
    try {
      const url = strategyId
        ? `/strategies/${encodeURIComponent(strategyId)}`
        : "/strategies";
      const method: "POST" | "PUT" = strategyId ? "PUT" : "POST";
      const res = await apiFetch<StrategyDetail>(url, {
        method,
        body: JSON.stringify(body),
      });
      onSaved?.(res.id);
      toast.success(`Saved ${res.name}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async () => {
    if (!strategyId) return;
    if (!window.confirm("Delete this strategy? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await apiFetch<void>(`/strategies/${encodeURIComponent(strategyId)}`, { method: "DELETE" });
      toast.success("Strategy deleted");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Card className="flex h-full min-h-0 flex-col">
      <CardHeader>
        <CardTitle>{strategyId ? "Edit strategy" : "New strategy"}</CardTitle>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor="se-name">Name</Label>
            <Input id="se-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="se-tags">Tags</Label>
            <Input id="se-tags" value={tags} onChange={(e) => setTags(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="se-desc">Description</Label>
            <Input id="se-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>
        <Tabs value={view} onValueChange={(v) => setView(v as "yaml" | "json")}>
          <TabsList>
            <TabsTrigger value="yaml">YAML</TabsTrigger>
            <TabsTrigger value="json">JSON view</TabsTrigger>
          </TabsList>
          <TabsContent value="yaml" className="min-h-0 flex-1 overflow-hidden">
            <div className="h-[420px] overflow-hidden rounded-md">
              <CodeEditor language="json" value={yaml} onChange={setYaml} />
            </div>
          </TabsContent>
          <TabsContent value="json" className="min-h-0 flex-1 overflow-hidden">
            <div className="h-[420px] overflow-hidden rounded-md">
              <CodeEditor language="json" value={json} onChange={setJson} readOnly />
            </div>
          </TabsContent>
        </Tabs>
        <div className="flex gap-2">
          <Button onClick={submit} disabled={submitting}>
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {strategyId ? "Update" : "Create"}
          </Button>
          {strategyId ? (
            <Button variant="destructive" onClick={remove} disabled={deleting}>
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Delete
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
