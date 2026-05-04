"use client";

import { PlusOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Select, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import useSWR, { mutate } from "swr";

import {
  createWorkspace,
  deleteWorkspace,
  listOrgs,
  listWorkspaces,
  type Organization,
  type Workspace,
} from "@/lib/api/tenancy";

const { Title } = Typography;

export default function WorkspacesAdminPage() {
  const { data: orgs = [] } = useSWR<Organization[]>("orgs", listOrgs);
  const { data: workspaces = [], isLoading } = useSWR<Workspace[]>("workspaces", () => listWorkspaces());
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{
    org_id: string;
    slug: string;
    name: string;
    description?: string;
    visibility?: string;
  }>();

  async function handleCreate() {
    const values = await form.validateFields();
    await createWorkspace(values);
    form.resetFields();
    setOpen(false);
    await mutate("workspaces");
  }

  async function handleDelete(id: string) {
    await deleteWorkspace(id);
    await mutate("workspaces");
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Space style={{ justifyContent: "space-between", width: "100%" }}>
        <Title level={3} style={{ margin: 0 }}>Workspaces</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          New workspace
        </Button>
      </Space>

      <Table
        dataSource={workspaces}
        rowKey="id"
        loading={isLoading}
        columns={[
          { title: "Slug", dataIndex: "slug" },
          { title: "Name", dataIndex: "name" },
          {
            title: "Org",
            dataIndex: "org_id",
            render: (id: string) => orgs.find((o) => o.id === id)?.slug ?? id.slice(0, 8),
          },
          {
            title: "Visibility",
            dataIndex: "visibility",
            render: (v: string) => <Tag>{v}</Tag>,
          },
          {
            title: "Archived",
            dataIndex: "archived",
            render: (v: boolean) => (v ? <Tag color="orange">archived</Tag> : <Tag color="green">active</Tag>),
          },
          {
            title: "Actions",
            render: (_: unknown, row: Workspace) => (
              <Button danger size="small" onClick={() => handleDelete(row.id)}>Delete</Button>
            ),
          },
        ]}
      />

      <Modal title="Create workspace" open={open} onCancel={() => setOpen(false)} onOk={handleCreate}>
        <Form form={form} layout="vertical" initialValues={{ visibility: "team" }}>
          <Form.Item label="Organization" name="org_id" rules={[{ required: true }]}>
            <Select options={orgs.map((o) => ({ value: o.id, label: o.name }))} />
          </Form.Item>
          <Form.Item label="Slug" name="slug" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="Name" name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="Description" name="description">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item label="Visibility" name="visibility">
            <Select
              options={[
                { value: "private", label: "Private — explicit members only" },
                { value: "team", label: "Team — listed teams in this org" },
                { value: "org", label: "Org — every member of the parent org" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
