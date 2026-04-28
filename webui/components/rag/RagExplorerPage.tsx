"use client";
import { Button, Card, Col, Form, Input, Row, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { RagApi, type RagCorpusInfo, type RagHierarchy, type RagHit } from "@/lib/api/rag";

const { Title, Paragraph, Text } = Typography;

export function RagExplorerPage() {
  const [corpora, setCorpora] = useState<RagCorpusInfo[]>([]);
  const [hierarchy, setHierarchy] = useState<RagHierarchy | null>(null);
  const [hits, setHits] = useState<RagHit[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    RagApi.corpora().then(setCorpora).catch(() => undefined);
    RagApi.hierarchy().then(setHierarchy).catch(() => undefined);
  }, []);

  const onQuery = async (values: Record<string, unknown>) => {
    setBusy(true);
    try {
      const hits = await RagApi.query({
        query: String(values.query),
        level: String(values.level || "l3"),
        corpus: values.corpus ? String(values.corpus) : undefined,
        order: values.order ? String(values.order) : undefined,
        vt_symbol: values.vt_symbol ? String(values.vt_symbol) : undefined,
        k: Number(values.k || 8),
      });
      setHits(hits);
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(false);
    }
  };

  const onWalk = async (values: Record<string, unknown>) => {
    setBusy(true);
    try {
      const hits = await RagApi.walk({
        query: String(values.query),
        levels: ["l0", "l1", "l2", "l3"],
        orders: ["first", "second", "third"],
        vt_symbol: values.vt_symbol ? String(values.vt_symbol) : undefined,
        per_level_k: 5,
        final_k: Number(values.k || 12),
      });
      setHits(hits);
    } catch (e) {
      message.error(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Title level={2}>Hierarchical RAG Explorer</Title>
        <Paragraph>
          Alpha-GPT four-level retrieval (L0 alpha base → L1 categories →
          L2 sub-categories → L3 chunks) over the three knowledge orders
          (first / second / third). Backed by Redis Stack + RediSearch HNSW.
        </Paragraph>
      </div>

      <Row gutter={16}>
        {(["first", "second", "third"] as const).map((order) => (
          <Col span={8} key={order}>
            <Card title={`${order}-order corpora`}>
              <Space direction="vertical" style={{ width: "100%" }}>
                {corpora
                  .filter((c) => c.order === order)
                  .map((c) => (
                    <div key={c.name}>
                      <Tag>{c.name}</Tag> <Text type="secondary">{c.chunks} chunks</Text>
                      <div style={{ fontSize: 12, color: "#999" }}>{c.description}</div>
                    </div>
                  ))}
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      {hierarchy && (
        <Card title="Hierarchy">
          <Space direction="vertical" style={{ width: "100%" }}>
            {Object.entries(hierarchy.categories).map(([l1, sub]) => (
              <div key={l1}>
                <Text strong>{l1}</Text>
                <Space wrap style={{ marginLeft: 8 }}>
                  {Object.entries(sub).map(([l2, names]) => (
                    <Tag key={l2}>{l2} ({names.length})</Tag>
                  ))}
                </Space>
              </div>
            ))}
          </Space>
        </Card>
      )}

      <Card title="Query">
        <Form layout="inline" onFinish={onQuery} initialValues={{ level: "l3", k: 8 }}>
          <Form.Item label="Query" name="query" rules={[{ required: true }]}>
            <Input style={{ width: 360 }} placeholder="natural-language question" />
          </Form.Item>
          <Form.Item label="Level" name="level">
            <Select style={{ width: 90 }} options={["l0", "l1", "l2", "l3"].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item label="Corpus" name="corpus">
            <Select
              allowClear
              style={{ width: 200 }}
              options={corpora.map((c) => ({ value: c.name, label: c.name }))}
            />
          </Form.Item>
          <Form.Item label="Order" name="order">
            <Select
              allowClear
              style={{ width: 120 }}
              options={["first", "second", "third"].map((v) => ({ value: v, label: v }))}
            />
          </Form.Item>
          <Form.Item label="vt_symbol" name="vt_symbol">
            <Input style={{ width: 140 }} />
          </Form.Item>
          <Form.Item label="k" name="k">
            <Input type="number" style={{ width: 70 }} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button htmlType="submit" type="primary" loading={busy}>
                Query
              </Button>
              <Button onClick={(e) => { e.preventDefault(); onWalk({ query: (document.querySelector('input[id^="query"]') as HTMLInputElement)?.value || "", k: 12 }); }}>
                Walk
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card title={`Hits (${hits.length})`}>
        <Table<RagHit>
          rowKey={(h) => `${h.corpus}:${h.level}:${h.doc_id}`}
          dataSource={hits}
          pagination={false}
          size="small"
          columns={[
            { title: "Score", dataIndex: "score", key: "score", render: (v: number) => v.toFixed(3), width: 80 },
            { title: "Corpus", dataIndex: "corpus", key: "corpus" },
            { title: "Level", dataIndex: "level", key: "level", render: (v) => <Tag>{v}</Tag>, width: 70 },
            { title: "Symbol", dataIndex: "vt_symbol", key: "vt_symbol", width: 90 },
            { title: "As of", dataIndex: "as_of", key: "as_of", width: 120 },
            {
              title: "Text",
              dataIndex: "text",
              key: "text",
              render: (t: string) => <span style={{ fontSize: 12 }}>{t.slice(0, 320)}…</span>,
            },
          ]}
        />
      </Card>
    </Space>
  );
}
