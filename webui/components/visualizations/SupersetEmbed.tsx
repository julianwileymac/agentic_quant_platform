"use client";

import { Alert, Button, Card, Skeleton, Space } from "antd";
import { useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api/client";

interface GuestTokenResponse {
  token: string;
  dashboard_uuid: string;
  superset_url: string;
}

interface SupersetEmbedProps {
  dashboardUuid?: string | null;
  title?: string;
}

const SUPERSET_URL = process.env.NEXT_PUBLIC_SUPERSET_URL ?? "http://localhost:8088";

export function SupersetEmbed({ dashboardUuid, title = "Superset Explorer" }: SupersetEmbedProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!dashboardUuid || !mountRef.current) return;
    const uuid: string = dashboardUuid;
    let cancelled = false;
    const mount = mountRef.current;
    mount.innerHTML = "";
    setLoading(true);
    setError(null);

    async function embed() {
      const { embedDashboard } = await import("@superset-ui/embedded-sdk");
      await embedDashboard({
        id: uuid,
        supersetDomain: SUPERSET_URL,
        mountPoint: mount,
        fetchGuestToken: async () => {
          const response = await apiFetch<GuestTokenResponse>("/visualizations/superset/guest-token", {
            method: "POST",
            body: JSON.stringify({ dashboard_uuid: uuid }),
          });
          return response.token;
        },
        dashboardUiConfig: {
          hideTitle: false,
          filters: { expanded: true },
        },
      });
    }

    embed()
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      mount.innerHTML = "";
    };
  }, [dashboardUuid]);

  if (!dashboardUuid) {
    return (
      <Alert
        type="info"
        showIcon
        message="No embedded dashboard configured"
        description="Run the Superset sync task, enable embedding for the created dashboard in Superset, then set AQP_SUPERSET_DEFAULT_DASHBOARD_UUID."
      />
    );
  }

  return (
    <Card
      title={title}
      extra={
        <Space>
          <Button href={`${SUPERSET_URL}/superset/dashboard/${dashboardUuid}/`} target="_blank" rel="noreferrer">
            Open Superset
          </Button>
        </Space>
      }
      styles={{ body: { padding: 0, minHeight: 520 } }}
    >
      {loading ? <Skeleton active style={{ padding: 24 }} /> : null}
      {error ? <Alert type="error" showIcon message="Superset embed failed" description={error} /> : null}
      <div ref={mountRef} style={{ width: "100%", minHeight: 640 }} />
    </Card>
  );
}
