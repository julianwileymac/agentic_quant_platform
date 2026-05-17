import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRegistryComponent, useRegistryKind } from "@/lib/api/registry";

export interface BackboneSelection {
  alias: string;
  module_path: string;
  features_dim: number;
  sequence_length: number;
  input_features: number;
  backbone_kwargs: Record<string, unknown>;
}

interface Props {
  value: BackboneSelection | null;
  onChange: (value: BackboneSelection | null) => void;
  /** Optional default features_dim. The picker pre-fills with 128. */
  defaultFeaturesDim?: number;
}

/**
 * Phase B (agentic-RL UI studios): schema-driven picker for the
 * Phase 3 `rl_policy_backbone` registrations (Transformer / RNN /
 * Autoencoder / PatchTST). Emits the canonical `policy_kwargs`
 * payload that the SB3 `BackboneFeaturesExtractor` accepts.
 *
 * Reads `/registry/rl_policy_backbone` for the alias list and
 * `/registry/rl_policy_backbone/{alias}` for the params schema —
 * same pattern as `RlBuilder` but rendered inline so the picker
 * fits inside a meta panel or a wizard step.
 */
export function BackbonePicker({
  value,
  onChange,
  defaultFeaturesDim = 128,
}: Props) {
  const list = useRegistryKind("rl_policy_backbone");
  const [alias, setAlias] = useState<string | null>(value?.alias ?? null);
  const detail = useRegistryComponent(alias ? "rl_policy_backbone" : null, alias ?? null);
  const [seqLen, setSeqLen] = useState<number>(value?.sequence_length ?? 30);
  const [inputFeatures, setInputFeatures] = useState<number>(value?.input_features ?? 0);
  const [featuresDim, setFeaturesDim] = useState<number>(value?.features_dim ?? defaultFeaturesDim);
  const [kwargs, setKwargs] = useState<Record<string, unknown>>(value?.backbone_kwargs ?? {});

  useEffect(() => {
    if (!alias || !detail.data) {
      onChange(null);
      return;
    }
    const moduleParts = detail.data.qualname.split(".");
    moduleParts.pop();
    const modulePath = detail.data.module ?? moduleParts.join(".");
    onChange({
      alias,
      module_path: modulePath,
      features_dim: featuresDim,
      sequence_length: seqLen,
      input_features: inputFeatures,
      backbone_kwargs: kwargs,
    });
  }, [alias, detail.data, seqLen, inputFeatures, featuresDim, kwargs, onChange]);

  const setField = (k: string, v: unknown) => setKwargs((prev) => ({ ...prev, [k]: v }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          Policy backbone
          {alias ? <Badge variant="secondary">{alias}</Badge> : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <p className="text-xs text-[var(--text-secondary)]">
          Picks one of the four Phase 3 backbones — Transformer / Recurrent /
          Autoencoder / PatchTST. Compiled into <code>policy_kwargs</code> for
          SB3 via the canonical{" "}
          <code>BackboneFeaturesExtractor</code>.
        </p>
        <div className="grid gap-1">
          <Label htmlFor="backbone-alias">Backbone</Label>
          <select
            id="backbone-alias"
            value={alias ?? ""}
            onChange={(e) => {
              const v = e.target.value || null;
              setAlias(v);
              setKwargs({});
            }}
            className="h-9 rounded-md border border-[var(--border-default)] bg-transparent px-2 font-mono text-sm"
          >
            <option value="">— Pick a backbone —</option>
            {(list.data ?? []).map((c) => (
              <option key={c.alias} value={c.alias}>
                {c.alias} ({c.category ?? "—"})
              </option>
            ))}
          </select>
        </div>
        {alias ? (
          <>
            <div className="grid grid-cols-3 gap-2">
              <NumberField
                id="bb-seq-len"
                label="sequence_length"
                value={seqLen}
                onChange={setSeqLen}
              />
              <NumberField
                id="bb-input-feat"
                label="input_features"
                value={inputFeatures}
                onChange={setInputFeatures}
                hint="0 = infer from obs"
              />
              <NumberField
                id="bb-features-dim"
                label="features_dim"
                value={featuresDim}
                onChange={setFeaturesDim}
              />
            </div>
            {detail.data?.doc ? (
              <details>
                <summary className="cursor-pointer text-xs text-[var(--text-secondary)]">
                  docs
                </summary>
                <p className="mt-1 whitespace-pre-wrap text-xs">{detail.data.doc}</p>
              </details>
            ) : null}
            {detail.data ? (
              <div className="grid gap-2">
                {detail.data.params
                  .filter(
                    (p) =>
                      ![
                        "input_features",
                        "sequence_length",
                        "output_dim",
                        "name",
                      ].includes(p.name),
                  )
                  .map((p) => (
                    <div key={p.name} className="flex flex-col gap-1">
                      <Label htmlFor={`bbk-${p.name}`}>
                        <span className="font-mono">{p.name}</span>{" "}
                        <span className="text-[10px] text-[var(--text-secondary)]">
                          {p.annotation}
                        </span>
                      </Label>
                      <Input
                        id={`bbk-${p.name}`}
                        value={String(kwargs[p.name] ?? p.default ?? "")}
                        onChange={(e) => setField(p.name, e.target.value)}
                        className="h-8 font-mono text-xs"
                      />
                    </div>
                  ))}
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function NumberField({
  id,
  label,
  value,
  onChange,
  hint,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (v: number) => void;
  hint?: string;
}) {
  return (
    <div className="grid gap-1">
      <Label htmlFor={id}>
        <span className="font-mono text-xs">{label}</span>
      </Label>
      <Input
        id={id}
        type="number"
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
        className="h-8 font-mono text-xs"
      />
      {hint ? (
        <span className="text-[10px] text-[var(--text-secondary)]">{hint}</span>
      ) : null}
    </div>
  );
}

/**
 * Project a `BackboneSelection` into the SB3 `policy_kwargs` block
 * accepted by the `BackboneFeaturesExtractor`. The shape matches the
 * one used by the example specs under `configs/rl/policies/*.yaml`.
 */
export function backboneToPolicyKwargs(b: BackboneSelection): Record<string, unknown> {
  return {
    features_extractor_class:
      "aqp.rl.policies.feature_extractors.BackboneFeaturesExtractor",
    features_extractor_kwargs: {
      backbone_alias: b.alias,
      sequence_length: b.sequence_length,
      ...(b.input_features > 0 ? { input_features: b.input_features } : {}),
      features_dim: b.features_dim,
      backbone_kwargs: b.backbone_kwargs,
    },
  };
}
