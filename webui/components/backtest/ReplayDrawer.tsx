"use client";

import { ExperimentOutlined, RocketOutlined } from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";

import { apiFetch } from "@/lib/api/client";

const { Text, Paragraph } = Typography;

interface FindingEdit {
  decision_id: string;
  vt_symbol?: string;
  ts?: string;
  action?: "BUY" | "SELL" | "HOLD" | string;
  size_pct?: number;
  rationale?: string;
}

interface ReplayDrawerProps {
  backtestId: string;
  open: boolean;
  initialEdits?: FindingEdit[];
  judgeReportId?: string | null;
  onClose: () => void;
  onQueued?: (taskId: string) => void;
}

interface SubmitResp {
  task_id: string;
  stream_url?: string;
}

export function ReplayDrawer({
  backtestId,
  open,
  initialEdits,
  judgeReportId,
  onClose,
  onQueued,
}: ReplayDrawerProps) {
  const { message } = App.useApp();
  const [edits, setEdits] = useState<FindingEdit[]>(initialEdits ?? []);
  const [note, setNote] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  // Re-seed edits when the drawer opens with new initial findings.
  if (open && initialEdits && initialEdits !== undefined && edits.length === 0 && initialEdits.length > 0) {
    setEdits(initialEdits);
  }

  async function submit() {
    if (!edits.length) {
      message.warning("Add at least one edit before queuing a replay.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await apiFetch<SubmitResp>(`/agentic/replay/${backtestId}`, {
        method: "POST",
        body: JSON.stringify({
          edits: edits.map((e) => ({
            decision_id: e.decision_id,
            action: e.action,
            size_pct: e.size_pct,
            rationale: e.rationale,
          })),
          note: note || undefined,
          judge_report_id: judgeReportId ?? undefined,
        }),
      });
      message.success(`Replay queued: ${res.task_id}`);
      onQueued?.(res.task_id);
      onClose();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function patch(decisionId: string, partial: Partial<FindingEdit>) {
    setEdits((prev) =>
      prev.map((e) => (e.decision_id === decisionId ? { ...e, ...partial } : e)),
    );
  }

  function removeEdit(decisionId: string) {
    setEdits((prev) => prev.filter((e) => e.decision_id !== decisionId));
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={
        <Space>
          <ExperimentOutlined />
          Counterfactual replay
        </Space>
      }
      width={720}
      extra={
        <Button
          type="primary"
          icon={<RocketOutlined />}
          loading={submitting}
          onClick={submit}
          disabled={!edits.length}
        >
          Queue replay
        </Button>
      }
    >
      <Paragraph type="secondary">
        Replay re-runs the backtest with these per-decision edits applied. The
        original ``AgentDecision`` rows and Parquet cache are <Text strong>not</Text>{" "}
        modified — the child run lives in <Tag>agent_replay_runs</Tag>.
      </Paragraph>
      {!edits.length ? (
        <Alert type="info" showIcon message="No pending edits. Apply suggestions from the Judge tab to add them." />
      ) : null}
      <Table<FindingEdit>
        rowKey="decision_id"
        dataSource={edits}
        size="small"
        pagination={false}
        columns={[
          {
            title: "Symbol",
            dataIndex: "vt_symbol",
            render: (v) => <Text code>{v ?? "—"}</Text>,
            width: 130,
          },
          { title: "TS", dataIndex: "ts", width: 160 },
          {
            title: "Action",
            dataIndex: "action",
            width: 120,
            render: (v: string, row) => (
              <Select
                size="small"
                value={v ?? "HOLD"}
                onChange={(next) => patch(row.decision_id, { action: next })}
                options={["BUY", "SELL", "HOLD"].map((a) => ({ value: a, label: a }))}
                style={{ width: "100%" }}
              />
            ),
          },
          {
            title: "Size %",
            dataIndex: "size_pct",
            width: 110,
            render: (v: number, row) => (
              <InputNumber
                size="small"
                style={{ width: "100%" }}
                min={0}
                max={1}
                step={0.05}
                value={v ?? 0}
                onChange={(next) => patch(row.decision_id, { size_pct: next ?? 0 })}
              />
            ),
          },
          {
            title: "Rationale",
            dataIndex: "rationale",
            render: (v: string, row) => (
              <Input
                size="small"
                value={v ?? ""}
                onChange={(e) => patch(row.decision_id, { rationale: e.target.value })}
              />
            ),
          },
          {
            title: "",
            width: 60,
            render: (_, row) => (
              <Button size="small" type="link" danger onClick={() => removeEdit(row.decision_id)}>
                Drop
              </Button>
            ),
          },
        ]}
      />
      <Form layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item label="Note (optional)">
          <Input.TextArea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </Form.Item>
      </Form>
    </Drawer>
  );
}
