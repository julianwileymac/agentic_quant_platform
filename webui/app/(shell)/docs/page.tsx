"use client";

import { Card, Col, Row, Space, Typography } from "antd";

import { PageContainer } from "@/components/shell/PageContainer";

const { Title, Text, Paragraph } = Typography;

const links = [
  { href: "http://localhost:8000/docs", label: "FastAPI OpenAPI", desc: "Swagger UI for the live REST surface" },
  { href: "http://localhost:8000/redoc", label: "FastAPI ReDoc", desc: "ReDoc-rendered alternative" },
  { href: process.env.NEXT_PUBLIC_MLFLOW_URL ?? "http://localhost:5000", label: "MLflow", desc: "Experiment tracking + registry" },
  { href: process.env.NEXT_PUBLIC_JAEGER_URL ?? "http://localhost:16686", label: "Jaeger", desc: "Distributed tracing" },
  { href: process.env.NEXT_PUBLIC_DASH_URL ?? "http://localhost:8000/dash/", label: "Dash monitor", desc: "Legacy strategy monitor" },
];

export default function DocsPage() {
  return (
    <PageContainer
      title="Docs"
      subtitle="Quick links to the live developer surfaces."
    >
      <Row gutter={[16, 16]}>
        {links.map((l) => (
          <Col xs={24} md={12} lg={8} key={l.href}>
            <Card hoverable>
              <Space direction="vertical" size={4} style={{ width: "100%" }}>
                <Title level={5} style={{ margin: 0 }}>
                  <a href={l.href} target="_blank" rel="noreferrer">
                    {l.label} ↗
                  </a>
                </Title>
                <Text type="secondary">{l.desc}</Text>
                <Text style={{ fontSize: 11, fontFamily: "monospace", opacity: 0.6 }}>{l.href}</Text>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
      <Card title="Project docs" style={{ marginTop: 16 }}>
        <Paragraph>
          The repository ships canonical docs under <code>docs/</code>. Highlights worth bookmarking:
        </Paragraph>
        <ul>
          <li><code>docs/data-plane.md</code> — sources, identifier graph, FRED/SEC/GDelt</li>
          <li><code>docs/backtest-engines.md</code> — event vs vectorbt vs backtesting.py</li>
          <li><code>docs/ml-framework.md</code> — Qlib-style ML stack</li>
          <li><code>docs/factor-research.md</code> — factor evaluation + Alphalens-style charts</li>
          <li><code>docs/strategy-lifecycle.md</code> — versioned strategies + diff</li>
          <li><code>docs/observability.md</code> — OpenTelemetry wiring</li>
        </ul>
      </Card>
    </PageContainer>
  );
}
