"use client";

import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Table,
  Tag,
  message,
} from "antd";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { KeyRound, ShieldCheck, Trash2 } from "lucide-react";

import { useStepUp, runWithStepUp } from "@/hooks/useStepUp";

interface BrokerCredential {
  id: string;
  provider: string;
  label: string;
  environment: "paper" | "live" | "sandbox";
  is_active: boolean;
  created_at: string;
}

const BROKERS = [
  { value: "alpaca", label: "Alpaca" },
  { value: "interactive_brokers", label: "Interactive Brokers" },
  { value: "tradier", label: "Tradier" },
  { value: "tradestation", label: "TradeStation" },
  { value: "schwab", label: "Charles Schwab" },
  { value: "etrade", label: "ETrade" },
  { value: "binance", label: "Binance" },
  { value: "coinbase", label: "Coinbase" },
  { value: "kraken", label: "Kraken" },
];

export default function BrokerSettingsPage() {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();
  const { isSupported, requestStepUp } = useStepUp();

  const list = useQuery<{ credentials: BrokerCredential[] }>({
    queryKey: ["broker-credentials"],
    queryFn: async () => {
      const res = await fetch("/api/me/broker-credentials", {
        credentials: "include",
      });
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
  });

  async function enrol(values: {
    provider: string;
    label: string;
    environment: "paper" | "live" | "sandbox";
    api_key: string;
    api_secret?: string;
  }) {
    setSubmitting(true);
    try {
      await runWithStepUp(requestStepUp, isSupported, async () => {
        const res = await fetch("/api/me/broker-credentials", {
          method: "POST",
          credentials: "include",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(values),
        });
        if (!res.ok) {
          const err = new Error(`enrol failed: ${res.status}`);
          (err as Error & { headers?: Headers }).headers = res.headers;
          throw err;
        }
      });
      message.success(`Connected ${values.provider}`);
      setOpen(false);
      form.resetFields();
      list.refetch();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Enrolment failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function revoke(id: string) {
    try {
      await runWithStepUp(requestStepUp, isSupported, async () => {
        const res = await fetch(
          `/api/me/broker-credentials/${encodeURIComponent(id)}`,
          { method: "DELETE", credentials: "include" },
        );
        if (!res.ok) {
          const err = new Error(`revoke failed: ${res.status}`);
          (err as Error & { headers?: Headers }).headers = res.headers;
          throw err;
        }
      });
      message.success("Credential revoked");
      list.refetch();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Revoke failed");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Alert
        type="info"
        showIcon
        icon={<ShieldCheck size={16} />}
        message="Your brokerage credentials are envelope-encrypted in our vault"
        description="API keys you enter here are encrypted with AES-256-GCM (per-credential DEK wrapped by a Vault Transit KEK). Plaintext is dropped from memory immediately after encryption. We can never read your raw credentials."
      />

      <Card
        title="Connected brokerages"
        extra={
          <Button
            type="primary"
            icon={<KeyRound size={14} />}
            onClick={() => setOpen(true)}
          >
            Add brokerage
          </Button>
        }
      >
        <Table
          rowKey="id"
          loading={list.isLoading}
          dataSource={list.data?.credentials ?? []}
          columns={[
            { title: "Provider", dataIndex: "provider" },
            { title: "Label", dataIndex: "label" },
            {
              title: "Environment",
              dataIndex: "environment",
              render: (env: BrokerCredential["environment"]) => (
                <Tag color={env === "live" ? "red" : "warning"}>{env}</Tag>
              ),
            },
            {
              title: "Status",
              dataIndex: "is_active",
              render: (active: boolean) =>
                active ? <Tag color="green">active</Tag> : <Tag>inactive</Tag>,
            },
            { title: "Created", dataIndex: "created_at" },
            {
              title: "",
              key: "actions",
              render: (_: unknown, row: BrokerCredential) => (
                <Button
                  size="small"
                  danger
                  icon={<Trash2 size={12} />}
                  onClick={() => revoke(row.id)}
                >
                  Revoke
                </Button>
              ),
            },
          ]}
          pagination={false}
        />
      </Card>

      <Modal
        title="Add brokerage"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={submitting}
        okText="Connect"
      >
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={enrol}
          initialValues={{ environment: "paper" }}
        >
          <Form.Item
            label="Provider"
            name="provider"
            rules={[{ required: true }]}
          >
            <Select options={BROKERS} placeholder="Pick a brokerage" />
          </Form.Item>
          <Form.Item
            label="Label"
            name="label"
            rules={[{ required: true }]}
            extra="Used in the EntityPicker dropdowns when configuring a strategy."
          >
            <Input placeholder="paper-prod, live-main, …" />
          </Form.Item>
          <Form.Item
            label="Environment"
            name="environment"
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: "paper", label: "Paper" },
                { value: "live", label: "Live" },
                { value: "sandbox", label: "Sandbox" },
              ]}
            />
          </Form.Item>
          <Form.Item
            label="API key"
            name="api_key"
            rules={[{ required: true }]}
            extra="Encrypted in memory and dropped immediately after persistence."
          >
            <Input.Password placeholder="paste here" />
          </Form.Item>
          <Form.Item
            label="API secret (if applicable)"
            name="api_secret"
          >
            <Input.Password placeholder="paste here" />
          </Form.Item>
          <div className="rounded border p-3 text-xs" style={{ borderColor: "var(--warn-fg)", background: "rgba(245, 158, 11, 0.06)", color: "var(--warn-fg)" }}>
            Step-up MFA required. You may be prompted to re-authenticate before
            the credential is saved.
          </div>
        </Form>
      </Modal>
    </div>
  );
}
