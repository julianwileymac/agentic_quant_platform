"use client";

import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { Alert, Badge, Button, Card, Empty, Input, List, Space, Tag, Typography } from "antd";
import Link from "next/link";
import { useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Text, Paragraph } = Typography;

interface NamespaceList {
  namespaces?: string[];
}

interface CatalogCardItem {
  id: string;
  name: string;
  namespace?: string | null;
  table?: string | null;
  description?: string | null;
  domain?: string | null;
  tags: string[];
  load_mode: string;
  iceberg_identifier?: string | null;
  row_count?: number | null;
  latest_row_count?: number | null;
  updated_at?: string | null;
  href?: string;
  has_annotation?: boolean;
  truncated?: boolean;
  entry_kind?: "dataset" | "instrument";
  vt_symbol?: string | null;
  ticker?: string | null;
  exchange?: string | null;
}

const REGISTERED_NS = "__registered__";
const UNIVERSE_NS = "__universe__";

export function CatalogBrowser() {
  const [selectedNs, setSelectedNs] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const namespaces = useApiQuery<NamespaceList>({
    queryKey: ["datasets", "namespaces"],
    path: "/datasets/namespaces",
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: "always",
  });

  const datasets = useApiQuery<CatalogCardItem[]>({
    queryKey: ["metadata", "catalog", "datasets", selectedNs ?? "__all__"],
    path: "/metadata/catalog/datasets",
    query: {
      limit: 1000,
      ...(selectedNs ? { namespace: selectedNs } : {}),
    },
    select: (raw) => (Array.isArray(raw) ? (raw as CatalogCardItem[]) : []),
    staleTime: 15_000,
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: "always",
  });

  const catalogItems = useMemo<CatalogCardItem[]>(() => {
    return (datasets.data ?? []).map((row) => {
      const icebergHref =
        row.iceberg_identifier && row.namespace && row.table
          ? `/data/catalog/${encodeURIComponent(row.namespace)}/${encodeURIComponent(row.table)}`
          : undefined;
      const registeredHref = row.id
        ? `/data/catalog/dataset/${encodeURIComponent(row.id)}`
        : undefined;
      const instrumentHref =
        row.entry_kind === "instrument" && row.vt_symbol
          ? `/data/catalog/instrument?vt=${encodeURIComponent(row.vt_symbol)}`
          : undefined;
      return {
        ...row,
        namespace: row.namespace ?? "registered",
        tags: row.tags ?? [],
        row_count: row.latest_row_count ?? row.row_count,
        href: instrumentHref ?? icebergHref ?? registeredHref,
      };
    });
  }, [datasets.data]);

  const filtered = useMemo(() => {
    const all = catalogItems;
    const needle = search.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((t) =>
      [
        t.id,
        t.name,
        t.namespace,
        t.description ?? "",
        t.domain ?? "",
        t.vt_symbol ?? "",
        t.ticker ?? "",
        (t.tags ?? []).join(" "),
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [catalogItems, search]);

  return (
    <PageContainer
      title="Data Catalog"
      subtitle="Iceberg tables, registered datasets, and stock universe (instruments) — auto-refreshes every 10s."
      extra={
        <Space>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="Search tables, tags, descriptions"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 320 }}
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              datasets.refetch();
              namespaces.refetch();
            }}
          >
            Refresh
          </Button>
        </Space>
      }
    >
      {namespaces.error ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message="Iceberg catalog unreachable"
          description={(namespaces.error as Error).message}
        />
      ) : null}
      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 16, height: "100%" }}>
        <Card size="small" title="Namespaces" styles={{ body: { padding: 0 } }}>
          <List
            size="small"
            dataSource={[
              "__all__",
              ...((namespaces.data?.namespaces ?? []) as string[]),
              REGISTERED_NS,
              UNIVERSE_NS,
            ]}
            renderItem={(ns) => {
              const label =
                ns === "__all__"
                  ? "All namespaces"
                  : ns === REGISTERED_NS
                    ? "Registered datasets"
                    : ns === UNIVERSE_NS
                      ? "Stock universe"
                      : ns;
              const active = selectedNs === (ns === "__all__" ? null : ns);
              return (
                <List.Item
                  onClick={() => setSelectedNs(ns === "__all__" ? null : ns)}
                  style={{
                    cursor: "pointer",
                    paddingLeft: 16,
                    background: active ? "rgba(22, 119, 255, 0.08)" : undefined,
                  }}
                >
                  <Text strong={active}>{label}</Text>
                </List.Item>
              );
            }}
          />
        </Card>

        <Card
          size="small"
          title={
            selectedNs === REGISTERED_NS
              ? "Registered datasets"
              : selectedNs === UNIVERSE_NS
                ? "Stock universe (instruments)"
                : selectedNs
                  ? `Tables · ${selectedNs}`
                  : "All datasets"
          }
          loading={datasets.isLoading}
        >
          {filtered.length === 0 ? (
            <Empty
              description={
                datasets.isLoading
                  ? "Loading…"
                  : selectedNs === UNIVERSE_NS
                    ? "No instruments in the security master yet. Sync the Alpha Vantage universe from settings or the Alpha Vantage admin."
                    : "No tables yet. Use the Data Ingest wizard to materialize your first dataset."
              }
            />
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                gap: 12,
              }}
            >
              {filtered.map((t) => {
                const card = (
                  <Card
                    hoverable={Boolean(t.href)}
                    size="small"
                    title={
                      <Space>
                        <Text strong>{t.name}</Text>
                        {t.entry_kind === "instrument" ? (
                          <Badge color="gold" text="instrument" />
                        ) : t.has_annotation ? (
                          <Badge color="cyan" text="annotated" />
                        ) : (
                          <Badge color="default" text="raw" />
                        )}
                      </Space>
                    }
                    extra={
                      <Tag color={t.entry_kind === "instrument" ? "orange" : "geekblue"}>
                        {t.entry_kind === "instrument"
                          ? t.exchange || t.namespace || "—"
                          : t.namespace}
                      </Tag>
                    }
                  >
                    <Paragraph
                      ellipsis={{ rows: 3 }}
                      type={t.description ? undefined : "secondary"}
                      style={{ minHeight: 56, marginBottom: 8 }}
                    >
                      {t.description ?? "No description yet."}
                    </Paragraph>
                    <Space size={4} wrap>
                      <Tag>{t.load_mode}</Tag>
                      {t.domain ? <Tag color="purple">{t.domain}</Tag> : null}
                      {t.truncated ? <Tag color="orange">truncated</Tag> : null}
                      {t.row_count != null ? <Tag>{t.row_count.toLocaleString()} rows</Tag> : null}
                      {(t.tags ?? []).slice(0, 4).map((tag) => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </Space>
                  </Card>
                );
                return t.href ? (
                  <Link key={t.id} href={t.href} style={{ textDecoration: "none" }}>
                    {card}
                  </Link>
                ) : (
                  <div key={t.id}>{card}</div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </PageContainer>
  );
}
