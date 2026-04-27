"use client";

import {
  DeleteOutlined,
  EditOutlined,
  MergeCellsOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import Link from "next/link";
import { useMemo, useState } from "react";

import { ConsolidationDrawer } from "@/components/data/ConsolidationDrawer";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface CatalogTable {
  iceberg_identifier: string;
  namespace: string;
  name: string;
  description?: string | null;
  domain?: string | null;
  tags?: string[];
  load_mode: string;
  row_count?: number | null;
  file_count?: number | null;
  has_annotation: boolean;
  updated_at?: string | null;
}

interface PatchPayload {
  description?: string | null;
  tags?: string[] | null;
  domain?: string | null;
}

export function IcebergEditor() {
  const { message, modal } = App.useApp();

  const tables = useApiQuery<CatalogTable[]>({
    queryKey: ["datasets", "tables", "iceberg-editor"],
    path: "/datasets/tables",
    staleTime: 15_000,
    select: (raw) => (Array.isArray(raw) ? (raw as CatalogTable[]) : []),
  });

  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<CatalogTable | null>(null);
  const [editDraft, setEditDraft] = useState<{ description: string; domain: string; tags: string }>({
    description: "",
    domain: "",
    tags: "",
  });
  const [consolidateOpen, setConsolidateOpen] = useState(false);

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

  function openEditor(table: CatalogTable) {
    setEditing(table);
    setEditDraft({
      description: table.description ?? "",
      domain: table.domain ?? "",
      tags: (table.tags ?? []).join(", "),
    });
  }

  async function saveEdit() {
    if (!editing) return;
    const body: PatchPayload = {
      description: editDraft.description,
      domain: editDraft.domain || null,
      tags: editDraft.tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      await apiFetch(
        `/datasets/${encodeURIComponent(editing.namespace)}/${encodeURIComponent(editing.name)}`,
        { method: "PATCH", body: JSON.stringify(body) },
      );
      message.success(`Updated ${editing.iceberg_identifier}`);
      setEditing(null);
      tables.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  function dropTable(table: CatalogTable) {
    modal.confirm({
      title: `Drop ${table.iceberg_identifier}?`,
      content: "This deletes the Iceberg table and its DatasetCatalog row.",
      okType: "danger",
      okText: "Drop",
      onOk: async () => {
        try {
          await apiFetch(
            `/datasets/${encodeURIComponent(table.namespace)}/${encodeURIComponent(table.name)}`,
            { method: "DELETE" },
          );
          message.success(`Dropped ${table.iceberg_identifier}`);
          tables.refetch();
          setSelected((prev) => prev.filter((id) => id !== table.iceberg_identifier));
        } catch (err) {
          message.error((err as Error).message);
        }
      },
    });
  }

  return (
    <PageContainer
      title="Iceberg Editor"
      subtitle="Edit metadata, group, and physically consolidate Iceberg tables."
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
          <Link href="/data/iceberg/consolidate">
            <Button>Auto-suggest groups</Button>
          </Link>
          <Button icon={<ReloadOutlined />} onClick={() => tables.refetch()}>
            Refresh
          </Button>
        </Space>
      }
    >
      {tables.error ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message="Iceberg catalog unreachable"
          description={(tables.error as Error).message}
        />
      ) : null}
      <Card
        size="small"
        title={
          <Space>
            <span>Tables ({filtered.length})</span>
            {selected.length ? (
              <Tag color="blue">{selected.length} selected</Tag>
            ) : null}
          </Space>
        }
        extra={
          <Space>
            <Button
              type="primary"
              icon={<MergeCellsOutlined />}
              disabled={selected.length < 2}
              onClick={() => setConsolidateOpen(true)}
            >
              Consolidate selected
            </Button>
            <Button onClick={() => setSelected([])} disabled={selected.length === 0}>
              Clear
            </Button>
          </Space>
        }
      >
        {filtered.length === 0 ? (
          <Empty description="No Iceberg tables found" />
        ) : (
          <Table<CatalogTable>
            size="small"
            rowKey="iceberg_identifier"
            dataSource={filtered}
            pagination={{ pageSize: 25 }}
            rowSelection={{
              selectedRowKeys: selected,
              onChange: (keys) => setSelected(keys.map(String)),
            }}
            columns={[
              {
                title: "Identifier",
                dataIndex: "iceberg_identifier",
                key: "iceberg_identifier",
                render: (v: string) => <code>{v}</code>,
                sorter: (a, b) => a.iceberg_identifier.localeCompare(b.iceberg_identifier),
              },
              {
                title: "Domain",
                dataIndex: "domain",
                key: "domain",
                render: (v: string | null | undefined) => v ?? <Text type="secondary">—</Text>,
              },
              {
                title: "Tags",
                dataIndex: "tags",
                key: "tags",
                render: (tags: string[] | undefined) => (
                  <Space wrap size={4}>
                    {(tags ?? []).slice(0, 5).map((t) => (
                      <Tag key={t}>{t}</Tag>
                    ))}
                  </Space>
                ),
              },
              {
                title: "Rows",
                dataIndex: "row_count",
                key: "row_count",
                render: (v: number | null | undefined) =>
                  v == null ? "—" : v.toLocaleString(),
                sorter: (a, b) => (a.row_count ?? 0) - (b.row_count ?? 0),
              },
              {
                title: "Files",
                dataIndex: "file_count",
                key: "file_count",
                render: (v: number | null | undefined) => (v == null ? "—" : v),
              },
              {
                title: "Description",
                dataIndex: "description",
                key: "description",
                ellipsis: true,
                render: (v: string | null | undefined) =>
                  v ? <Text>{v}</Text> : <Text type="secondary">—</Text>,
              },
              {
                title: "Actions",
                key: "actions",
                width: 140,
                render: (_v, row) => (
                  <Space>
                    <Button size="small" icon={<EditOutlined />} onClick={() => openEditor(row)}>
                      Edit
                    </Button>
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => dropTable(row)}
                    />
                  </Space>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Drawer
        title={editing ? `Edit ${editing.iceberg_identifier}` : "Edit table"}
        open={!!editing}
        onClose={() => setEditing(null)}
        width={520}
        extra={
          <Space>
            <Button onClick={() => setEditing(null)}>Cancel</Button>
            <Button type="primary" onClick={saveEdit}>
              Save
            </Button>
          </Space>
        }
      >
        {editing ? (
          <Form layout="vertical">
            <Form.Item label="Description">
              <Input.TextArea
                rows={5}
                value={editDraft.description}
                onChange={(e) =>
                  setEditDraft((p) => ({ ...p, description: e.target.value }))
                }
                placeholder="Describe what this table contains, lineage, caveats…"
              />
            </Form.Item>
            <Form.Item label="Domain" tooltip="Logical grouping such as 'fundamentals' or 'news'.">
              <Input
                value={editDraft.domain}
                onChange={(e) => setEditDraft((p) => ({ ...p, domain: e.target.value }))}
                placeholder="bars / fundamentals / sentiment"
              />
            </Form.Item>
            <Form.Item label="Tags (comma-separated)">
              <Input
                value={editDraft.tags}
                onChange={(e) => setEditDraft((p) => ({ ...p, tags: e.target.value }))}
                placeholder="quarterly, alpha-vantage"
              />
            </Form.Item>
          </Form>
        ) : null}
      </Drawer>

      <ConsolidationDrawer
        open={consolidateOpen}
        onClose={() => setConsolidateOpen(false)}
        members={selected}
        onCompleted={() => {
          tables.refetch();
          setSelected([]);
        }}
      />
    </PageContainer>
  );
}
