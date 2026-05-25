import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MlApi, type MlPullBody } from "@/lib/api/ml";

/**
 * HuggingFace / TorchHub model puller form.
 *
 * Routes through `POST /ml/models/pull`, which queues a Celery task
 * driving `HuggingFaceAdapter.pull` or `TorchHubAdapter.pull`. The
 * adapter resolves auth tokens via the platform's
 * `CredentialResolver` chain (Hard Rule 26) so the user never enters
 * an HF token in the UI.
 */
export function MlPullPage() {
  const [source, setSource] = useState<MlPullBody["source"]>("huggingface");
  const [modelName, setModelName] = useState("");
  const [revision, setRevision] = useState("");
  const [includeExamples, setIncludeExamples] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setTaskId(null);
    try {
      const body: MlPullBody = {
        source,
        model_name: modelName.trim(),
        revision: revision.trim() || undefined,
        include_examples: includeExamples,
      };
      const result = await MlApi.pull(body);
      setTaskId(result.task_id);
    } catch (exc) {
      setError((exc as Error).message ?? "pull failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Pull model</h1>
        <p className="text-muted-foreground text-sm">
          Download a model from HuggingFace Hub or TorchHub via the
          platform adapters. Tokens resolve through{" "}
          <code>CredentialResolver</code>; TorchHub names must be on
          the platform allow-list.
        </p>
      </header>

      <form className="flex max-w-lg flex-col gap-4" onSubmit={handleSubmit}>
        <div>
          <Label htmlFor="ml-pull-source">Source</Label>
          <select
            id="ml-pull-source"
            value={source}
            onChange={(e) => setSource(e.target.value as MlPullBody["source"])}
            className="border-input bg-background mt-1 h-9 w-full rounded-md border px-3 text-sm"
          >
            <option value="huggingface">HuggingFace</option>
            <option value="torchhub">TorchHub</option>
          </select>
        </div>

        <div>
          <Label htmlFor="ml-pull-name">Model name</Label>
          <Input
            id="ml-pull-name"
            placeholder={
              source === "huggingface"
                ? "ProsusAI/finbert"
                : "pytorch/vision/resnet50"
            }
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
            required
          />
        </div>

        <div>
          <Label htmlFor="ml-pull-revision">Revision (optional)</Label>
          <Input
            id="ml-pull-revision"
            placeholder="main"
            value={revision}
            onChange={(e) => setRevision(e.target.value)}
          />
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeExamples}
            onChange={(e) => setIncludeExamples(e.target.checked)}
          />
          Include examples folder when present
        </label>

        <Button type="submit" disabled={submitting || !modelName.trim()}>
          {submitting ? "Queuing…" : "Pull model"}
        </Button>
      </form>

      {error ? (
        <div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      {taskId ? (
        <div className="rounded border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
          Queued task <code>{taskId}</code>. Watch the chat stream for
          progress frames.
        </div>
      ) : null}
    </div>
  );
}
