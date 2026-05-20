import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import {
  type FlowResult,
  type FlowSchema,
  previewAnalysisFlow,
} from "@/lib/analysis/api";

import type { DatasetSelection } from "./DatasetPicker";

interface Props {
  flow: FlowSchema;
  dataset: DatasetSelection;
  onResult: (result: FlowResult) => void;
}

interface ParamField {
  name: string;
  type: string;
  default?: unknown;
  description?: string;
  enum?: unknown[];
  required: boolean;
  itemsType?: string;
  min?: number;
  max?: number;
}

/**
 * Walk a Pydantic JSON-schema body into a flat list of UI fields. We
 * intentionally don't try to handle every JSON-schema feature — the
 * fields the backend emits for ``FlowParams`` subclasses cover scalar
 * primitives, lists, enums, and Optional-of-primitive.
 */
function fieldsFromSchema(params_schema: Record<string, unknown>): ParamField[] {
  const properties =
    (params_schema.properties as Record<string, Record<string, unknown>> | undefined) ?? {};
  const required = new Set((params_schema.required as string[] | undefined) ?? []);
  const out: ParamField[] = [];
  for (const [name, raw] of Object.entries(properties)) {
    const field: ParamField = {
      name,
      type: typeof raw.type === "string" ? raw.type : "string",
      required: required.has(name),
    };
    if (raw.default !== undefined) field.default = raw.default;
    if (typeof raw.description === "string") field.description = raw.description;
    if (Array.isArray(raw.enum)) field.enum = raw.enum;
    if (raw.items && typeof raw.items === "object") {
      const items = raw.items as Record<string, unknown>;
      if (typeof items.type === "string") field.itemsType = items.type;
    }
    if (typeof raw.minimum === "number") field.min = raw.minimum;
    if (typeof raw.maximum === "number") field.max = raw.maximum;
    if (Array.isArray(raw.anyOf)) {
      const primary = raw.anyOf.find(
        (v): v is Record<string, unknown> =>
          typeof v === "object" && v !== null && (v as Record<string, unknown>).type !== "null",
      );
      if (primary && typeof primary.type === "string") field.type = primary.type;
    }
    out.push(field);
  }
  return out;
}

/** Coerce raw form input back into the type the backend expects. */
function coerceValue(field: ParamField, raw: string): unknown {
  const trimmed = raw.trim();
  if (trimmed === "" && !field.required && field.default !== undefined) {
    return undefined;
  }
  if (field.type === "integer") return Number.parseInt(trimmed, 10);
  if (field.type === "number") return Number.parseFloat(trimmed);
  if (field.type === "boolean") return trimmed.toLowerCase() === "true";
  if (field.type === "array") {
    if (trimmed === "") return [];
    const items = trimmed.split(",").map((p) => p.trim()).filter(Boolean);
    if (field.itemsType === "integer") return items.map((p) => Number.parseInt(p, 10));
    if (field.itemsType === "number") return items.map((p) => Number.parseFloat(p));
    return items;
  }
  return trimmed;
}

function defaultDisplay(field: ParamField): string {
  if (field.default === undefined || field.default === null) return "";
  if (Array.isArray(field.default)) return field.default.join(", ");
  return String(field.default);
}

export function FlowForm({ flow, dataset, onResult }: Props) {
  const fields = useMemo(() => fieldsFromSchema(flow.params_schema), [flow]);
  const [values, setValues] = useState<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const f of fields) out[f.name] = defaultDisplay(f);
    return out;
  });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const params: Record<string, unknown> = {};
    for (const field of fields) {
      const raw = values[field.name] ?? "";
      const coerced = coerceValue(field, raw);
      if (coerced === undefined) continue;
      params[field.name] = coerced;
    }
    setBusy(true);
    try {
      const body = {
        params,
        ...(flow.requires_dataset
          ? {
              iceberg_identifier: dataset.identifier,
              limit: dataset.limit,
            }
          : {}),
      };
      const result = await previewAnalysisFlow(flow.name, body);
      onResult(result);
      if (result.error) toast.error(`Flow returned an error: ${result.error}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`Preview failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {fields.map((field) => (
          <div key={field.name} className="flex flex-col gap-1">
            <Label htmlFor={`flow-${flow.name}-${field.name}`}>
              {field.name}
              {field.required ? <span className="text-[var(--neg-fg)]"> *</span> : null}
            </Label>
            {field.enum ? (
              <select
                id={`flow-${flow.name}-${field.name}`}
                className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-2 text-sm"
                value={values[field.name] ?? ""}
                onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
              >
                {field.enum.map((opt) => (
                  <option key={String(opt)} value={String(opt)}>
                    {String(opt)}
                  </option>
                ))}
              </select>
            ) : field.type === "boolean" ? (
              <select
                id={`flow-${flow.name}-${field.name}`}
                className="h-9 rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-2 text-sm"
                value={values[field.name] ?? "false"}
                onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
              >
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            ) : (
              <Input
                id={`flow-${flow.name}-${field.name}`}
                value={values[field.name] ?? ""}
                placeholder={field.description ?? field.type}
                onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
              />
            )}
            {field.description ? (
              <p className="text-[10px] text-[var(--text-secondary)]">
                {field.description}
              </p>
            ) : null}
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--text-secondary)]">
          {flow.requires_dataset
            ? `Dataset: ${dataset.identifier || "(pick one above)"}`
            : "(this flow does not require a dataset)"}
        </p>
        <Button
          size="sm"
          onClick={submit}
          disabled={busy || (flow.requires_dataset && !dataset.identifier)}
        >
          {busy ? "Running..." : "Preview"}
        </Button>
      </div>
    </div>
  );
}
