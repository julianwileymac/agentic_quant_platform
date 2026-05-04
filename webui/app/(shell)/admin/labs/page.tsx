"use client";

import { PlusOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Select, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import useSWR, { mutate } from "swr";

import {
  createLab,
  deleteLab,
  listLabs,
  listWorkspaces,
  type Lab,
  type Workspace,
} from "@/lib/api/tenancy";

const { Title } = Typography;

export default function LabsAdminPage() {
  const { data: workspaces = [] } = useSWR<Workspace[]>("workspaces", () => listWorkspaces());
  const { data: labs = [], isLoading } = useSWR<Lab[]>("labs", () => listLabs());
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{
    workspace_id: string;
    slug: string;
    name: string;
    description?: string;
    kernel_image?: string;
  }>();

  async function handleCreate() {
    const values = await form.validateFields();
    await createLab(values);
    form.resetFields();
    setOpen(false);
    await mutate("labs");
  }

  async function handleDelete(id: string) {
    await deleteLab(id);
    await mutate("labs");
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Space style={{ justifyContent: "space-between", width: "100%" }}>
        <Title level={3} style={{ margin: 0 }}>Labs</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          New lab
        </Button>
      </Space>

      <Table
        dataSource={labs}
        rowKey="id"
        loading={isLoading}
        columns={[
          { title: "Slug", dataIndex: "slug" },
          { title: "Name", dataIndex: "name" },
          {
            title: "Workspace",
            dataIndex: "workspace_id",
            render: (id: string) => workspaces.find((w) => w.id === id)?.slug ?? id.slice(0, 8),
          },
          { title: "Kernel image", dataIndex: "kernel_image" },
          {
            title: "Last active",
            dataIndex: "last_active_at",
            render: (s: string | null) => (s ? new Date(s).toLocaleString() : "—"),
          },
          {
            title: "Archived",
            dataIndex: "archived",
            render: (v: boolean) => (v ? <Tag color="orange">archived</Tag> : <Tag color="green">active</Tag>),
          },
          {
            title: "Actions",
            render: (_: unknown, row: Lab) => (
              <Button danger size="small" onClick={() => handleDelete(row.id)}>Delete</Button>
            ),
          },
        ]}
      />

      <Modal title="Create lab" open={open} onCancel={() => setOpen(false)} onOk={handleCreate}>
        <Form form={form} layout="vertical">
          <Form.Item label="Workspace" name="workspace_id" rules={[{ required: true }]}>
            <Select options={workspaces.map((w) => ({ value: w.id, label: w.name }))} />
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
          <Form.Item label="Kernel image" name="kernel_image">
            <Input placeholder="e.g. jupyter/scipy-notebook:latest" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
