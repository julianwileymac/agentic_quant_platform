"use client";

import { Alert, Empty, Space, Spin, Tag, Typography } from "antd";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface PreviewResp {
  candidate: { id: string; source: string; domain: string; field: string; description: string };
  values: Array<{ timestamp: string; value: number | null }>;
  count: number;
  coverage: { total: number; non_null: number; pct: number };
  error?: string | null;
}

interface Props {
  candidateId: string;
  vtSymbol?: string;
}

export function FeaturePreviewChart({ candidateId, vtSymbol }: Props) {
  const preview = useApiQuery<PreviewResp>({
    queryKey: ["feature-catalog", "preview", candidateId, vtSymbol ?? "—"],
    path: "/feature-catalog/preview",
    enabled: false,
  });

  // Trigger via mutation-like pattern: re-run when candidate changes.
  // Implement as effect-like: refetch on demand by reading mutation state.
  // For brevity we expose a button via the parent.
  if (preview.isLoading) return <Spin />;
  if (preview.error) return <Alert type="error" message={preview.error.message} />;
  if (!preview.data) return <Empty description="Click preview to materialize" image={Empty.PRESENTED_IMAGE_SIMPLE} />;

  const { candidate, values, coverage, error } = preview.data;
  if (error) return <Alert type="warning" showIcon message={error} />;
  if (values.length === 0) return <Empty description={`No data for ${candidate.field}`} image={Empty.PRESENTED_IMAGE_SIMPLE} />;

  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      <Space>
        <Tag color="blue">{candidate.source}</Tag>
        <Tag color="cyan">{candidate.domain}</Tag>
        <Text type="secondary" style={{ fontSize: 12 }}>
          coverage: {(coverage.pct * 100).toFixed(1)}% ({coverage.non_null}/{coverage.total})
        </Text>
      </Space>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={values} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <XAxis dataKey="timestamp" hide />
          <YAxis fontSize={11} width={48} />
          <Tooltip contentStyle={{ fontSize: 11 }} />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#3b82f6"
            strokeWidth={1.4}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </Space>
  );
}
