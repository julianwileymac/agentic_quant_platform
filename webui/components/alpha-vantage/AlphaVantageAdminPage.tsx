"use client";

import { Card, Space, Typography } from "antd";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

import { AlphaVantageBulkLoader } from "./AlphaVantageBulkLoader";

const { Text } = Typography;

interface HealthPayload {
  enabled: boolean;
  credentials_loaded: boolean;
  base_url: string;
  rpm_limit: number;
  daily_limit: number;
  cache_backend: string;
  message?: string | null;
}

export function AlphaVantageAdminPage() {
  const health = useApiQuery<HealthPayload>({
    queryKey: ["alpha-vantage", "health", "admin"],
    path: "/alpha-vantage/health",
    refetchInterval: 60_000,
  });

  return (
    <PageContainer
      title="Alpha Vantage Admin"
      subtitle="Provider health, rate-limit posture, and Celery-backed bulk loads into the per-endpoint Iceberg lake."
    >
      <Card title="Provider health" size="small">
        <Space direction="vertical">
          <Text>Enabled: {String(health.data?.enabled ?? false)}</Text>
          <Text>Credentials loaded: {String(health.data?.credentials_loaded ?? false)}</Text>
          <Text>Base URL: {health.data?.base_url ?? "n/a"}</Text>
          <Text>
            Rate limits: {health.data?.rpm_limit ?? 0} rpm, daily {health.data?.daily_limit || "unlimited"}
          </Text>
          <Text>Cache: {health.data?.cache_backend ?? "n/a"}</Text>
          {health.data?.message ? <Text type="warning">{health.data.message}</Text> : null}
        </Space>
      </Card>

      <div style={{ marginTop: 16 }}>
        <AlphaVantageBulkLoader />
      </div>
    </PageContainer>
  );
}
