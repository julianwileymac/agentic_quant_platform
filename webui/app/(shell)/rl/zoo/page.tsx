"use client";

import {
  Card,
  Col,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Paragraph, Text } = Typography;

interface RegistryEntry {
  alias: string;
  module: string;
  source?: string | null;
  category?: string | null;
  tags?: string[];
}

export default function RlZooPage() {
  return (
    <Suspense
      fallback={
        <PageContainer title="RL Agent Zoo">
          <Empty description="Loading..." />
        </PageContainer>
      }
    >
      <RlZooContents />
    </Suspense>
  );
}

function RlZooContents() {
  const searchParams = useSearchParams();
  const sourceFromQuery = searchParams.get("source") ?? "__all__";
  const categoryFromQuery = searchParams.get("category") ?? "__all__";
  const tagFromQuery = searchParams.get("tag") ?? "__all__";
  const [filter, setFilter] = useState("");
  const [source, setSource] = useState<string>(sourceFromQuery);
  const [category, setCategory] = useState<string>(categoryFromQuery);
  const [tag, setTag] = useState<string>(tagFromQuery);

  const catalog = useApiQuery<RegistryEntry[]>({
    queryKey: ["rl-zoo", "catalog"],
    path: "/registry/agent",
    staleTime: 60_000,
    select: (d) => (Array.isArray(d) ? (d as RegistryEntry[]) : []),
  });

  const list = useApiQuery<RegistryEntry[]>({
    queryKey: ["rl-zoo", "list", source, category, tag],
    path: "/registry/agent",
    query: {
      source: source === "__all__" ? undefined : source,
      category: category === "__all__" ? undefined : category,
      tag: tag === "__all__" ? undefined : tag,
    },
    staleTime: 20_000,
    select: (d) => (Array.isArray(d) ? (d as RegistryEntry[]) : []),
  });

  const sourceOptions = useMemo(() => {
    const srcs = new Set<string>();
    for (const e of catalog.data ?? []) {
      if (e.source) srcs.add(e.source);
    }
    return [{ value: "__all__", label: "All sources" }, ...Array.from(srcs).sort().map((s) => ({ value: s, label: s }))];
  }, [catalog.data]);

  const categoryOptions = useMemo(() => {
    const cats = new Set<string>();
    for (const e of catalog.data ?? []) {
      if (source !== "__all__" && e.source !== source) continue;
      if (e.category) cats.add(e.category);
    }
    return [{ value: "__all__", label: "All categories" }, ...Array.from(cats).sort().map((c) => ({ value: c, label: c }))];
  }, [catalog.data, source]);

  const tagOptions = useMemo(() => {
    const tags = new Set<string>();
    for (const e of catalog.data ?? []) {
      if (source !== "__all__" && e.source !== source) continue;
      if (category !== "__all__" && e.category !== category) continue;
      for (const t of e.tags ?? []) {
        if (t.startsWith("source:") || t.startsWith("category:")) continue;
        tags.add(t);
      }
    }
    return [{ value: "__all__", label: "All tags" }, ...Array.from(tags).sort().map((t) => ({ value: t, label: t }))];
  }, [catalog.data, source, category]);

  const filtered = useMemo(
    () =>
      (list.data ?? []).filter(
        (e) =>
          !filter ||
          e.alias.toLowerCase().includes(filter.toLowerCase()) ||
          (e.module ?? "").toLowerCase().includes(filter.toLowerCase()) ||
          (e.category ?? "").toLowerCase().includes(filter.toLowerCase()),
      ),
    [list.data, filter],
  );
  const loading = list.isLoading || catalog.isLoading;

  useEffect(() => {
    setSource(sourceFromQuery);
    setCategory(categoryFromQuery);
    setTag(tagFromQuery);
  }, [sourceFromQuery, categoryFromQuery, tagFromQuery]);

  return (
    <PageContainer title="RL Agent Zoo">
      <Paragraph>
        Reinforcement-learning agents available for training. Pair an agent
        with one of the existing envs (StockTradingEnv, PortfolioAllocationEnv)
        via the RL training UI.
      </Paragraph>

      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="Search by name or module"
          onChange={(e) => setFilter(e.target.value)}
          style={{ width: 320 }}
          allowClear
        />
        <Select
          value={source}
          onChange={(v) => {
            setSource(v);
            setCategory("__all__");
            setTag("__all__");
          }}
          style={{ width: 220 }}
          options={sourceOptions}
        />
        <Select
          value={category}
          onChange={(v) => {
            setCategory(v);
            setTag("__all__");
          }}
          style={{ width: 220 }}
          options={categoryOptions}
        />
        <Select
          value={tag}
          onChange={setTag}
          style={{ width: 220 }}
          options={tagOptions}
        />
      </Space>
      <Paragraph type="secondary" style={{ marginBottom: 12 }}>
        Showing {filtered.length} agents
        {source !== "__all__" ? ` from ${source}` : ""}.
      </Paragraph>

      {loading ? (
        <Empty description="Loading..." />
      ) : filtered.length === 0 ? (
        <Empty description="No RL agents registered" />
      ) : (
        <Row gutter={[16, 16]}>
          {filtered.map((e) => (
            <Col key={e.alias} xs={24} sm={12} md={8}>
              <Card
                title={e.alias}
                extra={e.source ? <Tag color="purple">{e.source}</Tag> : null}
                actions={[
                  <a
                    key="train"
                    href={`/rl?agent=${encodeURIComponent(e.alias)}`}
                  >
                    Train agent
                  </a>,
                  <a
                    key="backtest"
                    href={`/backtest/new?agent=${encodeURIComponent(e.alias)}&source=${encodeURIComponent(e.source ?? "")}`}
                  >
                    Open backtest wizard
                  </a>,
                ]}
              >
                <Paragraph style={{ marginBottom: 8 }}>
                  <Text type="secondary">{e.module}</Text>
                </Paragraph>
                {e.category && <Tag>{e.category}</Tag>}
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </PageContainer>
  );
}
