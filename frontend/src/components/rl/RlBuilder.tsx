import { Loader2, Save } from "lucide-react";
import { useMemo, useState } from "react";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useRegistryComponent, useRegistryKind, type ComponentSummary } from "@/lib/api/registry";

interface Props {
  /** Registry kind (e.g. `rl_agent`, `rl_observation`, `rl_reward`, `rl_experiment`). */
  kind: string;
  /** Page title rendered in the shell. */
  title: string;
  /** Page subtitle. */
  subtitle: string;
  /** POST endpoint that consumes `{class, module_path, kwargs}`. */
  saveEndpoint: string;
}

/**
 * Generic builder for any registry kind. Pick a registered class, fill
 * its kwargs schema, and POST to the supplied endpoint.
 */
export function RlBuilder({ kind, title, subtitle, saveEndpoint }: Props) {
  const list = useRegistryKind(kind);
  const [alias, setAlias] = useState<string>("");
  const detail = useRegistryComponent(alias ? kind : null, alias || null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [savedId, setSavedId] = useState<string | null>(null);

  const setField = (k: string, v: unknown) => setValues((prev) => ({ ...prev, [k]: v }));

  const save = async () => {
    if (!alias || !detail.data) {
      toast.warning("Pick a class first");
      return;
    }
    setBusy(true);
    try {
      const moduleParts = detail.data.qualname.split(".");
      moduleParts.pop();
      const modulePath = detail.data.module ?? moduleParts.join(".");
      const kwargs: Record<string, unknown> = {};
      for (const param of detail.data.params) {
        const v = values[param.name];
        if (v === undefined || v === null || v === "") continue;
        kwargs[param.name] = v;
      }
      const res = await apiFetch<{ id?: string; status?: string }>(saveEndpoint, {
        method: "POST",
        body: JSON.stringify({
          class: detail.data.alias,
          module_path: modulePath,
          kwargs,
        }),
      });
      setSavedId(res.id ?? null);
      toast.success(`Saved (${res.status ?? "ok"})`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const aliasColumns: ColumnDef<ComponentSummary>[] = [
    { key: "alias", header: "Class", render: (r) => <span className="font-mono">{r.alias}</span> },
    {
      key: "category",
      header: "Category",
      width: 130,
      render: (r) => <Badge variant="secondary">{r.category ?? "—"}</Badge>,
    },
    {
      key: "params",
      header: "Params",
      width: 90,
      align: "right",
      render: (r) => <span className="font-mono">{r.params?.length ?? 0}</span>,
    },
  ];

  const filteredAliases = useMemo(() => list.data ?? [], [list.data]);

  return (
    <PageContainer title={title} subtitle={subtitle}>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[420px_1fr]">
        <Card className="h-[60vh]">
          <CardHeader>
            <CardTitle>Pick a class</CardTitle>
            <Badge variant="secondary">{filteredAliases.length}</Badge>
          </CardHeader>
          <CardContent className="h-full p-0">
            <DataTable<ComponentSummary>
              rows={filteredAliases}
              rowKey={(r) => r.alias}
              columns={aliasColumns}
              onRowClick={(r) => {
                setAlias(r.alias);
                setValues({});
              }}
              emptyState={list.isPending ? <span>Loading…</span> : <span>No classes for /{kind}.</span>}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{alias || "Pick a class"}</CardTitle>
            {alias ? <Badge variant="secondary">{kind}</Badge> : null}
          </CardHeader>
          <CardContent className="grid gap-3">
            {!alias ? (
              <p className="text-sm italic text-[var(--text-secondary)]">
                Select a class from the registry to populate its kwargs schema.
              </p>
            ) : detail.isPending ? (
              <p className="text-sm text-[var(--text-secondary)]">Loading schema…</p>
            ) : detail.data ? (
              <>
                {detail.data.doc ? (
                  <p className="text-xs text-[var(--text-secondary)]">{detail.data.doc}</p>
                ) : null}
                {detail.data.params.length === 0 ? (
                  <p className="text-xs italic text-[var(--text-secondary)]">No tunable kwargs.</p>
                ) : (
                  detail.data.params.map((p) => (
                    <div key={p.name} className="flex flex-col gap-1">
                      <Label htmlFor={`p-${p.name}`}>
                        <span className="font-mono">{p.name}</span>{" "}
                        <span className="text-[10px] text-[var(--text-secondary)]">{p.annotation}</span>
                        {p.required ? <span className="ml-1 text-[var(--neg-fg)]">*</span> : null}
                      </Label>
                      <Input
                        id={`p-${p.name}`}
                        value={String(values[p.name] ?? p.default ?? "")}
                        onChange={(e) => setField(p.name, e.target.value)}
                        className="font-mono"
                      />
                      {p.description ? (
                        <span className="text-[10px] text-[var(--text-secondary)]">{p.description}</span>
                      ) : null}
                    </div>
                  ))
                )}
                <Button onClick={save} disabled={busy} className="w-fit gap-2">
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {busy ? "Saving…" : "Save"}
                </Button>
                {savedId ? (
                  <p className="text-xs text-[var(--text-secondary)]">
                    Saved id: <code className="font-mono">{savedId}</code>
                  </p>
                ) : null}
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
