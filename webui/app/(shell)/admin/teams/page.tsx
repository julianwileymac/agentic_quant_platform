"use client";

import { PlusOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Select, Space, Table, Typography } from "antd";
import { useState } from "react";
import useSWR, { mutate } from "swr";

import {
  createTeam,
  deleteTeam,
  listOrgs,
  listTeams,
  type Organization,
  type Team,
} from "@/lib/api/tenancy";

const { Title } = Typography;

export default function TeamsAdminPage() {
  const { data: orgs = [] } = useSWR<Organization[]>("orgs", listOrgs);
  const { data: teams = [], isLoading } = useSWR<Team[]>("teams", () => listTeams());
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ org_id: string; slug: string; name: string; description?: string }>();

  async function handleCreate() {
    const values = await form.validateFields();
    await createTeam(values);
    form.resetFields();
    setOpen(false);
    await mutate("teams");
  }

  async function handleDelete(id: string) {
    await deleteTeam(id);
    await mutate("teams");
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Space style={{ justifyContent: "space-between", width: "100%" }}>
        <Title level={3} style={{ margin: 0 }}>Teams</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          New team
        </Button>
      </Space>

      <Table
        dataSource={teams}
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
          { title: "Description", dataIndex: "description" },
          {
            title: "Actions",
            render: (_: unknown, row: Team) => (
              <Button danger size="small" onClick={() => handleDelete(row.id)}>Delete</Button>
            ),
          },
        ]}
      />

      <Modal title="Create team" open={open} onCancel={() => setOpen(false)} onOk={handleCreate}>
        <Form form={form} layout="vertical">
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
        </Form>
      </Modal>
    </Space>
  );
}
