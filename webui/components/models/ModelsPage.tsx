"use client";

import {
  CloudDownloadOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";

const { Text, Paragraph } = Typography;

interface ProviderControl {
  provider: string;
  deep_model: string;
  quick_model: string;
  ollama_host: string;
  vllm_base_url: string;
  ollama_online: boolean;
  ollama_models: string[];
  vllm_online: boolean;
  vllm_models: string[];
}

interface ProviderCatalog {
  active: string;
  providers: Array<{
    slug: string;
    default_deep_model: string;
    default_quick_model: string;
  }>;
}

interface RunningModelEntry {
  name: string;
  size: number;
  digest: string;
  expires_at: string;
}

interface RunningModelsResponse {
  running: RunningModelEntry[];
}

interface VllmProfileSummary {
  name: string;
  path: string;
  provider: string;
  model: string;
  served_model_name: string;
  base_url: string;
  hf_model_id: string;
  compose_profile: string;
  compose_service: string;
  compose: { running: boolean; state: string; raw: string };
  probe: { online: boolean; models: string[]; error: string | null };
}

interface VllmServingSummary {
  configured_base_url: string;
  docker_available: boolean;
  profiles: VllmProfileSummary[];
}

interface TaskAccepted {
  task_id: string;
  stream_url?: string | null;
}

function bytesToHuman(bytes: number): string {
  if (!bytes) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)} ${u[i]}`;
}

export function ModelsPage() {
  const { message, modal } = App.useApp();

  const providerCatalog = useApiQuery<ProviderCatalog>({
    queryKey: ["agentic", "providers"],
    path: "/agentic/providers",
    staleTime: 30_000,
  });
  const providerControl = useApiQuery<ProviderControl>({
    queryKey: ["agentic", "provider-control"],
    path: "/agentic/provider-control",
    staleTime: 10_000,
  });
  const runningModels = useApiQuery<RunningModelsResponse>({
    queryKey: ["agentic", "models", "running"],
    path: "/agentic/models/running",
    refetchInterval: 30_000,
  });
  const vllmProfiles = useApiQuery<VllmServingSummary>({
    queryKey: ["agentic", "vllm", "profiles"],
    path: "/agentic/vllm/profiles",
    refetchInterval: 30_000,
  });

  const [providerDraft, setProviderDraft] = useState({
    provider: "",
    deep_model: "",
    quick_model: "",
    ollama_host: "",
    vllm_base_url: "",
  });
  const [pullName, setPullName] = useState("");
  const [pullTaskId, setPullTaskId] = useState<string | null>(null);
  const [vllmTaskId, setVllmTaskId] = useState<string | null>(null);

  const pullStream = useChatStream(pullTaskId);
  const vllmStream = useChatStream(vllmTaskId);

  useEffect(() => {
    if (!providerControl.data) return;
    setProviderDraft({
      provider: providerControl.data.provider ?? "",
      deep_model: providerControl.data.deep_model ?? "",
      quick_model: providerControl.data.quick_model ?? "",
      ollama_host: providerControl.data.ollama_host ?? "",
      vllm_base_url: providerControl.data.vllm_base_url ?? "",
    });
  }, [providerControl.data]);

  const providerOptions = useMemo(
    () => (providerCatalog.data?.providers ?? []).map((p) => ({ label: p.slug, value: p.slug })),
    [providerCatalog.data],
  );

  const pullProgressEvent = useMemo(() => {
    const events = pullStream.events;
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i];
      if (ev && typeof ev.percent === "number") return ev;
    }
    return null;
  }, [pullStream.events]);

  async function saveProviderControl() {
    try {
      await apiFetch("/agentic/provider-control", {
        method: "PUT",
        body: JSON.stringify(providerDraft),
      });
      message.success("Provider defaults saved");
      providerControl.refetch();
      providerCatalog.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function startPull() {
    if (!pullName.trim()) {
      message.warning("Enter a model tag, e.g. llama3.2 or nemotron:latest");
      return;
    }
    try {
      const res = await apiFetch<TaskAccepted>("/agentic/models/pull", {
        method: "POST",
        body: JSON.stringify({ name: pullName.trim() }),
      });
      setPullTaskId(res.task_id);
      message.success(`Pull queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function deleteOllamaModel(name: string) {
    modal.confirm({
      title: `Delete Ollama model ${name}?`,
      content: "This frees disk space; the model can be re-pulled later.",
      okType: "danger",
      okText: "Delete",
      onOk: async () => {
        try {
          await apiFetch(`/agentic/models/${encodeURIComponent(name)}`, {
            method: "DELETE",
          });
          message.success(`Deleted ${name}`);
          providerControl.refetch();
          runningModels.refetch();
        } catch (err) {
          message.error((err as Error).message);
        }
      },
    });
  }

  async function startVllmProfile(profile: string) {
    try {
      const res = await apiFetch<TaskAccepted>("/agentic/vllm/start", {
        method: "POST",
        body: JSON.stringify({ profile }),
      });
      setVllmTaskId(res.task_id);
      message.success(`vLLM start queued: ${profile}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function stopVllmProfile(profile: string) {
    try {
      const res = await apiFetch<TaskAccepted>("/agentic/vllm/stop", {
        method: "POST",
        body: JSON.stringify({ profile }),
      });
      setVllmTaskId(res.task_id);
      message.success(`vLLM stop queued: ${profile}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Models & Providers"
      subtitle="Pull, delete, and serve local LLMs (Ollama + vLLM) used by the agentic trader."
    >
      {/* Provider defaults */}
      <Card
        title="Provider defaults"
        extra={
          providerControl.isLoading ? (
            <Spin size="small" />
          ) : (
            <Tag color={providerControl.data?.provider ? "blue" : "default"}>
              {providerControl.data?.provider || "unset"}
            </Tag>
          )
        }
      >
        <Form layout="vertical">
          <Row gutter={16}>
            <Col xs={24} md={6}>
              <Form.Item label="Provider">
                <Select
                  value={providerDraft.provider || undefined}
                  options={providerOptions}
                  onChange={(value) => setProviderDraft((prev) => ({ ...prev, provider: value }))}
                  allowClear
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label="Deep model">
                <Input
                  value={providerDraft.deep_model}
                  onChange={(e) =>
                    setProviderDraft((prev) => ({ ...prev, deep_model: e.target.value }))
                  }
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label="Quick model">
                <Input
                  value={providerDraft.quick_model}
                  onChange={(e) =>
                    setProviderDraft((prev) => ({ ...prev, quick_model: e.target.value }))
                  }
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item label="Ollama host">
                <Input
                  value={providerDraft.ollama_host}
                  onChange={(e) =>
                    setProviderDraft((prev) => ({ ...prev, ollama_host: e.target.value }))
                  }
                  placeholder="http://localhost:11434"
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item label="vLLM base URL override">
                <Input
                  value={providerDraft.vllm_base_url}
                  onChange={(e) =>
                    setProviderDraft((prev) => ({ ...prev, vllm_base_url: e.target.value }))
                  }
                  placeholder="http://localhost:8002/v1"
                />
              </Form.Item>
            </Col>
          </Row>
          <Space>
            <Button type="primary" onClick={saveProviderControl}>
              Save defaults
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                providerControl.refetch();
                runningModels.refetch();
                vllmProfiles.refetch();
              }}
            >
              Refresh status
            </Button>
          </Space>
        </Form>
      </Card>

      {/* Ollama */}
      <Card
        title={
          <Space>
            <span>Ollama</span>
            <Tag color={providerControl.data?.ollama_online ? "green" : "default"}>
              {providerControl.data?.ollama_online ? "online" : "offline"}
            </Tag>
            <Text type="secondary">{providerControl.data?.ollama_host || "(host unset)"}</Text>
          </Space>
        }
        style={{ marginTop: 16 }}
      >
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Card size="small" title="Pull a model">
              <Form layout="vertical">
                <Form.Item label="Model tag" tooltip="e.g. nemotron, llama3.2:latest, qwen2:7b">
                  <Input
                    value={pullName}
                    onChange={(e) => setPullName(e.target.value)}
                    placeholder="llama3.2"
                    onPressEnter={startPull}
                  />
                </Form.Item>
                <Space>
                  <Button
                    type="primary"
                    icon={<CloudDownloadOutlined />}
                    onClick={startPull}
                    disabled={!pullName.trim()}
                  >
                    Pull
                  </Button>
                  {pullTaskId ? (
                    <Tag color="processing">{pullStream.status}</Tag>
                  ) : null}
                </Space>
                {pullTaskId ? (
                  <div style={{ marginTop: 12 }}>
                    <Progress
                      percent={
                        pullProgressEvent && typeof pullProgressEvent.percent === "number"
                          ? Math.min(100, Math.round(pullProgressEvent.percent as number))
                          : pullStream.done
                            ? 100
                            : 0
                      }
                      status={
                        pullStream.error
                          ? "exception"
                          : pullStream.done
                            ? "success"
                            : "active"
                      }
                    />
                    <Paragraph type="secondary" style={{ marginTop: 8 }}>
                      {String(
                        pullProgressEvent?.message ??
                          pullStream.events[pullStream.events.length - 1]?.message ??
                          "",
                      )}
                    </Paragraph>
                  </div>
                ) : null}
              </Form>
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card
              size="small"
              title={`Local models (${providerControl.data?.ollama_models.length ?? 0})`}
              extra={
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={() => providerControl.refetch()}
                >
                  Refresh
                </Button>
              }
            >
              {(providerControl.data?.ollama_models ?? []).length === 0 ? (
                <Empty description="No local models" />
              ) : (
                <List
                  size="small"
                  dataSource={providerControl.data?.ollama_models ?? []}
                  renderItem={(name) => (
                    <List.Item
                      actions={[
                        <Button
                          key="del"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => deleteOllamaModel(name)}
                        >
                          Delete
                        </Button>,
                      ]}
                    >
                      <Space>
                        <Tag color="blue">{name}</Tag>
                      </Space>
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Col>
        </Row>
        <Card size="small" title="Running models" style={{ marginTop: 16 }}>
          {(runningModels.data?.running ?? []).length === 0 ? (
            <Empty description="None loaded" />
          ) : (
            <Table<RunningModelEntry>
              size="small"
              rowKey="name"
              dataSource={runningModels.data?.running ?? []}
              pagination={false}
              columns={[
                { title: "Model", dataIndex: "name", key: "name" },
                {
                  title: "Size",
                  dataIndex: "size",
                  key: "size",
                  render: (v: number) => bytesToHuman(v),
                },
                { title: "Digest", dataIndex: "digest", key: "digest", ellipsis: true },
                { title: "Expires", dataIndex: "expires_at", key: "expires_at" },
              ]}
            />
          )}
        </Card>
      </Card>

      {/* vLLM */}
      <Card
        title={
          <Space>
            <span>vLLM</span>
            <Tag color={vllmProfiles.data?.docker_available ? "blue" : "default"}>
              docker {vllmProfiles.data?.docker_available ? "available" : "unavailable"}
            </Tag>
            {providerControl.data?.vllm_base_url ? (
              <Text type="secondary">
                base URL: <code>{providerControl.data.vllm_base_url}</code>
              </Text>
            ) : null}
          </Space>
        }
        style={{ marginTop: 16 }}
      >
        {!vllmProfiles.data?.docker_available ? (
          <Alert
            type="info"
            showIcon
            message="Docker CLI not detected"
            description="vLLM start/stop requires the Docker CLI on the API host. Profiles below are still listed and probed; you can start them manually with docker compose."
            style={{ marginBottom: 16 }}
          />
        ) : null}

        {(vllmProfiles.data?.profiles ?? []).length === 0 ? (
          <Empty description="No vLLM profiles found under configs/llm/*.yaml" />
        ) : (
          <Row gutter={[16, 16]}>
            {(vllmProfiles.data?.profiles ?? []).map((profile) => (
              <Col xs={24} md={12} key={profile.name}>
                <Card
                  size="small"
                  title={
                    <Space>
                      <RocketOutlined />
                      <span>{profile.name}</span>
                      <Tag color={profile.compose.running ? "green" : "default"}>
                        {profile.compose.state}
                      </Tag>
                      <Tag color={profile.probe.online ? "green" : "default"}>
                        {profile.probe.online ? "served" : "offline"}
                      </Tag>
                    </Space>
                  }
                  extra={
                    <Space>
                      <Button
                        size="small"
                        type="primary"
                        icon={<PlayCircleOutlined />}
                        onClick={() => startVllmProfile(profile.name)}
                        disabled={!vllmProfiles.data?.docker_available}
                      >
                        Start
                      </Button>
                      <Button
                        size="small"
                        icon={<PoweroffOutlined />}
                        onClick={() => stopVllmProfile(profile.name)}
                        disabled={!vllmProfiles.data?.docker_available}
                      >
                        Stop
                      </Button>
                    </Space>
                  }
                >
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="Model">
                      <code>{profile.model}</code>
                    </Descriptions.Item>
                    <Descriptions.Item label="Served as">
                      <code>{profile.served_model_name}</code>
                    </Descriptions.Item>
                    <Descriptions.Item label="HF id">
                      <code>{profile.hf_model_id || "—"}</code>
                    </Descriptions.Item>
                    <Descriptions.Item label="Base URL">
                      <code>{profile.base_url}</code>
                    </Descriptions.Item>
                    <Descriptions.Item label="Compose">
                      <code>
                        {`docker compose --profile ${profile.compose_profile} up -d ${profile.compose_service}`}
                      </code>
                    </Descriptions.Item>
                    <Descriptions.Item label="Probed models">
                      {profile.probe.models.length ? (
                        <Space wrap size={4}>
                          {profile.probe.models.map((m) => (
                            <Tag key={m} color="purple">
                              {m}
                            </Tag>
                          ))}
                        </Space>
                      ) : (
                        <Text type="secondary">—</Text>
                      )}
                    </Descriptions.Item>
                  </Descriptions>
                </Card>
              </Col>
            ))}
          </Row>
        )}

        {vllmTaskId ? (
          <Card size="small" title="vLLM task progress" style={{ marginTop: 16 }}>
            <Tag>{vllmStream.status}</Tag>
            <List
              size="small"
              dataSource={vllmStream.events.slice(-50)}
              renderItem={(e, idx) => (
                <List.Item key={`vllm-evt-${idx}`}>
                  <Space>
                    <Tag>{String(e.stage ?? "info")}</Tag>
                    <Text>{String(e.message ?? "")}</Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        ) : null}
      </Card>
    </PageContainer>
  );
}
