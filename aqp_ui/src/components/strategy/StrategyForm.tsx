"use client";

import Form from "@rjsf/antd";
import validator from "@rjsf/validator-ajv8";
import { Alert, Tabs } from "antd";
import { parse, stringify } from "yaml";
import { useState } from "react";

import { EntityPickerWidget } from "./EntityPickerWidget";
import { paperRecipeSchema, paperRecipeUiSchema } from "@/lib/strategy/schema";

const widgets = { EntityPickerWidget };

export interface StrategyFormProps {
  initialYaml?: string;
  initialJson?: Record<string, unknown>;
  onSubmit: (args: {
    yamlText: string;
    json: Record<string, unknown>;
  }) => Promise<void>;
}

/**
 * Schema-driven recipe editor.
 *
 * AGENTS rule 8: every credential / dataset / namespace selection
 * binds to <EntityPicker /> via the EntityPickerWidget bridge.
 * The user NEVER types a raw API key into this form.
 *
 * YAML <-> JSON round-trip:
 *   - Load: parse incoming YAML to JSON, edit.
 *   - Save: stringify back to YAML, POST to BFF, BFF forwards to
 *     upstream /paper/recipes which hash-locks into
 *     paper_recipe_spec_versions (hash-locked, immutable).
 */
export function StrategyForm({
  initialYaml,
  initialJson,
  onSubmit,
}: StrategyFormProps) {
  const [parseError, setParseError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [tab, setTab] = useState<"form" | "yaml">("form");
  const [yamlText, setYamlText] = useState<string>(
    initialYaml ?? (initialJson ? stringify(initialJson) : ""),
  );
  const [formData, setFormData] = useState<Record<string, unknown> | undefined>(
    initialYaml ? safeParseYaml(initialYaml) : initialJson,
  );

  return (
    <div className="flex flex-col gap-4">
      {parseError ? (
        <Alert
          type="error"
          message="YAML parse error"
          description={parseError}
          showIcon
        />
      ) : null}

      <Tabs
        activeKey={tab}
        onChange={(key) => {
          if (key === "yaml" && formData) {
            setYamlText(stringify(formData));
          } else if (key === "form") {
            const parsed = safeParseYaml(yamlText);
            if (parsed) setFormData(parsed);
          }
          setTab(key as "form" | "yaml");
        }}
        items={[
          {
            key: "form",
            label: "Form editor",
            children: (
              <Form
                schema={paperRecipeSchema}
                uiSchema={paperRecipeUiSchema}
                validator={validator}
                widgets={widgets}
                formData={formData}
                disabled={submitting}
                onChange={(e) => setFormData(e.formData as Record<string, unknown>)}
                onSubmit={async (e) => {
                  setSubmitting(true);
                  try {
                    const json = e.formData as Record<string, unknown>;
                    const yamlOut = stringify(json);
                    await onSubmit({ yamlText: yamlOut, json });
                  } finally {
                    setSubmitting(false);
                  }
                }}
              />
            ),
          },
          {
            key: "yaml",
            label: "Raw YAML",
            children: (
              <textarea
                value={yamlText}
                onChange={(e) => setYamlText(e.target.value)}
                onBlur={() => {
                  const parsed = safeParseYaml(yamlText);
                  if (parsed) {
                    setFormData(parsed);
                    setParseError(null);
                  } else {
                    setParseError("Could not parse YAML. Check indentation and quotes.");
                  }
                }}
                disabled={submitting}
                spellCheck={false}
                className="min-h-[400px] w-full rounded border p-3 font-mono text-xs"
                style={{
                  background: "var(--bg-elevated)",
                  borderColor: "var(--border-default)",
                  color: "var(--text-primary)",
                }}
              />
            ),
          },
        ]}
      />
    </div>
  );
}

function safeParseYaml(text: string): Record<string, unknown> | undefined {
  try {
    const out = parse(text);
    return typeof out === "object" && out !== null
      ? (out as Record<string, unknown>)
      : undefined;
  } catch {
    return undefined;
  }
}
