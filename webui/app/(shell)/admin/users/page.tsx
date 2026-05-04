"use client";

import { PlusOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import useSWR, { mutate } from "swr";

import { createUser, deleteUser, listUsers, type User } from "@/lib/api/tenancy";

const { Title } = Typography;

export default function UsersAdminPage() {
  const { data: users = [], isLoading } = useSWR<User[]>("users", listUsers);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ email: string; display_name: string; auth_subject?: string }>();

  async function handleCreate() {
    const values = await form.validateFields();
    await createUser(values);
    form.resetFields();
    setOpen(false);
    await mutate("users");
  }

  async function handleDelete(id: string) {
    await deleteUser(id);
    await mutate("users");
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Space style={{ justifyContent: "space-between", width: "100%" }}>
        <Title level={3} style={{ margin: 0 }}>Users</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          New user
        </Button>
      </Space>

      <Table
        dataSource={users}
        rowKey="id"
        loading={isLoading}
        columns={[
          { title: "Email", dataIndex: "email" },
          { title: "Display name", dataIndex: "display_name" },
          {
            title: "Provider",
            dataIndex: "auth_provider",
            render: (s: string) => <Tag>{s}</Tag>,
          },
          {
            title: "Status",
            dataIndex: "status",
            render: (s: string) => <Tag color={s === "active" ? "green" : "default"}>{s}</Tag>,
          },
          {
            title: "Actions",
            render: (_: unknown, row: User) => (
              <Button danger size="small" onClick={() => handleDelete(row.id)}>Delete</Button>
            ),
          },
        ]}
      />

      <Modal title="Create user" open={open} onCancel={() => setOpen(false)} onOk={handleCreate}>
        <Form form={form} layout="vertical">
          <Form.Item label="Email" name="email" rules={[{ required: true, type: "email" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="Display name" name="display_name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="Auth subject (optional)" name="auth_subject">
            <Input placeholder="OIDC sub claim or local username" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
