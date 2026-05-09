import { GitBranch, Plus, RefreshCcw, Trash2 } from "lucide-react";
import { useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import {
  kafkaApi,
  type KafkaConsumerGroup,
  type KafkaTopic,
} from "@/lib/api/kafka";

interface CreateForm {
  name: string;
  partitions: number;
  replication_factor: number;
}

export function KafkaRoute() {
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<CreateForm>({
    name: "aqp.new-topic",
    partitions: 3,
    replication_factor: 1,
  });
  const [confirmCreate, setConfirmCreate] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<KafkaTopic | null>(null);

  const topics = useApiQuery<KafkaTopic[]>({
    queryKey: ["kafka", "topics"],
    path: "/streaming/kafka/topics",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const groups = useApiQuery<KafkaConsumerGroup[]>({
    queryKey: ["kafka", "groups"],
    path: "/streaming/kafka/consumer-groups",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const submitCreate = async () => {
    try {
      await kafkaApi.createTopic({
        name: createForm.name,
        partitions: createForm.partitions,
        replication_factor: createForm.replication_factor,
      });
      toast.success(`Topic ${createForm.name} created`);
      topics.refetch();
      setCreateOpen(false);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Create failed: ${msg}`);
    } finally {
      setConfirmCreate(false);
    }
  };

  const submitDelete = async () => {
    if (!confirmDelete) return;
    try {
      await kafkaApi.deleteTopic(confirmDelete.name);
      toast.success(`Topic ${confirmDelete.name} deleted`);
      topics.refetch();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Delete failed: ${msg}`);
    } finally {
      setConfirmDelete(null);
    }
  };

  return (
    <PageContainer
      title="Kafka"
      subtitle="Native Kafka admin — topics, consumer groups, lag. Mutations are friction-gated; sample messages open in a per-topic drawer (Phase 5 follow-up)."
      extra={
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              topics.refetch();
              groups.refetch();
            }}
          >
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button onClick={() => setCreateOpen(true)} className="gap-2">
            <Plus className="h-4 w-4" /> New topic
          </Button>
        </div>
      }
    >
      <Tabs defaultValue="topics">
        <TabsList>
          <TabsTrigger value="topics">Topics ({topics.data?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="groups">Consumer groups ({groups.data?.length ?? 0})</TabsTrigger>
        </TabsList>

        <TabsContent value="topics">
          <Card className="h-[calc(100vh-260px)]">
            <CardContent className="h-full p-0">
              <DataTable<KafkaTopic>
                rows={topics.data ?? []}
                rowKey={(t) => t.name}
                emptyState={topics.isPending ? <span>Loading topics…</span> : <span>No topics.</span>}
                columns={[
                  {
                    key: "name",
                    header: "Topic",
                    render: (t) => (
                      <div className="flex items-center gap-2">
                        <GitBranch className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                        <span className="font-mono">{t.name}</span>
                        {t.is_internal ? (
                          <Badge variant="secondary" className="text-[9px]">
                            internal
                          </Badge>
                        ) : null}
                      </div>
                    ),
                  },
                  {
                    key: "partitions",
                    header: "Partitions",
                    width: 110,
                    align: "right",
                    render: (t) => <Numeric value={t.partitions} kind="integer" digits={0} color="neutral" />,
                  },
                  {
                    key: "rf",
                    header: "RF",
                    width: 70,
                    align: "right",
                    render: (t) => <Numeric value={t.replication_factor} kind="integer" digits={0} color="neutral" />,
                  },
                  {
                    key: "config",
                    header: "Config",
                    render: (t) => (
                      <span className="font-mono text-[10px] text-[var(--text-secondary)]">
                        {summariseConfig(t.config)}
                      </span>
                    ),
                  },
                  {
                    key: "actions",
                    header: "Actions",
                    width: 130,
                    render: (t) => (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDelete(t);
                        }}
                        disabled={t.is_internal}
                        className="gap-1 text-[var(--neg-fg)]"
                      >
                        <Trash2 className="h-3.5 w-3.5" /> Delete
                      </Button>
                    ),
                  },
                ]}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="groups">
          <Card className="h-[calc(100vh-260px)]">
            <CardContent className="h-full p-0">
              <DataTable<KafkaConsumerGroup>
                rows={groups.data ?? []}
                rowKey={(g) => g.group_id}
                emptyState={
                  groups.isPending ? <span>Loading groups…</span> : <span>No consumer groups.</span>
                }
                columns={[
                  {
                    key: "id",
                    header: "Group",
                    render: (g) => <span className="font-mono">{g.group_id}</span>,
                  },
                  {
                    key: "state",
                    header: "State",
                    width: 130,
                    render: (g) => (
                      <Badge variant={g.state === "Stable" ? "positive" : "secondary"}>{g.state}</Badge>
                    ),
                  },
                  {
                    key: "members",
                    header: "Members",
                    width: 100,
                    align: "right",
                    render: (g) => <Numeric value={g.members} kind="integer" digits={0} color="neutral" />,
                  },
                  {
                    key: "topics",
                    header: "Topics",
                    render: (g) => (
                      <span className="font-mono text-xs">{(g.topics ?? []).join(", ") || "—"}</span>
                    ),
                  },
                ]}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {createOpen ? (
        <Card className="mt-4 max-w-xl">
          <CardContent className="grid gap-3 py-4">
            <div className="text-sm font-semibold">New topic</div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div className="flex flex-col gap-1 sm:col-span-3">
                <Label htmlFor="kafka-name">Topic name</Label>
                <Input
                  id="kafka-name"
                  className="font-mono"
                  value={createForm.name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="kafka-partitions">Partitions</Label>
                <Input
                  id="kafka-partitions"
                  type="number"
                  min={1}
                  value={createForm.partitions}
                  onChange={(e) =>
                    setCreateForm((f) => ({ ...f, partitions: Number(e.target.value) || 1 }))
                  }
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="kafka-rf">Replication factor</Label>
                <Input
                  id="kafka-rf"
                  type="number"
                  min={1}
                  value={createForm.replication_factor}
                  onChange={(e) =>
                    setCreateForm((f) => ({ ...f, replication_factor: Number(e.target.value) || 1 }))
                  }
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => setConfirmCreate(true)} className="gap-2">
                <Plus className="h-4 w-4" /> Create
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {confirmCreate ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(open) => !open && setConfirmCreate(false)}
          title={`Create topic ${createForm.name}`}
          consequence="Creates a Kafka topic. Existing topics with the same name fail. Replication factor must not exceed the number of available brokers."
          details={[
            { label: "Topic", value: createForm.name },
            { label: "Partitions", value: createForm.partitions },
            { label: "Replication factor", value: createForm.replication_factor },
          ]}
          confirmPhrase="CREATE"
          confirmLabel="Create topic"
          confirmVariant="warn"
          onConfirm={submitCreate}
        />
      ) : null}

      {confirmDelete ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(open) => !open && setConfirmDelete(null)}
          title={`Delete topic ${confirmDelete.name}`}
          consequence="Deletes the topic and all its data. This is irreversible. Type the topic name to confirm."
          details={[
            { label: "Topic", value: confirmDelete.name, tone: "negative" },
            { label: "Partitions", value: confirmDelete.partitions },
          ]}
          confirmPhrase={confirmDelete.name}
          confirmLabel="Delete topic"
          confirmVariant="destructive"
          onConfirm={submitDelete}
        />
      ) : null}
    </PageContainer>
  );
}

function summariseConfig(config: Record<string, string> | undefined): string {
  if (!config) return "—";
  const entries = Object.entries(config).slice(0, 3);
  if (!entries.length) return "—";
  return entries.map(([k, v]) => `${k}=${v}`).join(" · ");
}
