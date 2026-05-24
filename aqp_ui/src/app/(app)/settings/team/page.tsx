"use client";

import { Button, Card, Form, Input, Modal, Select, Table, Tag, message } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Mail, Plus, UserPlus } from "lucide-react";

import { useStepUp, runWithStepUp } from "@/hooks/useStepUp";

interface Member {
  user_id: string;
  email: string;
  role: "viewer" | "editor" | "admin" | "owner";
  joined_at: string;
}

interface Invite {
  id: string;
  email: string;
  role: Member["role"];
  status: "pending" | "accepted" | "revoked";
  created_at: string;
}

export default function TeamSettingsPage() {
  const [inviteOpen, setInviteOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const { isSupported, requestStepUp } = useStepUp();
  const [form] = Form.useForm();

  const members = useQuery<{ members: Member[] }>({
    queryKey: ["org-members"],
    queryFn: async () => {
      const res = await fetch("/api/tenancy/members", { credentials: "include" });
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
  });

  const invites = useQuery<{ invites: Invite[] }>({
    queryKey: ["org-invites"],
    queryFn: async () => {
      const res = await fetch("/api/tenancy/invites", { credentials: "include" });
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
  });

  async function createInvite(values: { email: string; role: Member["role"] }) {
    setSubmitting(true);
    try {
      await runWithStepUp(requestStepUp, isSupported, async () => {
        const res = await fetch("/api/tenancy/invites", {
          method: "POST",
          credentials: "include",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(values),
        });
        if (!res.ok) {
          const err = new Error(`invite failed: ${res.status}`);
          (err as Error & { headers?: Headers }).headers = res.headers;
          throw err;
        }
      });
      message.success(`Invite sent to ${values.email}`);
      setInviteOpen(false);
      form.resetFields();
      invites.refetch();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Invite failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Members"
        extra={
          <Button
            type="primary"
            icon={<UserPlus size={14} />}
            onClick={() => setInviteOpen(true)}
          >
            Invite member
          </Button>
        }
      >
        <Table
          rowKey="user_id"
          loading={members.isLoading}
          dataSource={members.data?.members ?? []}
          columns={[
            { title: "Email", dataIndex: "email" },
            {
              title: "Role",
              dataIndex: "role",
              render: (role: Member["role"]) => <Tag>{role}</Tag>,
            },
            { title: "Joined", dataIndex: "joined_at" },
          ]}
          pagination={false}
        />
      </Card>

      <Card title="Pending invites">
        <Table
          rowKey="id"
          loading={invites.isLoading}
          dataSource={invites.data?.invites ?? []}
          columns={[
            {
              title: "Email",
              dataIndex: "email",
              render: (email: string) => (
                <span className="flex items-center gap-2">
                  <Mail size={14} /> {email}
                </span>
              ),
            },
            {
              title: "Role",
              dataIndex: "role",
              render: (role: Member["role"]) => <Tag>{role}</Tag>,
            },
            { title: "Status", dataIndex: "status" },
            { title: "Sent", dataIndex: "created_at" },
          ]}
          pagination={false}
        />
      </Card>

      <Card title="Microsoft Entra tenant link">
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Connect your organization's Microsoft Entra ID tenant for SSO. AQP
          super-admin approval is required (AGENTS rule 44 — we never
          auto-provision from a raw <code>tid</code> claim).
        </p>
        <Button
          icon={<Plus size={14} />}
          style={{ marginTop: 12 }}
          onClick={() => {
            window.location.href = "/api/auth/entra/login?returnTo=/settings/team";
          }}
        >
          Request tenant link
        </Button>
      </Card>

      <Modal
        title="Invite member"
        open={inviteOpen}
        onCancel={() => setInviteOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={submitting}
        okText="Send invite"
      >
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={createInvite}
          initialValues={{ role: "viewer" }}
        >
          <Form.Item
            label="Email"
            name="email"
            rules={[
              { required: true, message: "Email is required" },
              { type: "email", message: "Enter a valid email" },
            ]}
          >
            <Input placeholder="quant@example.com" autoFocus />
          </Form.Item>
          <Form.Item label="Role" name="role" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "viewer", label: "Viewer (read-only)" },
                { value: "editor", label: "Editor" },
                { value: "admin", label: "Admin" },
                { value: "owner", label: "Owner" },
              ]}
            />
          </Form.Item>
          <div className="rounded border p-3 text-xs" style={{ borderColor: "var(--border-default)", color: "var(--text-muted)" }}>
            This action requires step-up MFA. You may be prompted to re-authenticate.
          </div>
        </Form>
      </Modal>
    </div>
  );
}
