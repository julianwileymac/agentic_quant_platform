/**
 * Builds index — submit a new Kaniko build + tail recent jobs.
 *
 * Tail uses WebSocket ``/manage/builds/{job_name}/logs/stream``
 * proxied through the admin BFF. Audit-first: submit goes through
 * ``POST /admin/builds`` which writes a row BEFORE the SDK call.
 */
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { adminApi, type BuildSubmitResponse } from "@/lib/api";

export function BuildsIndex() {
  const [imageRef, setImageRef] = useState("ghcr.io/aqp/demo:dev");
  const [configmap, setConfigmap] = useState("demo-dockerfile");
  const [submitted, setSubmitted] = useState<BuildSubmitResponse[]>([]);

  const submit = useMutation<BuildSubmitResponse, Error, void>({
    mutationFn: async () =>
      adminApi.submitBuild({
        image_ref: imageRef,
        source: { kind: "configmap", configmap_name: configmap },
      }),
    onSuccess(data) {
      setSubmitted((prev) => [data, ...prev].slice(0, 25));
    },
  });

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Image builds</h1>
        <p className="text-sm text-muted-foreground">
          In-cluster Kaniko (Chainguard fork) builds. Credentials resolve via
          EKS Pod Identity / IRSA / Workload Identity Federation — never
          through Kubernetes Secrets containing cloud creds.
        </p>
      </header>
      <form
        className="space-y-4 rounded-lg border bg-card p-6"
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-4">
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">Image ref</div>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={imageRef}
              onChange={(e) => setImageRef(e.target.value)}
              required
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-500">ConfigMap with Dockerfile</div>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={configmap}
              onChange={(e) => setConfigmap(e.target.value)}
              required
            />
          </label>
        </div>
        <button
          type="submit"
          disabled={submit.isPending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {submit.isPending ? "Submitting..." : "Submit build"}
        </button>
        {submit.error ? <p className="text-sm text-red-600">{submit.error.message}</p> : null}
      </form>

      <div className="rounded-lg border bg-card p-6">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Recent submissions
        </h2>
        {submitted.length === 0 ? (
          <p className="text-sm text-muted-foreground">No submissions yet this session.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {submitted.map((entry) => (
              <li key={entry.data?.job_name ?? entry.status} className="rounded border p-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono">{entry.data?.job_name}</span>
                  <Link
                    className="text-xs text-blue-600 hover:underline"
                    to={`/builds/${entry.data?.job_name ?? ""}`}
                  >
                    open log stream
                  </Link>
                </div>
                <div className="text-xs text-muted-foreground">
                  {entry.data?.image_ref} - {entry.data?.namespace}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
