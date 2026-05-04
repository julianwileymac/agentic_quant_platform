"use client";

import { Col, Row } from "antd";

import { ProducerCard } from "@/components/streaming/ProducerCard";
import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import { type ProducerSummary } from "@/lib/api/streaming";

export default function ProducersPage() {
  const list = useApiQuery<ProducerSummary[]>({
    queryKey: ["producers", "list"],
    path: "/streaming/producers",
  });

  return (
    <PageContainer
      title="Producers"
      subtitle="Lightweight market-data producers (Alpha-Vantage, IBKR, Alpaca, polygon, custom)."
    >
      <Row gutter={[16, 16]}>
        {(list.data ?? []).map((row) => (
          <Col key={row.id} xs={24} sm={12} md={8}>
            <ProducerCard row={row} onChange={() => list.refetch()} />
          </Col>
        ))}
      </Row>
    </PageContainer>
  );
}
