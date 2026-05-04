"use client";

import { PlusOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Select, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import useSWR, { mutate } from "swr";

import {
  createProject,
  deleteProject,
  listProjects,
  listWorkspaces,
  type Project,
  type Workspace,
} from "@/lib/api/tenancy";

const { Title } = Typography;

export default function ProjectsAdminPage() {
  const { data: workspaces = [] } = useSWR<Workspace[]>("workspaces", () => listWorkspaces());
  const { data: projects = [], isLoading } = useSWR<Project[]>("projects", () => listProjects());
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{
    workspace_id: string;
    slug: string;
    name: string;
    description?: string;
  }>();

  async function handleCreate() {
    const values = await form.validateFields();
    await createProject(values);
    form.resetFields();
    setOpen(false);
    await mutate("projects");
  }

  async function handleDelete(id: string) {
    await deleteProject(id);
    await mutate("projects");
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Space style={{ justifyContent: "space-between", width: "100%" }}>
        <Title level={3} style={{ margin: 0 }}>Projects</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          New project
        </Button>
      </Space>

      <Table
        dataSource={projects}
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
          { title: "Description", dataIndex: "description" },
          {
            title: "Archived",
            dataIndex: "archived",
            render: (v: boolean) => (v ? <Tag color="orange">archived</Tag> : <Tag color="green">active</Tag>),
          },
          {
            title: "Actions",
            render: (_: unknown, row: Project) => (
              <Button danger size="small" onClick={() => handleDelete(row.id)}>Delete</Button>
            ),
          },
        ]}
      />

      <Modal title="Create project" open={open} onCancel={() => setOpen(false)} onOk={handleCreate}>
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
        </Form>
      </Modal>
    </Space>
  );
}
