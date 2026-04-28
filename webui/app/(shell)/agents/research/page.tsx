"use client";
import { Card, Col, Row, Typography } from "antd";
import Link from "next/link";

const { Title, Paragraph } = Typography;

export default function ResearchAgentsHub() {
  return (
    <div>
      <Title level={2}>Research Agents</Title>
      <Paragraph>
        News mining, equity research, and interactive universe selection — each
        backed by the hierarchical Redis RAG (L1 news_sentiment + L2 disclosures
        + L3 regulatory).
      </Paragraph>
      <Row gutter={16}>
        {[
          { href: "/agents/research/news", title: "News Miner", body: "Recent news + sentiment + regulatory flags" },
          { href: "/agents/research/equity", title: "Equity Researcher", body: "Long-form research note with RAG citations" },
          { href: "/agents/research/universe", title: "Universe Selector", body: "Interactive universe shaping with justification" },
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
