"use client";

import { ArrowLeftOutlined, DeleteOutlined } from "@ant-design/icons";
import { App, Button, Card, Col, List, Row, Space, Statistic, Tag, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";

import { OhlcChart, type OhlcBar } from "@/components/charts";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { usePageContextStore } from "@/lib/store/page-context";

const { Text } = Typography;

interface BarsResponse {
  bars?: Array<{
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number | null;
  }>;
}

interface StatsResponse {
  count?: number;
  start?: string;
  end?: string;
  last_close?: number | null;
  return_total?: number | null;
  vol_annualized?: number | null;
}

interface CacheScopeRow {
  scope: string;
  key: string;
  cached: boolean;
  ttl_seconds: number;
}

interface CacheInfoResponse {
  ticker: string;
  available: boolean;
  scopes: CacheScopeRow[];
}

export function DataSymbolBrowser({ vtSymbol }: { vtSymbol: string }) {
  const router = useRouter();
  const { message } = App.useApp();
  const setContext = usePageContextStore((s) => s.setContext);

  useEffect(() => {
    setContext({ page: "/data/browser", vt_symbol: vtSymbol });
    return () => setContext({ vt_symbol: undefined });
  }, [vtSymbol, setContext]);

  const bars = useApiQuery<BarsResponse>({
    queryKey: ["data", "bars", vtSymbol],
    path: `/data/${encodeURIComponent(vtSymbol)}/bars`,
  });
  const stats = useApiQuery<StatsResponse>({
    queryKey: ["data", "stats", vtSymbol],
    path: `/data/${encodeURIComponent(vtSymbol)}/stats`,
  });
  const cache = useApiQuery<CacheInfoResponse>({
    queryKey: ["data", "cache", vtSymbol],
    path: `/data/security/${encodeURIComponent(vtSymbol)}/cache/info`,
    refetchInterval: 30_000,
  });

  async function flushCache() {
    try {
      await apiFetch(`/data/security/${encodeURIComponent(vtSymbol)}/cache`, {
        method: "DELETE",
      });
      message.success("Cache flushed");
      cache.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  const ohlc: OhlcBar[] = useMemo(
    () =>
      (bars.data?.bars ?? []).map((b) => ({
        timestamp: b.timestamp,
        open: Number(b.open),
        high: Number(b.high),
        low: Number(b.low),
        close: Number(b.close),
        volume: b.volume ?? null,
      })),
    [bars.data],
  );

  return (
    <PageContainer
      title={
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => router.push("/data/browser")} />
          {vtSymbol}
          <Tag color="blue">bars</Tag>
        </Space>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={18}>
          <Card title="OHLC" size="small">
            {ohlc.length ? <OhlcChart data={ohlc} height={420} /> : <Text type="secondary">No bars on disk yet.</Text>}
          </Card>
        </Col>
        <Col xs={24} lg={6}>
          <Card title="Stats" size="small">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Statistic title="Bars" value={stats.data?.count ?? "—"} />
              <Statistic
                title="Last close"
                value={stats.data?.last_close ?? "—"}
                precision={2}
              />
              <Statistic
                title="Total return"
                value={stats.data?.return_total != null ? stats.data.return_total * 100 : 0}
                precision={2}
                suffix="%"
              />
              <Statistic
                title="Vol (annualized)"
                value={stats.data?.vol_annualized != null ? stats.data.vol_annualized * 100 : 0}
                precision={2}
                suffix="%"
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {stats.data?.start ? `From ${stats.data.start}` : null}{" "}
                {stats.data?.end ? `→ ${stats.data.end}` : null}
              </Text>
            </Space>
          </Card>
          <Card
            title="Cached details"
            size="small"
            style={{ marginTop: 16 }}
            extra={
              <Button size="small" icon={<DeleteOutlined />} onClick={flushCache} danger>
                Flush
              </Button>
            }
          >
            {cache.data?.available === false ? (
              <Text type="secondary">Redis cache unreachable.</Text>
            ) : (
              <List
                size="small"
                dataSource={cache.data?.scopes ?? []}
                locale={{ emptyText: "No cached records" }}
                renderItem={(item) => (
                  <List.Item style={{ padding: "4px 0" }}>
                    <Space size={6}>
                      <Tag color={item.cached ? "green" : "default"}>
                        {item.scope}
                      </Tag>
                      <Text style={{ fontSize: 11 }}>{item.key}</Text>
                      {item.cached ? (
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          ttl {item.ttl_seconds}s
                        </Text>
                      ) : null}
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
