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

interface CatalogTable {
  iceberg_identifier: string;
  namespace: string;
  name: string;
  description?: string | null;
  domain?: string | null;
  tags?: string[];
  load_mode: string;
  source_uri?: string | null;
  row_count?: number | null;
  file_count?: number | null;
  truncated: boolean;
  has_annotation: boolean;
  catalog_id?: string | null;
  location?: string | null;
  updated_at?: string | null;
}

export function CatalogBrowser() {
  const [selectedNs, setSelectedNs] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const namespaces = useApiQuery<NamespaceList>({
    queryKey: ["datasets", "namespaces"],
    path: "/datasets/namespaces",
    staleTime: 30_000,
  });

  const tables = useApiQuery<CatalogTable[]>({
    queryKey: ["datasets", "tables", selectedNs ?? "__all__"],
    path: "/datasets/tables",
    query: selectedNs ? { namespace: selectedNs } : undefined,
    select: (raw) => (Array.isArray(raw) ? (raw as CatalogTable[]) : []),
    staleTime: 15_000,
  });

  const filtered = useMemo(() => {
    const all = tables.data ?? [];
    const needle = search.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((t) =>
      [t.iceberg_identifier, t.description ?? "", t.domain ?? "", (t.tags ?? []).join(" ")]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [tables.data, search]);

  return (
    <PageContainer
      title="Data Catalog"
      subtitle="Iceberg tables, organized by namespace, with LLM-generated annotations and lineage."
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
              tables.refetch();
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
            dataSource={["__all__", ...((namespaces.data?.namespaces ?? []) as string[])]}
            renderItem={(ns) => {
              const label = ns === "__all__" ? "All namespaces" : ns;
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
          title={selectedNs ? `Tables · ${selectedNs}` : "All tables"}
          loading={tables.isLoading}
        >
          {filtered.length === 0 ? (
            <Empty
              description={
                tables.isLoading
                  ? "Loading…"
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
              {filtered.map((t) => (
                <Link
                  key={t.iceberg_identifier}
                  href={`/data/catalog/${encodeURIComponent(t.namespace)}/${encodeURIComponent(t.name)}`}
                  style={{ textDecoration: "none" }}
                >
                  <Card
                    hoverable
                    size="small"
                    title={
                      <Space>
                        <Text strong>{t.name}</Text>
                        {t.has_annotation ? (
                          <Badge color="cyan" text="annotated" />
                        ) : (
                          <Badge color="default" text="raw" />
                        )}
                      </Space>
                    }
                    extra={<Tag color="geekblue">{t.namespace}</Tag>}
                  >
                    <Paragraph
                      ellipsis={{ rows: 3 }}
                      type={t.description ? undefined : "secondary"}
                      style={{ minHeight: 56, marginBottom: 8 }}
                    >
                      {t.description ?? "No description yet — re-annotate from the detail page."}
                    </Paragraph>
                    <Space size={4} wrap>
                      <Tag>{t.load_mode}</Tag>
                      {t.domain ? <Tag color="purple">{t.domain}</Tag> : null}
                      {t.truncated ? <Tag color="orange">truncated</Tag> : null}
                      {(t.tags ?? []).slice(0, 4).map((tag) => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </Space>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>
    </PageContainer>
  );
}
