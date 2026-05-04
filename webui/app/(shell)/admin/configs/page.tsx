"use client";

import { Button, Card, Col, Input, Row, Select, Space, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import {
  clearConfigLayer,
  getConfigLayer,
  getEffectiveConfig,
  setConfigLayer,
} from "@/lib/api/tenancy";
import { useTenancyStore } from "@/lib/store/tenancy";

const { Title, Text } = Typography;
const { TextArea } = Input;

const SCOPE_OPTIONS = [
  { value: "global", label: "Global (read-only)", readOnly: true },
  { value: "org", label: "Organization" },
  { value: "team", label: "Team" },
  { value: "user", label: "User" },
  { value: "workspace", label: "Workspace" },
  { value: "project", label: "Project" },
  { value: "lab", label: "Lab" },
] as const;

const NAMESPACES = ["llm", "rag", "risk", "agent", "compute", "iceberg", "alpha_vantage"];

export default function ConfigsAdminPage() {
  const tenancy = useTenancyStore();
  const [scope, setScope] = useState<string>("workspace");
  const [scopeId, setScopeId] = useState<string>(tenancy.workspaceId ?? "");
  const [namespace, setNamespace] = useState<string>("llm");
  const [layer, setLayer] = useState<string>("{}");
  const [effective, setEffective] = useState<string>("{}");
  const [status, setStatus] = useState<string | null>(null);

  // Update default scope id when scope changes.
  useEffect(() => {
    const fallback: Record<string, string | null> = {
      org: tenancy.orgId,
      team: tenancy.teamId,
      user: tenancy.userId,
      workspace: tenancy.workspaceId,
      project: tenancy.projectId,
      lab: tenancy.labId,
    };
    setScopeId(fallback[scope] ?? "");
  }, [scope, tenancy.orgId, tenancy.teamId, tenancy.userId, tenancy.workspaceId, tenancy.projectId, tenancy.labId]);

  async function load() {
    setStatus(null);
    try {
      const eff = await getEffectiveConfig(namespace);
      setEffective(JSON.stringify(eff, null, 2));
      if (scope !== "global" && scopeId) {
        const lay = await getConfigLayer(scope, scopeId, namespace);
        setLayer(JSON.stringify(lay, null, 2));
      } else {
        setLayer("{}");
      }
    } catch (e) {
      setStatus(`Load failed: ${(e as Error).message}`);
    }
  }

  async function save() {
    setStatus(null);
    try {
      const payload = JSON.parse(layer);
      const res = await setConfigLayer(scope, scopeId, namespace, payload);
      setStatus(`Saved overlay ${res.overlay_id.slice(0, 8)}`);
      await load();
    } catch (e) {
      setStatus(`Save failed: ${(e as Error).message}`);
    }
  }

  async function clear() {
    setStatus(null);
    try {
      await clearConfigLayer(scope, scopeId, namespace);
      setStatus("Cleared");
      await load();
    } catch (e) {
      setStatus(`Clear failed: ${(e as Error).message}`);
    }
  }

  const isReadOnly = scope === "global";

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Title level={3} style={{ margin: 0 }}>Layered Config</Title>
      <Text type="secondary">
        Resolution order: <Tag>global</Tag> → <Tag>org</Tag> → <Tag>team</Tag> → <Tag>user</Tag> →{" "}
        <Tag>workspace</Tag> → <Tag>project</Tag>. Each layer&apos;s payload is deep-merged into the
        next via vbt-pro&apos;s merge_dicts semantics; later layers win on conflict. Use the literal
        string <Tag>__unset__</Tag> as a value to drop a key at the current layer.
      </Text>

      <Row gutter={16}>
        <Col span={6}>
          <Text strong>Scope</Text>
          <Select
            value={scope}
            onChange={setScope}
            options={SCOPE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            style={{ width: "100%" }}
          />
        </Col>
        <Col span={6}>
          <Text strong>Scope ID</Text>
          <Input
            value={scopeId}
            onChange={(e) => setScopeId(e.target.value)}
            disabled={isReadOnly}
            placeholder="UUID of org/team/user/workspace/project/lab"
          />
        </Col>
        <Col span={6}>
          <Text strong>Namespace</Text>
          <Select
            value={namespace}
            onChange={setNamespace}
            options={NAMESPACES.map((n) => ({ value: n, label: n }))}
            style={{ width: "100%" }}
          />
        </Col>
        <Col span={6} style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
          <Button onClick={load}>Load</Button>
          <Button type="primary" disabled={isReadOnly} onClick={save}>Save</Button>
          <Button danger disabled={isReadOnly} onClick={clear}>Clear</Button>
        </Col>
      </Row>

      {status && <Tag color={status.startsWith("Saved") || status === "Cleared" ? "green" : "red"}>{status}</Tag>}

      <Row gutter={16}>
        <Col span={12}>
          <Card title="Layer payload (this scope)">
            <TextArea
              value={layer}
              onChange={(e) => setLayer(e.target.value)}
              rows={20}
              disabled={isReadOnly}
              spellCheck={false}
              style={{ fontFamily: "monospace" }}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="Effective config (after stack merge)">
            <TextArea
              value={effective}
              rows={20}
              readOnly
              spellCheck={false}
              style={{ fontFamily: "monospace" }}
            />
          </Card>
        </Col>
      </Row>
    </Space>
  );
}
