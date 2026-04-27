"use client";

import { PauseCircleOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Card, Col, Form, Input, Row, Space, Switch, Tag } from "antd";
import type { ICellRendererParams } from "ag-grid-community";

import { DataGrid, paperRunColumns } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import type { PaperRunSummary } from "@/lib/api/domains";

interface PaperRunRow extends PaperRunSummary {
  task_id?: string | null;
}

export function PaperPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const list = useApiQuery<PaperRunRow[]>({
    queryKey: ["paper", "runs"],
    path: "/paper/runs",
    refetchInterval: 5000,
    select: (raw) => (Array.isArray(raw) ? (raw as PaperRunRow[]) : []),
  });

  async function start() {
    const v = await form.validateFields();
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(String(v.config_json || "{}"));
    } catch (err) {
      message.error(`Config must be valid JSON: ${(err as Error).message}`);
      return;
    }
    if (v.dry_run) {
      const session = (parsed as { session?: Record<string, unknown> }).session ?? {};
      session.dry_run = true;
      (parsed as { session?: Record<string, unknown> }).session = session;
    }
    try {
      const res = await apiFetch<{ task_id: string }>("/paper/start", {
        method: "POST",
        body: JSON.stringify({
          config: parsed,
          run_name: String(v.run_name || "paper-adhoc"),
        }),
      });
      message.success(`Paper run queued (${res.task_id})`);
      list.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function stop(row: PaperRunRow) {
    const target = row.task_id ?? row.id;
    if (!target) {
      message.warning("This run has no task id yet.");
      return;
    }
    try {
      await apiFetch(`/paper/stop/${target}`, { method: "POST" });
      message.success("Stop signal sent");
      list.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Paper trading"
      subtitle="Run strategies against a paper broker. Stop with one click."
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => list.refetch()}>
          Refresh
        </Button>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="Start a paper run" size="small">
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                run_name: "paper-adhoc",
                dry_run: true,
                config_json: JSON.stringify(
                  {
                    session: { run_name: "paper-adhoc", initial_cash: 100000 },
                    strategy: {
                      class: "FrameworkAlgorithm",
                      module_path: "aqp.strategies.framework",
                      kwargs: {
                        universe_model: {
                          class: "StaticUniverse",
                          module_path: "aqp.strategies.universes",
                          kwargs: { symbols: ["AAPL", "MSFT", "SPY"] },
                        },
                        alpha_model: {
                          class: "MeanReversionAlpha",
                          module_path: "aqp.strategies.mean_reversion",
                          kwargs: { lookback: 20, z_threshold: 2.0 },
                        },
                      },
                    },
                  },
                  null,
                  2,
                ),
              }}
            >
              <Form.Item label="Run name" name="run_name" rules={[{ required: true }]}>
                <Input placeholder="my-paper-run" />
              </Form.Item>
              <Form.Item label="Dry run" name="dry_run" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item
                label="Config (JSON)"
                name="config_json"
                rules={[{ required: true }]}
                tooltip="Inline PaperSessionConfig — equivalent to a configs/paper/*.yaml expressed as JSON."
              >
                <Input.TextArea autoSize={{ minRows: 8, maxRows: 16 }} style={{ fontFamily: "monospace" }} />
              </Form.Item>
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={start}>
                Start
              </Button>
            </Form>
            <div style={{ marginTop: 12 }}>
              <Tag color="blue">Heartbeat poll: 5s</Tag>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="Runs" size="small">
            <DataGrid<PaperRunSummary>
              rowData={list.data ?? []}
              loading={list.isLoading}
              columnDefs={[
                ...paperRunColumns,
                {
                  headerName: "Actions",
                  width: 120,
                  cellRenderer: (p: ICellRendererParams<PaperRunRow>) => (
                    <Space>
                      <Button
                        size="small"
                        icon={<PauseCircleOutlined />}
                        danger
                        onClick={() => p.data && stop(p.data)}
                      >
                        Stop
                      </Button>
                    </Space>
                  ),
                },
              ]}
              height={420}
            />
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
