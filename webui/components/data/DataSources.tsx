"use client";

import { App, Alert, Button, Card, Drawer, Form, Input, Space, Switch, Tabs, Tag, Tooltip, Typography } from "antd";
import type { ICellRendererParams } from "ag-grid-community";
import { useState } from "react";

import { DataGrid, StatusBadgeCell } from "@/components/data-grid";
import { PageContainer } from "@/components/shell/PageContainer";
import { SourceSetupWizardModal } from "@/components/data/SourceSetupWizardModal";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { fetchersApi, type FetcherSummary } from "@/lib/api/fetchers";
import { sourcesApi, type ImportProbeResponse } from "@/lib/api/sources";

interface SourceRow {
  id: string;
  name: string;
  display_name: string;
  vendor?: string | null;
  kind: string;
  kind_subtype?: string | null;
  protocol: string;
  enabled: boolean;
  capabilities?: Record<string, unknown>;
  rate_limits?: Record<string, unknown>;
  credentials_ref?: string | null;
  auth_type?: string;
  base_url?: string | null;
  meta?: Record<string, unknown>;
  health_status?: string | null;
  last_probe_at?: string | null;
}

interface SourceLibraryRow {
  id: string;
  source_name: string;
  display_name: string;
  import_uri?: string | null;
  reference_path?: string | null;
  docs_url?: string | null;
  default_node?: string | null;
  tags: string[];
  version: number;
  enabled: boolean;
  updated_at: string;
}

export function DataSources() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState<string>("registry");
  const [editing, setEditing] = useState<SourceRow | null>(null);
  const [saving, setSaving] = useState(false);
  const [wizardSource, setWizardSource] = useState<string | null>(null);
  const [importProbe, setImportProbe] = useState<ImportProbeResponse | null>(null);
  const [probing, setProbing] = useState(false);

  const list = useApiQuery<SourceRow[]>({
    queryKey: ["sources", "list"],
    path: "/sources/",
    select: (raw) => (Array.isArray(raw) ? (raw as SourceRow[]) : []),
  });

  const fetchers = useApiQuery<FetcherSummary[]>({
    queryKey: ["fetchers", "all"],
    path: "/fetchers",
    select: (raw) => (Array.isArray(raw) ? (raw as FetcherSummary[]) : []),
    enabled: activeTab === "fetchers",
  });

  const library = useApiQuery<SourceLibraryRow[]>({
    queryKey: ["sources", "library"],
    path: "/sources/library",
    select: (raw) => (Array.isArray(raw) ? (raw as SourceLibraryRow[]) : []),
    enabled: activeTab === "library",
  });

  async function toggle(row: SourceRow) {
    try {
      await apiFetch(`/sources/${row.name}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !row.enabled }),
      });
      message.success(`${row.display_name}: ${!row.enabled ? "enabled" : "disabled"}`);
      list.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function probe(row: SourceRow) {
    try {
      const res = await apiFetch<{ ok: boolean; message?: string }>(`/sources/${row.name}/probe`);
      if (res.ok) message.success(`${row.display_name}: reachable`);
      else message.warning(`${row.display_name}: ${res.message ?? "unreachable"}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  function openEdit(row: SourceRow) {
    setEditing(row);
    editForm.setFieldsValue({
      display_name: row.display_name,
      vendor: row.vendor,
      kind: row.kind,
      auth_type: row.auth_type,
      base_url: row.base_url,
      protocol: row.protocol,
      credentials_ref: row.credentials_ref,
      tags: Array.isArray(row.meta?.tags) ? (row.meta?.tags as string[]).join(",") : "",
      meta_json: JSON.stringify(row.meta ?? {}, null, 2),
    });
  }

  async function saveEdit() {
    if (!editing) return;
    setSaving(true);
    try {
      const values = await editForm.validateFields();
      await apiFetch(`/sources/${editing.name}`, {
        method: "PUT",
        body: JSON.stringify({
          display_name: values.display_name,
          vendor: values.vendor,
          kind: values.kind,
          auth_type: values.auth_type,
          base_url: values.base_url,
          protocol: values.protocol,
          credentials_ref: values.credentials_ref,
          tags: csv(values.tags),
          meta: parseJson(values.meta_json),
        }),
      });
      message.success(`Saved ${editing.display_name}`);
      setEditing(null);
      list.refetch();
      library.refetch();
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function importSource() {
    setSaving(true);
    try {
      const values = await form.validateFields();
      await apiFetch("/sources/import", {
        method: "POST",
        body: JSON.stringify({
          name: values.name,
          display_name: values.display_name,
          raw_source_url: values.raw_source_url,
          uri: values.uri,
          reference_path: values.reference_path,
          docs_url: values.docs_url,
          vendor: values.vendor,
          kind: values.kind,
          protocol: values.protocol,
          credentials_ref: values.credentials_ref,
          tags: csv(values.tags),
          metadata: parseJson(values.metadata_json),
        }),
      });
      message.success(`Imported ${values.name}`);
      form.resetFields();
      list.refetch();
      library.refetch();
      setActiveTab("registry");
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function probeFetcher(name: string) {
    try {
      const res = await fetchersApi.probe(name, {});
      if (res.ok) message.success(`${name}: probe ok`);
      else message.warning(`${name}: ${res.error ?? "unreachable"}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function probeImportTarget() {
    setProbing(true);
    try {
      const values = form.getFieldsValue([
        "raw_source_url",
        "uri",
        "reference_path",
      ]);
      const result = await sourcesApi.importProbe({
        raw_source_url: values.raw_source_url || undefined,
        uri: values.uri || undefined,
        reference_path: values.reference_path || undefined,
      });
      setImportProbe(result);
      if (result.suggested_default_node && !form.getFieldValue("kind")) {
        form.setFieldsValue({ kind: result.detected_kind });
      }
      message.success(
        `Probed (${result.reachable ? "reachable" : "not reachable"})`,
      );
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setProbing(false);
    }
  }

  return (
    <PageContainer
      title="Sources registry"
      subtitle="All known data adapters: data_sources rows + engine fetcher catalog."
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: "registry",
            label: "Registry",
            children: (
              <DataGrid<SourceRow>
                rowData={list.data ?? []}
                loading={list.isLoading}
                columnDefs={[
                  { field: "display_name", headerName: "Source", flex: 2, minWidth: 200 },
                  { field: "vendor", headerName: "Vendor", width: 140 },
                  {
                    field: "kind",
                    headerName: "Kind",
                    width: 110,
                    cellRenderer: StatusBadgeCell,
                  },
                  {
                    field: "kind_subtype",
                    headerName: "Subtype",
                    width: 110,
                  },
                  { field: "protocol", headerName: "Protocol", width: 110 },
                  {
                    field: "rate_limits",
                    headerName: "Rate",
                    width: 130,
                    valueGetter: (p) => {
                      const rl = (p.data?.rate_limits ?? {}) as Record<string, unknown>;
                      const rpm = rl.requests_per_minute ?? rl.req_per_minute;
                      return rpm ? `${rpm} rpm` : "-";
                    },
                  },
                  {
                    field: "health_status",
                    headerName: "Health",
                    width: 110,
                    cellRenderer: (p: ICellRendererParams<SourceRow>) => {
                      const status = p.value ?? "unknown";
                      const color =
                        status === "ok"
                          ? "green"
                          : status === "error"
                          ? "red"
                          : "default";
                      return (
                        <Tooltip title={p.data?.last_probe_at ?? "no probe yet"}>
                          <Tag color={color}>{String(status)}</Tag>
                        </Tooltip>
                      );
                    },
                  },
                  {
                    field: "enabled",
                    headerName: "Enabled",
                    width: 110,
                    cellRenderer: (p: ICellRendererParams<SourceRow>) => (
                      <Switch
                        size="small"
                        checked={Boolean(p.value)}
                        onChange={() => p.data && toggle(p.data)}
                      />
                    ),
                  },
                  {
                    headerName: "Actions",
                    width: 280,
                    cellRenderer: (p: ICellRendererParams<SourceRow>) => (
                      <Space>
                        <Button size="small" onClick={() => p.data && probe(p.data)}>
                          Probe
                        </Button>
                        <Button size="small" onClick={() => p.data && openEdit(p.data)}>
                          Edit
                        </Button>
                        <Button
                          size="small"
                          onClick={() => p.data && setWizardSource(p.data.name)}
                        >
                          Wizard
                        </Button>
                      </Space>
                    ),
                  },
                ]}
                height="calc(100vh - 280px)"
              />
            ),
          },
          {
            key: "fetchers",
            label: "Fetcher catalog",
            children: (
              <DataGrid<FetcherSummary>
                rowData={fetchers.data ?? []}
                loading={fetchers.isLoading}
                columnDefs={[
                  { field: "name", headerName: "Alias", flex: 1.5, minWidth: 220 },
                  {
                    field: "kind",
                    headerName: "Kind",
                    width: 110,
                    cellRenderer: StatusBadgeCell,
                  },
                  { field: "description", headerName: "Description", flex: 2, minWidth: 240 },
                  {
                    field: "tags",
                    headerName: "Tags",
                    width: 200,
                    valueFormatter: (p) =>
                      Array.isArray(p.value) ? (p.value as string[]).join(", ") : "",
                  },
                  {
                    headerName: "Actions",
                    width: 140,
                    cellRenderer: (p: ICellRendererParams<FetcherSummary>) => (
                      <Button
                        size="small"
                        onClick={() => p.data && probeFetcher(p.data.name)}
                      >
                        Probe
                      </Button>
                    ),
                  },
                ]}
                height="calc(100vh - 280px)"
              />
            ),
          },
          {
            key: "import",
            label: "Import / setup",
            children: (
              <Card size="small" title="Import source metadata">
                <Form form={form} layout="vertical">
                  <Form.Item name="name" label="Source key" rules={[{ required: true }]}>
                    <Input placeholder="my_vendor" />
                  </Form.Item>
                  <Form.Item name="display_name" label="Display name">
                    <Input placeholder="My Vendor Data" />
                  </Form.Item>
                  <Form.Item name="raw_source_url" label="Raw source URL">
                    <Input placeholder="https://example.com/data.csv" />
                  </Form.Item>
                  <Form.Item name="uri" label="URI">
                    <Input placeholder="s3://bucket/path or gs://bucket/path" />
                  </Form.Item>
                  <Form.Item name="reference_path" label="Reference path">
                    <Input placeholder="/data/vendor/reference.csv" />
                  </Form.Item>
                  <Form.Item name="docs_url" label="Documentation URL">
                    <Input placeholder="https://docs.example.com" />
                  </Form.Item>
                  <Space style={{ width: "100%" }} align="start">
                    <Form.Item name="vendor" label="Vendor">
                      <Input />
                    </Form.Item>
                    <Form.Item name="kind" label="Kind">
                      <Input placeholder="rest_api" />
                    </Form.Item>
                    <Form.Item name="protocol" label="Protocol">
                      <Input placeholder="https/json" />
                    </Form.Item>
                    <Form.Item name="credentials_ref" label="Credential ref">
                      <Input placeholder="AQP_VENDOR_API_KEY" />
                    </Form.Item>
                  </Space>
                  <Form.Item name="tags" label="Tags">
                    <Input placeholder="macro, vendor, daily" />
                  </Form.Item>
                  <Form.Item name="metadata_json" label="Metadata JSON">
                    <Input.TextArea autoSize={{ minRows: 5 }} placeholder='{"domain":"market.bars"}' />
                  </Form.Item>
                  <Space>
                    <Button loading={probing} onClick={probeImportTarget}>
                      Probe URL / path
                    </Button>
                    <Button type="primary" loading={saving} onClick={importSource}>
                      Import source
                    </Button>
                  </Space>
                  {importProbe && (
                    <Alert
                      style={{ marginTop: 12 }}
                      type={importProbe.reachable ? "success" : "warning"}
                      showIcon
                      message={
                        <Space direction="vertical" size={2}>
                          <span>
                            <Tag color="blue">{importProbe.detected_kind}</Tag>
                            <Tag color="purple">{importProbe.detected_protocol}</Tag>
                            <Tag>{importProbe.suggested_default_node}</Tag>
                          </span>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {importProbe.message || "Probe complete"}
                          </Typography.Text>
                        </Space>
                      }
                    />
                  )}
                </Form>
              </Card>
            ),
          },
          {
            key: "library",
            label: "Metadata library",
            children: (
              <DataGrid<SourceLibraryRow>
                rowData={library.data ?? []}
                loading={library.isLoading}
                columnDefs={[
                  { field: "display_name", headerName: "Source", flex: 1.5, minWidth: 220 },
                  { field: "source_name", headerName: "Key", width: 160 },
                  { field: "default_node", headerName: "Default node", width: 180 },
                  { field: "version", headerName: "Version", width: 100 },
                  { field: "import_uri", headerName: "Import URI", flex: 2, minWidth: 240 },
                  {
                    field: "tags",
                    headerName: "Tags",
                    width: 220,
                    valueFormatter: (p) =>
                      Array.isArray(p.value) ? (p.value as string[]).join(", ") : "",
                  },
                ]}
                height="calc(100vh - 280px)"
              />
            ),
          },
        ]}
      />
      <Drawer
        title={editing ? `Edit ${editing.display_name}` : "Edit source"}
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        width={560}
        extra={
          <Button type="primary" loading={saving} onClick={saveEdit}>
            Save
          </Button>
        }
      >
        <Typography.Paragraph type="secondary">
          Source edits update the registry and write an immutable metadata version.
        </Typography.Paragraph>
        <Form form={editForm} layout="vertical">
          <Form.Item name="display_name" label="Display name">
            <Input />
          </Form.Item>
          <Form.Item name="vendor" label="Vendor">
            <Input />
          </Form.Item>
          <Form.Item name="kind" label="Kind">
            <Input />
          </Form.Item>
          <Form.Item name="auth_type" label="Auth type">
            <Input />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input />
          </Form.Item>
          <Form.Item name="protocol" label="Protocol">
            <Input />
          </Form.Item>
          <Form.Item name="credentials_ref" label="Credential reference">
            <Input />
          </Form.Item>
          <Form.Item name="tags" label="Tags">
            <Input />
          </Form.Item>
          <Form.Item name="meta_json" label="Metadata JSON">
            <Input.TextArea autoSize={{ minRows: 8 }} />
          </Form.Item>
        </Form>
      </Drawer>
      <SourceSetupWizardModal
        sourceKey={wizardSource}
        open={Boolean(wizardSource)}
        onClose={() => setWizardSource(null)}
        onComplete={() => {
          list.refetch();
          library.refetch();
        }}
      />
    </PageContainer>
  );
}

function csv(value: unknown): string[] {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseJson(value: unknown): Record<string, unknown> {
  const raw = String(value ?? "").trim();
  if (!raw) return {};
  const parsed = JSON.parse(raw);
  return parsed && typeof parsed === "object" && !Array.isArray(parsed)
    ? (parsed as Record<string, unknown>)
    : {};
}
