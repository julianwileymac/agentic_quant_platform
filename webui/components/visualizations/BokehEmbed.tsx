"use client";

import { Alert, Card, Skeleton } from "antd";
import { useEffect, useId, useMemo, useState } from "react";

import { apiFetch } from "@/lib/api/client";

declare global {
  interface Window {
    Bokeh?: {
      embed: {
        embed_item: (item: unknown, target?: string) => void;
      };
    };
  }
}

export interface BokehChartSpec {
  kind: "line" | "scatter" | "histogram" | "candlestick" | "table";
  dataset_identifier: string;
  title?: string;
  x?: string;
  y?: string;
  groupby?: string | null;
  limit?: number;
  target_id?: string;
}

interface BokehRenderResponse {
  item: Record<string, unknown>;
}

interface BokehEmbedProps {
  spec: BokehChartSpec;
}

let bokehScriptPromise: Promise<void> | null = null;
let loadedBokehVersion: string | null = null;

export function BokehEmbed({ spec }: BokehEmbedProps) {
  const reactId = useId();
  const targetId = useMemo(
    () => spec.target_id ?? `bokeh-${reactId.replace(/[^a-zA-Z0-9_-]/g, "")}`,
    [reactId, spec.target_id],
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const payload = { ...spec, target_id: targetId };
    const container = document.getElementById(targetId);
    if (container) container.innerHTML = "";

    async function render() {
      const response = await apiFetch<BokehRenderResponse>("/visualizations/bokeh/render", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const version = typeof response.item.version === "string" ? response.item.version : "3.6.3";
      await loadBokehJs(version);
      if (!window.Bokeh) throw new Error("BokehJS did not load");
      window.Bokeh.embed.embed_item(response.item, targetId);
    }

    render()
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      const el = document.getElementById(targetId);
      if (el) el.innerHTML = "";
    };
  }, [spec, targetId]);

  return (
    <Card title={spec.title ?? "Bokeh chart"} styles={{ body: { minHeight: 420 } }}>
      {loading ? <Skeleton active /> : null}
      {error ? <Alert type="warning" showIcon message="Bokeh render unavailable" description={error} /> : null}
      <div id={targetId} style={{ width: "100%", minHeight: 420 }} />
    </Card>
  );
}

function loadBokehJs(version: string): Promise<void> {
  if (window.Bokeh && loadedBokehVersion === version) return Promise.resolve();
  if (bokehScriptPromise) return bokehScriptPromise;
  const bokehJsUrl = `https://cdn.bokeh.org/bokeh/release/bokeh-${version}.min.js`;
  bokehScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = bokehJsUrl;
    script.async = true;
    script.onload = () => {
      loadedBokehVersion = version;
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load ${bokehJsUrl}`));
    document.head.appendChild(script);
  });
  return bokehScriptPromise;
}
