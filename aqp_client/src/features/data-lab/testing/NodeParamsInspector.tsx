import Form from "@rjsf/core";
import validator from "@rjsf/validator-ajv8";
import type { IChangeEvent } from "@rjsf/core";
import type { RJSFSchema, UiSchema } from "@rjsf/utils";
import { Code2, FileJson, Pin } from "lucide-react";
import { useMemo, useState } from "react";

import { CodeEditor } from "@/components/common/CodeEditor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import type { LabNodeSpec, LabNodeType } from "@/lib/api/lab";

interface NodeParamsInspectorProps {
  node: LabNodeSpec;
  /** Resolved NodeType metadata (palette entry) for ``node.type``. */
  nodeType?: LabNodeType | null;
  /** Last-known live status for this node from the WS envelope ring. */
  status?: string;
  /** Persist a params edit. The Testing canvas patches the LabGraph
   *  through ``patchLabGraph`` with the new node list. */
  onSubmit: (next: LabNodeSpec) => void | Promise<void>;
}

/**
 * Right-rail params inspector for the Testing-mode canvas.
 *
 * When the NodeType ships a ``params_schema`` (auto-generated from
 * the matching Pydantic model in :mod:`aqp.lab.params_models`), we
 * render a typed form via @rjsf/core + ajv8. When no schema is
 * available we fall back to a CodeMirror JSON editor so the user can
 * still author params for new / unschematised nodes.
 *
 * Phase 2 keeps the inspector intentionally simple — no field-level
 * EntityPicker wiring yet. EntityPicker integration lives behind
 * a uiSchema widget map we add per category in Phase 3.
 */
export function NodeParamsInspector({
  node,
  nodeType,
  status,
  onSubmit,
}: NodeParamsInspectorProps) {
  const [jsonDraft, setJsonDraft] = useState<string>(() =>
    JSON.stringify(node.params ?? {}, null, 2),
  );
  const schema = (nodeType?.params_schema as RJSFSchema | undefined) ?? null;
  const uiSchema = useMemo<UiSchema>(
    () => ({
      "ui:submitButtonOptions": { norender: true },
    }),
    [],
  );

  const handleRjsfChange = (event: IChangeEvent) => {
    const next: LabNodeSpec = {
      ...node,
      params: event.formData as Record<string, unknown>,
    };
    void onSubmit(next);
  };

  const handleJsonSave = () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(jsonDraft) as Record<string, unknown>;
    } catch (err) {
      toast.error(
        `Invalid JSON: ${err instanceof Error ? err.message : String(err)}`,
      );
      return;
    }
    void onSubmit({ ...node, params: parsed });
    toast.success(`Saved params for ${node.id ?? node.type}.`);
  };

  return (
    <Card className="border-0 shadow-none">
      <CardContent className="space-y-3 px-2 py-3">
        <div className="flex items-center gap-2">
          <Code2 className="h-4 w-4" />
          <code className="truncate text-xs font-mono">{node.type}</code>
          {status ? (
            <Badge
              variant={
                status === "done"
                  ? "positive"
                  : status === "error"
                    ? "negative"
                    : status === "halted" || status === "cancelled"
                      ? "warn"
                      : "secondary"
              }
              className="ml-auto"
            >
              {status}
            </Badge>
          ) : null}
        </div>
        {nodeType?.description ? (
          <p className="text-[11px] text-muted-foreground">{nodeType.description}</p>
        ) : null}
        {nodeType?.inputs && nodeType.inputs.length ? (
          <div className="flex flex-wrap gap-1 text-[10px]">
            {nodeType.inputs.map((port) => (
              <Badge key={`in-${port.name}`} variant="outline" className="gap-1">
                <Pin className="h-3 w-3 rotate-180" />
                {port.name}:{port.dtype}
              </Badge>
            ))}
          </div>
        ) : null}
        {nodeType?.outputs && nodeType.outputs.length ? (
          <div className="flex flex-wrap gap-1 text-[10px]">
            {nodeType.outputs.map((port) => (
              <Badge key={`out-${port.name}`} variant="secondary" className="gap-1">
                <Pin className="h-3 w-3" />
                {port.name}:{port.dtype}
              </Badge>
            ))}
          </div>
        ) : null}

        {schema ? (
          <div className="rjsf-aqp">
            <Form
              schema={schema}
              uiSchema={uiSchema}
              validator={validator}
              formData={node.params ?? {}}
              onChange={handleRjsfChange}
              showErrorList={false}
              liveValidate={false}
              tagName="div"
            />
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <FileJson className="h-4 w-4" />
              <span>No typed schema — edit params as JSON.</span>
            </div>
            <div className="h-56">
              <CodeEditor
                value={jsonDraft}
                onChange={setJsonDraft}
                language="json"
                height="100%"
              />
            </div>
            <Button
              size="sm"
              variant="outline"
              className="w-full"
              onClick={handleJsonSave}
            >
              Save params
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default NodeParamsInspector;
