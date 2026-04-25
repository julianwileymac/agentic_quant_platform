"use client";

import { ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Empty, Input, Row, Space, Tag, Timeline, Typography } from "antd";
import type { ICellRendererParams } from "ag-grid-community";
import { useState } from "react";

import { DataGrid, crewRunColumns } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import type { CrewRunSummary } from "@/lib/api/domains";
import { useChatStream } from "@/lib/ws";

const { Text } = Typography;

export function CrewTracePage() {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskInput, setTaskInput] = useState("");
  const list = useApiQuery<CrewRunSummary[]>({
    queryKey: ["agents", "crews"],
    path: "/agents/crews",
    refetchInterval: 8000,
    select: (raw) => (Array.isArray(raw) ? (raw as CrewRunSummary[]) : []),
  });
  const stream = useChatStream(taskId);

  return (
    <PageContainer
      title="Crew trace"
      subtitle="Live event timeline for agent crews."
      extra={
        <Space>
          <Input
            placeholder="task id"
            value={taskInput}
            onChange={(e) => setTaskInput(e.target.value)}
            style={{ width: 220 }}
          />
          <Button onClick={() => setTaskId(taskInput || null)} type="primary">
            Subscribe
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => list.refetch()}>
            Refresh
          </Button>
        </Space>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card title="Recent crews" size="small">
            <DataGrid<CrewRunSummary>
              rowData={list.data ?? []}
              loading={list.isLoading}
              columnDefs={[
                ...crewRunColumns,
                {
                  headerName: "Watch",
                  width: 110,
                  cellRenderer: (p: ICellRendererParams<CrewRunSummary>) => (
                    <Button
                      size="small"
                      onClick={() => {
                        const tid = p.data?.task_id;
                        if (!tid) return;
                        setTaskInput(tid);
                        setTaskId(tid);
                      }}
                    >
                      Tail
                    </Button>
                  ),
                },
              ]}
              height={420}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title={
              <Space>
                Timeline
                {taskId ? <Tag>{taskId}</Tag> : null}
                {taskId ? (
                  <Tag color={stream.status === "open" ? "green" : "default"}>{stream.status}</Tag>
                ) : null}
              </Space>
            }
            size="small"
          >
            {!taskId ? (
              <Empty description="Pick a crew to tail" />
            ) : stream.events.length === 0 ? (
              <Text type="secondary">Waiting for events…</Text>
            ) : (
              <Timeline
                style={{ marginTop: 12 }}
                items={stream.events.map((e, i) => ({
                  color:
                    e.stage === "error"
                      ? "red"
                      : e.stage === "done"
                        ? "green"
                        : e.stage === "tool"
                          ? "purple"
                          : "blue",
                  children: (
                    <div>
                      <Space>
                        <Tag>{String(e.stage ?? "event")}</Tag>
                        {e.agent ? <Tag>{e.agent}</Tag> : null}
                        {e.tool ? <Tag color="purple">tool: {e.tool}</Tag> : null}
                      </Space>
                      <div style={{ fontSize: 12, opacity: 0.85, marginTop: 4 }}>
                        {e.message ?? e.delta ?? e.content ?? ""}
                      </div>
                      {e.tool_output ? (
                        <pre style={{ fontSize: 11, opacity: 0.7, marginTop: 4 }}>
                          {JSON.stringify(e.tool_output, null, 2).slice(0, 600)}
                        </pre>
                      ) : null}
                    </div>
                  ),
                  key: i,
                }))}
              />
            )}
            {stream.error ? (
              <Alert type="error" message={stream.error} style={{ marginTop: 8 }} />
            ) : null}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
