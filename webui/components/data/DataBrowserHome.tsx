"use client";

import { Button, Card, Input, Space, Tag, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface UniverseEntry {
  ticker?: string;
  vt_symbol?: string;
  name?: string;
}

export function DataBrowserHome() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const universe = useApiQuery<{ items?: UniverseEntry[]; source?: string }>({
    queryKey: ["data", "universe", q || ""],
    path: "/data/universe",
    query: { limit: 100, query: q || undefined },
  });

  const items = universe.data?.items ?? [];

  return (
    <PageContainer
      title="Data Browser"
      subtitle="Pick a symbol to inspect bars, indicators, fundamentals, and news."
      extra={
        <Input.Search
          allowClear
          placeholder="Filter symbols"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ width: 280 }}
        />
      }
    >
      <Card>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
          {items.length === 0 ? (
            <Text type="secondary">No symbols matched.</Text>
          ) : (
            items.map((it) => {
              const ticker = it.ticker ?? it.vt_symbol?.split(".")[0] ?? "";
              const vt = it.vt_symbol ?? `${ticker}.SMART`;
              return (
                <Button
                  key={vt}
                  block
                  onClick={() => router.push(`/data/browser/${encodeURIComponent(vt)}`)}
                  style={{ height: 56, textAlign: "left" }}
                >
                  <Space direction="vertical" size={0} style={{ width: "100%" }}>
                    <Text strong>{ticker}</Text>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {vt}
                    </Text>
                  </Space>
                </Button>
              );
            })
          )}
        </div>
        {universe.data?.source ? (
          <div style={{ marginTop: 12 }}>
            <Tag>source: {universe.data.source}</Tag>
          </div>
        ) : null}
      </Card>
    </PageContainer>
  );
}
