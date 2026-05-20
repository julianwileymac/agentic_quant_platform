import {
  AlertTriangle,
  CheckCircle2,
  Code,
  FileCode,
  Plus,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { CodeEditor } from "@/components/common/CodeEditor";
import { EntityPicker } from "@/components/common/EntityPicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import {
  AirbyteBuilderApi,
  type BuilderField,
  type BuilderSection,
  type BuilderState,
  type CdkSchemaResponse,
  type FetcherCodegenResponse,
  type InferStreamsResponse,
  EMPTY_BUILDER_STATE,
  type ManifestDraftResult,
} from "@/lib/api/airbyteBuilder";
import { useApiQuery } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { DiscoveryApi } from "@/lib/api/discovery";

/**
 * Schema-driven Airbyte connector builder.
 *
 * Replaces the JSON editor in `AirbyteWorkspace.tsx` with a form
 * generator that consumes `/airbyte/builder/cdk-schema`. Credentials
 * use the EntityPicker (whitelist-only) so secrets never sit in
 * free-text inputs. The form produces either a low-code YAML
 * manifest or an AQP-native Fetcher stub via the codegen endpoint.
 */
export function ConnectorBuilderForm() {
  const [searchParams] = useSearchParams();
  const schemaQuery = useApiQuery<CdkSchemaResponse>({
    queryKey: ["airbyte", "builder", "schema"],
    path: "/airbyte/builder/cdk-schema",
    staleTime: 60_000 * 5,
  });

  const [state, setState] = useState<BuilderState>(EMPTY_BUILDER_STATE);
  const [yaml, setYaml] = useState<string>("");
  const [validation, setValidation] = useState<{ errors: string[]; warnings: string[] }>({
    errors: [],
    warnings: [],
  });
  const [streamPreview, setStreamPreview] = useState<InferStreamsResponse | null>(null);
  const [fetcherPreview, setFetcherPreview] = useState<FetcherCodegenResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [committing, setCommitting] = useState(false);

  // Phase 1 deep-link: ?from=discovery&entry_id=<uuid>
  useEffect(() => {
    const from = searchParams.get("from");
    const entryId = searchParams.get("entry_id");
    if (from !== "discovery" || !entryId) return;
    DiscoveryApi.describe(entryId)
      .then((entry) => {
        const slug = (entry.suggested_connector || entry.name)
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "_")
          .replace(/^_+|_+$/g, "");
        setState((prev) => ({
          ...prev,
          metadata: {
            connector_id: slug || prev.metadata.connector_id || "",
            display_name: entry.name,
            docs_url: entry.docs_url ?? "",
          },
          requester: {
            ...prev.requester,
            base_url: entry.source_uri ?? prev.requester.base_url ?? "",
          },
        }));
        toast.success(`Pre-filled from discovery entry ${entry.name}`);
      })
      .catch((err: Error) => toast.error(`Discovery entry load failed: ${err.message}`));
  }, [searchParams]);

  const sections = useMemo(() => schemaQuery.data?.sections ?? [], [schemaQuery.data]);

  const validate = async () => {
    try {
      const result = await AirbyteBuilderApi.manifestValidate(state);
      setValidation(result);
      if (result.errors.length === 0) {
        toast.success("Manifest is valid");
      }
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const draftYaml = async () => {
    try {
      const result: ManifestDraftResult = await AirbyteBuilderApi.manifestDraft(state);
      setYaml(result.yaml);
      setValidation(result.validation);
      toast.success("YAML manifest generated");
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const inferStreams = async () => {
    try {
      const result = await AirbyteBuilderApi.streamsInfer(state);
      setStreamPreview(result);
      if (result.ok) toast.success("Stream schema inferred");
      else toast.error(result.error ?? "Inference failed");
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const previewFetcher = async () => {
    try {
      const result = await AirbyteBuilderApi.codegenFetcher(state, { commit: false });
      setFetcherPreview(result);
      toast.success("AQP Fetcher stub generated");
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const commitFetcher = async () => {
    try {
      setCommitting(true);
      const result = await AirbyteBuilderApi.codegenFetcher(state, { commit: true });
      setFetcherPreview(result);
      toast.success(`AQP Fetcher written to ${result.path}`);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setCommitting(false);
    }
  };

  const persistState = async () => {
    if (!state.metadata.connector_id) {
      toast.error("connector_id is required to save");
      return;
    }
    try {
      setSaving(true);
      const result = await AirbyteBuilderApi.putState(
        state.metadata.connector_id,
        state,
      );
      setYaml(result.manifest_yaml);
      toast.success(`Saved builder state for ${result.connector_id}`);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const addStream = () =>
    setState((prev) => ({ ...prev, streams: [...prev.streams, { name: "", path: "" }] }));
  const removeStream = (idx: number) =>
    setState((prev) => ({
      ...prev,
      streams: prev.streams.filter((_, i) => i !== idx),
    }));

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="flex flex-col gap-3">
        {sections.map((section) => (
          <BuilderSectionCard
            key={section.key}
            section={section}
            state={state}
            onChange={setState}
            onAddStream={addStream}
            onRemoveStream={removeStream}
          />
        ))}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={validate} className="gap-1">
            <CheckCircle2 className="h-4 w-4" /> Validate
          </Button>
          <Button variant="outline" onClick={draftYaml} className="gap-1">
            <FileCode className="h-4 w-4" /> Generate YAML
          </Button>
          <Button variant="outline" onClick={inferStreams} className="gap-1">
            <Search className="h-4 w-4" /> Infer streams
          </Button>
          <Button variant="outline" onClick={previewFetcher} className="gap-1">
            <Code className="h-4 w-4" /> Preview AQP Fetcher
          </Button>
          <Button onClick={persistState} disabled={saving} className="gap-1">
            <Save className="h-4 w-4" /> {saving ? "Saving..." : "Save state"}
          </Button>
        </div>
      </div>
      <div className="flex flex-col gap-3">
        {(validation.errors.length > 0 || validation.warnings.length > 0) && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" /> Validation
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs">
              {validation.errors.length > 0 && (
                <div>
                  <p className="font-semibold text-[var(--neg-fg)]">Errors</p>
                  <ul className="ml-4 list-disc">
                    {validation.errors.map((err) => (
                      <li key={err}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
              {validation.warnings.length > 0 && (
                <div className="mt-2">
                  <p className="font-semibold text-[var(--warn-fg)]">Warnings</p>
                  <ul className="ml-4 list-disc">
                    {validation.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        )}
        {yaml && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileCode className="h-4 w-4" /> Low-code YAML manifest
              </CardTitle>
            </CardHeader>
            <CardContent className="h-72 p-0">
              <CodeEditor language="yaml" value={yaml} onChange={() => undefined} />
            </CardContent>
          </Card>
        )}
        {streamPreview && (
          <StreamPreview preview={streamPreview} />
        )}
        {fetcherPreview && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-4 w-4" /> AQP Fetcher stub
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-xs">
              <p className="break-all font-mono text-[10px] text-[var(--text-muted)]">
                {fetcherPreview.path}
                {fetcherPreview.exists ? (
                  <Badge variant="warn" className="ml-2">exists</Badge>
                ) : null}
              </p>
              <div className="h-72 overflow-hidden rounded-md">
                <CodeEditor
                  language="python"
                  value={fetcherPreview.rendered ?? ""}
                  onChange={() => undefined}
                />
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="default"
                  onClick={commitFetcher}
                  disabled={committing || fetcherPreview.written}
                  className="gap-1"
                >
                  <Save className="h-4 w-4" />{" "}
                  {fetcherPreview.written ? "Written" : "Commit to userland/"}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => setFetcherPreview(null)}
                  className="gap-1"
                >
                  Close
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

interface SectionCardProps {
  section: BuilderSection;
  state: BuilderState;
  onChange: (next: BuilderState | ((prev: BuilderState) => BuilderState)) => void;
  onAddStream: () => void;
  onRemoveStream: (idx: number) => void;
}

function BuilderSectionCard({
  section,
  state,
  onChange,
  onAddStream,
  onRemoveStream,
}: SectionCardProps) {
  const value = (state as unknown as Record<string, unknown>)[section.key] ?? {};
  if (section.repeatable) {
    const list = Array.isArray(value) ? (value as Array<Record<string, unknown>>) : [];
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>{section.title}</span>
            <Button variant="ghost" size="sm" onClick={onAddStream} className="gap-1 text-xs">
              <Plus className="h-3 w-3" /> Add
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          {list.map((item, idx) => (
            <div key={idx} className="grid gap-2 rounded-md border border-[var(--border-default)] p-2 md:grid-cols-2">
              {section.fields.map((field) => (
                <FieldInput
                  key={field.name}
                  field={field}
                  value={item[field.name] ?? ""}
                  onChange={(v) =>
                    onChange((prev) => {
                      const arr = [...(prev[section.key as keyof BuilderState] as unknown as Array<Record<string, unknown>>)];
                      arr[idx] = { ...(arr[idx] ?? {}), [field.name]: v };
                      return { ...prev, [section.key]: arr } as BuilderState;
                    })
                  }
                />
              ))}
              <div className="md:col-span-2 flex justify-end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onRemoveStream(idx)}
                  className="gap-1 text-xs text-[var(--neg-fg)]"
                >
                  <Trash2 className="h-3 w-3" /> Remove stream
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{section.title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {section.fields.map((field) => (
          <FieldInput
            key={field.name}
            field={field}
            value={(value as Record<string, unknown>)[field.name] ?? ""}
            onChange={(v) =>
              onChange((prev) => ({
                ...prev,
                [section.key]: {
                  ...((prev[section.key as keyof BuilderState] as unknown as Record<string, unknown>) ?? {}),
                  [field.name]: v,
                },
              }) as BuilderState)
            }
          />
        ))}
      </CardContent>
    </Card>
  );
}

interface FieldInputProps {
  field: BuilderField;
  value: unknown;
  onChange: (next: unknown) => void;
}

function FieldInput({ field, value, onChange }: FieldInputProps) {
  if (field.kind === "select") {
    return (
      <div className="flex flex-col gap-1">
        <Label>
          {field.label}
          {field.required ? <span className="ml-1 text-[var(--neg-fg)]">*</span> : null}
        </Label>
        <select
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(event.target.value)}
          className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm"
        >
          {(field.options ?? []).map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }
  if (field.kind === "credential_ref") {
    return (
      <div className="flex flex-col gap-1">
        <Label>
          {field.label}
          {field.required ? <span className="ml-1 text-[var(--neg-fg)]">*</span> : null}
        </Label>
        <EntityPicker
          kind="credentials"
          value={typeof value === "string" ? value : null}
          onChange={(next) => onChange(next ?? "")}
          placeholder="Pick a credential"
          allowCustom
          clearable
        />
        <p className="text-[10px] text-[var(--text-muted)]">
          Format: <code>service/account/field</code> (e.g. <code>iceberg/rest/token</code>).
        </p>
      </div>
    );
  }
  if (field.kind === "json") {
    return (
      <div className="flex flex-col gap-1">
        <Label>{field.label}</Label>
        <textarea
          value={typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2)}
          onChange={(event) => {
            try {
              const parsed = event.target.value ? JSON.parse(event.target.value) : {};
              onChange(parsed);
            } catch {
              onChange(event.target.value);
            }
          }}
          className={cn(
            "min-h-[80px] rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 font-mono text-xs",
          )}
        />
      </div>
    );
  }
  if (field.kind === "boolean") {
    return (
      <div className="flex flex-col gap-1">
        <Label>{field.label}</Label>
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(event) => onChange(event.target.checked)}
          />
          {field.description ? (
            <span className="text-[10px] text-[var(--text-muted)]">{field.description}</span>
          ) : null}
        </div>
      </div>
    );
  }
  if (field.kind === "number") {
    return (
      <div className="flex flex-col gap-1">
        <Label>{field.label}</Label>
        <Input
          type="number"
          value={String(value ?? field.default ?? "")}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <Label>
        {field.label}
        {field.required ? <span className="ml-1 text-[var(--neg-fg)]">*</span> : null}
      </Label>
      <Input
        type={field.kind === "secret" ? "password" : "text"}
        value={String(value ?? field.default ?? "")}
        placeholder={field.placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      {field.description ? (
        <p className="text-[10px] text-[var(--text-muted)]">{field.description}</p>
      ) : null}
    </div>
  );
}

function StreamPreview({ preview }: { preview: InferStreamsResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RefreshCw className="h-4 w-4" /> Inferred streams
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2 text-xs">
        {preview.streams.map((stream) => (
          <div
            key={stream.name}
            className="rounded-md border border-[var(--border-default)] p-2"
          >
            <p className="font-mono text-sm">
              {stream.name}
              {stream.error ? (
                <Badge variant="warn" className="ml-2">{stream.error}</Badge>
              ) : null}
            </p>
            {stream.fields && stream.fields.length > 0 ? (
              <ul className="ml-3 mt-1 list-disc text-[10px] text-[var(--text-muted)]">
                {stream.fields.map((field) => (
                  <li key={field.name}>
                    <code>{field.name}</code>
                    <span className="ml-1 italic">({field.type})</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
