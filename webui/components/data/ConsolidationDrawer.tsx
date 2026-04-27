"use client";

import {
  ExperimentOutlined,
  MergeCellsOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Checkbox,
  Descriptions,
  Drawer,
  Form,
  Input,
  List,
  Space,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { useChatStream } from "@/lib/ws";

const { Text, Paragraph } = Typography;

interface TaskAccepted {
  task_id: string;
  stream_url?: string | null;
}

export interface ConsolidationDrawerProps {
  open: boolean;
  onClose: () => void;
  members: string[];
  defaultTarget?: string;
  onCompleted?: () => void;
}

export function ConsolidationDrawer({
  open,
  onClose,
  members,
  defaultTarget,
  onCompleted,
}: ConsolidationDrawerProps) {
  const { message } = App.useApp();
  const [target, setTarget] = useState(defaultTarget ?? "");
  const [dryRun, setDryRun] = useState(true);
  const [dropMembers, setDropMembers] = useState(true);
  const [confirm, setConfirm] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  useEffect(() => {
    if (open && !target && members.length) {
      // Suggest a target name based on the longest common prefix.
      const names = members.map((m) => m.split(".").pop() ?? "");
      const ns = members[0]?.split(".")[0] ?? "aqp";
      const prefix = longestCommonPrefix(names).replace(/[_-]+\d*$/, "");
      const safe = prefix.trim() || "merged";
      setTarget(`${ns}.${safe}`);
    }
    if (!open) {
      setTaskId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, members, defaultTarget]);

  async function submit() {
    if (!target.includes(".")) {
      message.error("target must be 'namespace.name'");
      return;
    }
    if (!dryRun && dropMembers && !confirm) {
      message.error("Tick 'I understand' to drop the member tables");
      return;
    }
    try {
      const res = await apiFetch<TaskAccepted>("/datasets/grouping/consolidate", {
        method: "POST",
        body: JSON.stringify({
          group_name: target,
          members,
          dry_run: dryRun,
          drop_members: dropMembers,
          confirm,
        }),
      });
      setTaskId(res.task_id);
      message.success(`Consolidation queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  useEffect(() => {
    if (stream.done && !stream.error && onCompleted) {
      onCompleted();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.done]);

  const lastEvent = stream.events[stream.events.length - 1];

  return (
    <Drawer
      title={
        <Space>
          <MergeCellsOutlined />
          <span>Consolidate Iceberg tables</span>
        </Space>
      }
      open={open}
      onClose={onClose}
      width={620}
      destroyOnClose
    >
      <Alert
        type={dryRun ? "info" : "warning"}
        showIcon
        icon={dryRun ? <ExperimentOutlined /> : <WarningOutlined />}
        message={
          dryRun
            ? "Dry-run: validates schema compatibility and reports row counts without writing."
            : "Wet run: creates a new table and (optionally) drops the originals."
        }
        style={{ marginBottom: 12 }}
      />
      <Form layout="vertical">
        <Form.Item label="Target identifier">
          <Input
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="aqp.bars_yfinance"
          />
        </Form.Item>
        <Form.Item label={`Members (${members.length})`}>
          <List
            size="small"
            bordered
            dataSource={members}
            renderItem={(m) => (
              <List.Item>
                <code>{m}</code>
              </List.Item>
            )}
            style={{ maxHeight: 220, overflow: "auto" }}
          />
        </Form.Item>
        <Form.Item>
          <Space direction="vertical">
            <Checkbox checked={dryRun} onChange={(e) => setDryRun(e.target.checked)}>
              Dry run (recommended for first pass)
            </Checkbox>
            <Checkbox
              checked={dropMembers}
              onChange={(e) => setDropMembers(e.target.checked)}
              disabled={dryRun}
            >
              Drop member tables after merge
            </Checkbox>
            <Checkbox
              checked={confirm}
              onChange={(e) => setConfirm(e.target.checked)}
              disabled={dryRun || !dropMembers}
            >
              I understand this will drop the original tables.
            </Checkbox>
          </Space>
        </Form.Item>
        <Space>
          <Button type="primary" onClick={submit} disabled={members.length < 2 || !target}>
            {dryRun ? "Run dry-run" : "Run consolidation"}
          </Button>
          <Button onClick={onClose}>Close</Button>
        </Space>
      </Form>

      {taskId ? (
        <div style={{ marginTop: 16 }}>
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="Task">{taskId}</Descriptions.Item>
            <Descriptions.Item label="Stream">
              <Tag color={stream.status === "open" ? "blue" : "default"}>{stream.status}</Tag>
              {stream.done ? (
                <Tag color={stream.error ? "red" : "green"}>
                  {stream.error ? "error" : "done"}
                </Tag>
              ) : null}
            </Descriptions.Item>
            {typeof lastEvent?.percent === "number" ? (
              <Descriptions.Item label="Progress" span={2}>
                {Number(lastEvent.percent).toFixed(1)}%
              </Descriptions.Item>
            ) : null}
            <Descriptions.Item label="Last message" span={2}>
              <Text type="secondary">{String(lastEvent?.message ?? "—")}</Text>
            </Descriptions.Item>
          </Descriptions>
          {stream.error ? (
            <Alert type="error" showIcon style={{ marginTop: 12 }} message={stream.error} />
          ) : null}
          {stream.done && !stream.error ? (
            <Alert
              type="success"
              showIcon
              style={{ marginTop: 12 }}
              message="Consolidation finished — refresh the catalog to see the new table."
            />
          ) : null}
          <Paragraph
            type="secondary"
            style={{
              marginTop: 12,
              fontSize: 11,
              maxHeight: 220,
              overflow: "auto",
              fontFamily: "monospace",
              whiteSpace: "pre",
            }}
          >
            {(stream.events ?? []).map((e) => JSON.stringify(e)).join("\n")}
          </Paragraph>
        </div>
      ) : null}
    </Drawer>
  );
}

function longestCommonPrefix(items: string[]): string {
  if (!items.length) return "";
  let prefix: string = items[0] ?? "";
  for (let i = 1; i < items.length && prefix; i++) {
    const next = items[i] ?? "";
    while (next.indexOf(prefix) !== 0) {
      prefix = prefix.slice(0, prefix.length - 1);
      if (!prefix) return "";
    }
  }
  return prefix;
}
