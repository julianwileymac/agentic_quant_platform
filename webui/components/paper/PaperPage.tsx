"use client";

import { PauseCircleOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Card, Col, Form, Input, Row, Space, Switch, Tag } from "antd";
import type { ICellRendererParams } from "ag-grid-community";

import { DataGrid, paperRunColumns } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import type { PaperRunSummary } from "@/lib/api/domains";

export function PaperPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const list = useApiQuery<PaperRunSummary[]>({
    queryKey: ["paper", "runs"],
    path: "/paper/runs",
    refetchInterval: 5000,
    select: (raw) => (Array.isArray(raw) ? (raw as PaperRunSummary[]) : []),
  });

  async function start() {
    const v = await form.validateFields();
    try {
      const res = await apiFetch<{ id: string }>("/paper/start", {
        method: "POST",
        body: JSON.stringify({
          config_path: v.config_path,
          dry_run: Boolean(v.dry_run),
        }),
      });
      message.success(`Paper run started (${res.id})`);
      list.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function stop(id: string) {
    try {
      await apiFetch(`/paper/${id}/stop`, { method: "POST" });
      message.success("Stopped");
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
                config_path: "configs/paper/alpaca_mean_rev.yaml",
                dry_run: true,
              }}
            >
              <Form.Item label="Config path" name="config_path" rules={[{ required: true }]}>
                <Input placeholder="configs/paper/..." />
              </Form.Item>
              <Form.Item label="Dry run" name="dry_run" valuePropName="checked">
                <Switch />
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
                  cellRenderer: (p: ICellRendererParams<PaperRunSummary>) => (
                    <Space>
                      <Button
                        size="small"
                        icon={<PauseCircleOutlined />}
                        danger
                        onClick={() => p.data && stop(p.data.id)}
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
