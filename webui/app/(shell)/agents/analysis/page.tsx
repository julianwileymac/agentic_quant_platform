"use client";
import { Card, Col, Row, Typography } from "antd";
import Link from "next/link";

const { Title, Paragraph } = Typography;

export default function AnalysisHub() {
  return (
    <div>
      <Title level={2}>Analysis Agents</Title>
      <Paragraph>
        Interpret each agent step, each backtest/paper run, and the portfolio
        as a whole. The reflector closes the loop by writing post-outcome
        lessons back into the L0 RAG alpha base.
      </Paragraph>
      <Row gutter={16}>
        {[
          { href: "/agents/analysis/step", title: "Step Analyst", body: "Verdict + improvements for a single agent step" },
          { href: "/agents/analysis/run", title: "Run Analyst", body: "End-to-end interpretation of a backtest run" },
          { href: "/agents/analysis/portfolio", title: "Portfolio Analyst", body: "Aggregate risk + concentration + reg exposure" },
        ].map((c) => (
          <Col span={8} key={c.href}>
            <Link href={c.href}>
              <Card hoverable title={c.title}>
                <Paragraph>{c.body}</Paragraph>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>
    </div>
  );
}
