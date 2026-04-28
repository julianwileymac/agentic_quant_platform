"use client";
import { Button, Card, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { RagApi, type RagCorpusInfo } from "@/lib/api/rag";

const { Title, Paragraph } = Typography;

export function RagAdminPage() {
  const [corpora, setCorpora] = useState<RagCorpusInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    RagApi.corpora().then(setCorpora).catch(() => undefined);
  }, []);

  const refresh = () => RagApi.corpora().then(setCorpora);

  const onIndex = async (corpus: string) => {
    setBusy(corpus);
    try {
      const r = await RagApi.indexCorpus(corpus);
      message.success(`queued task ${r.task_id}`);
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(null);
      setTimeout(refresh, 1000);
    }
  };

  const onRaptor = async (corpus: string) => {
    setBusy(corpus);
    try {
      const r = await RagApi.raptor(corpus);
      message.success(`queued raptor task ${r.task_id}`);
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Title level={2}>RAG Admin</Title>
        <Paragraph>
          Trigger per-corpus indexing, refresh the L0 alpha base, or build
          RAPTOR summary trees. All operations queue Celery tasks routed
          to the <code>rag</code> queue.
        </Paragraph>
      </div>

      <Card>
        <Space>
          <Button
            type="primary"
            onClick={async () => {
              try {
                const r = await RagApi.refreshL0();
                message.success(`refresh-l0 task ${r.task_id}`);
              } catch (e) {
                message.error(String(e));
              }
            }}
          >
            Refresh L0 alpha base
          </Button>
          <Button
            onClick={async () => {
              try {
                const r = await RagApi.refreshHierarchy();
                message.success(`refresh-hierarchy task ${r.task_id}`);
              } catch (e) {
                message.error(String(e));
              }
            }}
          >
            Refresh entire hierarchy
          </Button>
        </Space>
      </Card>

      <Card title="Corpora">
        <Table<RagCorpusInfo>
          rowKey="name"
          dataSource={corpora}
          pagination={{ pageSize: 25 }}
          columns={[
            { title: "Name", dataIndex: "name", key: "name" },
            { title: "Order", dataIndex: "order", key: "order", render: (v) => <Tag>{v}</Tag> },
            { title: "L1", dataIndex: "l1", key: "l1" },
            { title: "L2", dataIndex: "l2", key: "l2" },
            { title: "Iceberg", dataIndex: "iceberg", key: "iceberg", render: (v) => v || "-" },
            { title: "Chunks", dataIndex: "chunks", key: "chunks", align: "right" },
            {
              title: "Actions",
              key: "actions",
              render: (_: unknown, c) => (
                <Space>
                  <Button size="small" loading={busy === c.name} onClick={() => onIndex(c.name)}>
                    Index
                  </Button>
                  <Button size="small" onClick={() => onRaptor(c.name)}>RAPTOR</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
