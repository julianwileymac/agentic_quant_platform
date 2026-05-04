"use client";

import { Button, Card, Input, Select, Space, Tag, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface UniverseEntry {
  ticker?: string;
  vt_symbol?: string;
  name?: string;
}

interface UniverseResponse {
  items?: UniverseEntry[];
  source?: string;
  total?: number;
  next_offset?: number | null;
  has_more?: boolean;
}

export function DataBrowserHome() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [source, setSource] = useState("lake");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<UniverseEntry[]>([]);
  const universe = useApiQuery<UniverseResponse>({
    queryKey: ["data", "universe", q || "", source, offset],
    path: "/data/universe",
    query: { limit: 250, offset, query: q || undefined, source },
  });

  useEffect(() => {
    const next = universe.data?.items ?? [];
    setItems((previous) => {
      const merged = offset === 0 ? next : [...previous, ...next];
      const bySymbol = new Map<string, UniverseEntry>();
      for (const item of merged) {
        const key = item.vt_symbol ?? item.ticker;
        if (key) bySymbol.set(key, item);
      }
      return Array.from(bySymbol.values());
    });
  }, [universe.data, offset]);

  useEffect(() => {
    setOffset(0);
    setItems([]);
  }, [q, source]);

  return (
    <PageContainer
      title="Data Browser"
      subtitle="Pick a symbol to inspect bars, indicators, fundamentals, and news."
      extra={
        <Space>
          <Select
            value={source}
            onChange={setSource}
            style={{ width: 180 }}
            options={[
              { value: "lake", label: "Parquet lake (on disk)" },
              { value: "managed_snapshot", label: "Managed snapshot" },
              { value: "alpha_vantage", label: "AlphaVantage live" },
              { value: "catalog", label: "Data catalog" },
              { value: "config", label: "Config fallback" },
            ]}
          />
          <Input.Search
            allowClear
            placeholder="Filter symbols"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ width: 280 }}
          />
        </Space>
      }
    >
      <Card>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
          {items.length === 0 ? (
            <Text type="secondary">
              No symbols matched.
              {source === "lake"
                ? " Ensure bars exist under AQP_PARQUET_DIR/bars, or switch source to Managed snapshot / Data catalog."
                : null}
            </Text>
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
            <Tag>
              {items.length} of {universe.data.total ?? "?"} loaded
            </Tag>
            {universe.data.has_more ? (
              <Button
                size="small"
                onClick={() => setOffset(universe.data?.next_offset ?? items.length)}
                loading={universe.isFetching}
              >
                Load more
              </Button>
            ) : null}
          </div>
        ) : null}
      </Card>
    </PageContainer>
  );
}
