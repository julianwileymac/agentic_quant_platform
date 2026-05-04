"use client";

import { PlusOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import useSWR, { mutate } from "swr";

import { createOrg, deleteOrg, listOrgs, type Organization } from "@/lib/api/tenancy";

const { Title } = Typography;

export default function OrgsAdminPage() {
  const { data: orgs = [], isLoading } = useSWR<Organization[]>("orgs", listOrgs);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ slug: string; name: string; billing_email?: string }>();

  async function handleCreate() {
    const values = await form.validateFields();
    await createOrg(values);
    form.resetFields();
    setOpen(false);
    await mutate("orgs");
  }

  async function handleDelete(id: string) {
    await deleteOrg(id);
    await mutate("orgs");
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Space style={{ justifyContent: "space-between", width: "100%" }}>
        <Title level={3} style={{ margin: 0 }}>Organizations</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          New organization
        </Button>
      </Space>

      <Table
        dataSource={orgs}
        rowKey="id"
        loading={isLoading}
        columns={[
          { title: "Slug", dataIndex: "slug" },
          { title: "Name", dataIndex: "name" },
          {
            title: "Status",
            dataIndex: "status",
            render: (s: string) => <Tag color={s === "active" ? "green" : "default"}>{s}</Tag>,
          },
          { title: "Billing email", dataIndex: "billing_email" },
          {
            title: "Actions",
            render: (_: unknown, row: Organization) => (
              <Button danger size="small" onClick={() => handleDelete(row.id)}>
                Delete
              </Button>
            ),
          },
        ]}
      />

      <Modal
        title="Create organization"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={handleCreate}
      >
        <Form form={form} layout="vertical">
          <Form.Item label="Slug" name="slug" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="Name" name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="Billing email" name="billing_email">
            <Input type="email" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
