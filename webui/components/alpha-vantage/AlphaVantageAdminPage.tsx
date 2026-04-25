"use client";

import { App, Button, Card, Form, Input, Select, Space, Typography } from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Paragraph, Text } = Typography;

interface HealthPayload {
  enabled: boolean;
  credentials_loaded: boolean;
  base_url: string;
  rpm_limit: number;
  daily_limit: number;
  cache_backend: string;
  message?: string | null;
}

interface BulkForm {
  category: string;
  symbols: string;
  extra_params?: string;
}

interface BulkResponse {
  task_id: string;
  stream_url: string;
  category: string;
  symbols: string[];
}

export function AlphaVantageAdminPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm<BulkForm>();
  const [queued, setQueued] = useState<BulkResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const health = useApiQuery<HealthPayload>({
    queryKey: ["alpha-vantage", "health", "admin"],
    path: "/alpha-vantage/health",
    refetchInterval: 60_000,
  });

  async function submit() {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      const payload = {
        category: values.category,
        symbols: values.symbols.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean),
        extra_params: parseJson(values.extra_params),
      };
      const res = await apiFetch<BulkResponse>("/alpha-vantage/bulk-load", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setQueued(res);
      message.success(`Queued Alpha Vantage bulk load ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageContainer
      title="Alpha Vantage Admin"
      subtitle="Provider health, rate-limit posture, and Celery-backed bulk loads into AQP storage."
    >
      <Card title="Provider health" size="small">
        <Space direction="vertical">
          <Text>Enabled: {String(health.data?.enabled ?? false)}</Text>
          <Text>Credentials loaded: {String(health.data?.credentials_loaded ?? false)}</Text>
          <Text>Base URL: {health.data?.base_url ?? "n/a"}</Text>
          <Text>Rate limits: {health.data?.rpm_limit ?? 0} rpm, daily {health.data?.daily_limit || "unlimited"}</Text>
          <Text>Cache: {health.data?.cache_backend ?? "n/a"}</Text>
          {health.data?.message ? <Text type="warning">{health.data.message}</Text> : null}
        </Space>
      </Card>

      <Card title="Bulk load" size="small" style={{ marginTop: 16 }}>
        <Form<BulkForm>
          form={form}
          layout="vertical"
          initialValues={{ category: "timeseries", symbols: "IBM, MSFT", extra_params: "{\"function\":\"daily_adjusted\"}" }}
          onFinish={submit}
        >
          <Form.Item label="Category" name="category" rules={[{ required: true }]}>
            <Select
              options={["timeseries", "fundamentals", "universe", "news", "earnings", "technicals", "options"].map((value) => ({
                value,
                label: value,
              }))}
            />
          </Form.Item>
          <Form.Item label="Symbols" name="symbols" rules={[{ required: true }]}>
            <Input.TextArea autoSize placeholder="IBM, MSFT, AAPL" />
          </Form.Item>
          <Form.Item label="Extra params JSON" name="extra_params">
            <Input.TextArea autoSize placeholder='{"function":"daily_adjusted"}' />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting}>
            Queue bulk load
          </Button>
        </Form>
        {queued ? (
          <Paragraph style={{ marginTop: 16 }} copyable={{ text: queued.task_id }}>
            Queued task: {queued.task_id}
          </Paragraph>
        ) : null}
      </Card>
    </PageContainer>
  );
}

function parseJson(raw?: string): Record<string, unknown> {
  if (!raw?.trim()) return {};
  const parsed = JSON.parse(raw);
  return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
}
