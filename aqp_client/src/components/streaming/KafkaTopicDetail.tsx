import { ArrowLeft, RefreshCcw } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import type { KafkaTopic, TopicSampleMessage } from "@/lib/api/streaming";

export function KafkaTopicDetail() {
  const { name = "" } = useParams<{ name: string }>();
  const decoded = decodeURIComponent(name);

  const topic = useApiQuery<KafkaTopic>({
    queryKey: ["streaming", "kafka", "topic", decoded],
    path: `/streaming/kafka/topics/${encodeURIComponent(decoded)}`,
    enabled: Boolean(decoded),
  });
  const sample = useApiQuery<TopicSampleMessage[]>({
    queryKey: ["streaming", "kafka", "topic", decoded, "messages"],
    path: `/streaming/kafka/topics/${encodeURIComponent(decoded)}/messages`,
    query: { limit: 50 },
    enabled: Boolean(decoded),
    select: (raw) => (Array.isArray(raw) ? (raw as TopicSampleMessage[]) : []),
  });

  const metrics: Metric[] = [
    {
      label: "Partitions",
      value: topic.data?.partitions ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
    },
    {
      label: "Replication factor",
      value: topic.data?.replication_factor ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
    },
    {
      label: "Internal",
      value: null,
      hint: <Badge variant="secondary">{topic.data?.is_internal ? "yes" : "no"}</Badge>,
    },
    {
      label: "Sample messages",
      value: sample.data?.length ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
    },
  ];

  const columns: ColumnDef<TopicSampleMessage>[] = [
    { key: "partition", header: "Partition", width: 110, align: "right", render: (r) => <span className="font-mono">{r.partition}</span> },
    { key: "offset", header: "Offset", width: 130, align: "right", render: (r) => <span className="font-mono">{r.offset}</span> },
    {
      key: "timestamp",
      header: "Timestamp",
      width: 160,
      render: (r) => (
        <span className="font-mono text-xs">
          {r.timestamp ? new Date(r.timestamp).toISOString() : "—"}
        </span>
      ),
    },
    { key: "key", header: "Key", width: 160, render: (r) => <span className="font-mono text-xs">{r.key ?? "—"}</span> },
    {
      key: "value",
      header: "Value preview",
      render: (r) => (
        <span className="line-clamp-1 font-mono text-[10px] text-[var(--text-secondary)]">
          {r.value_preview ?? ""}
        </span>
      ),
    },
  ];

  return (
    <PageContainer
      title={decoded}
      subtitle="Kafka topic detail. Partitions / RF + a 50-message sample for hot-stream inspection."
      extra={
        <div className="flex items-center gap-2">
          <Link to="/streaming/kafka">
            <Button variant="ghost" size="sm" className="gap-1">
              <ArrowLeft className="h-4 w-4" /> Back
            </Button>
          </Link>
          <Button variant="ghost" size="sm" onClick={() => sample.refetch()}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
        </div>
      }
    >
      <MetricsGrid metrics={metrics} columns={4} />

      <Card className="mt-3">
        <CardHeader>
          <CardTitle>Topic config</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="max-h-48 overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs">
            {JSON.stringify(topic.data?.config ?? {}, null, 2)}
          </pre>
        </CardContent>
      </Card>

      <Card className="mt-3 h-[50vh]">
        <CardHeader>
          <CardTitle>Sample messages</CardTitle>
          <Badge variant="secondary">{sample.data?.length ?? 0}</Badge>
        </CardHeader>
        <CardContent className="h-full p-0">
          <DataTable<TopicSampleMessage>
            rows={sample.data ?? []}
            rowKey={(r) => `${r.partition}-${r.offset}`}
            columns={columns}
            emptyState={sample.isPending ? <span>Loading…</span> : <span>No messages.</span>}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
