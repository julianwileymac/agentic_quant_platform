"use client";

import { Button, Card, Descriptions } from "antd";
import { CreditCard, ExternalLink } from "lucide-react";

export default function BillingSettingsPage() {
  async function openPortal() {
    const res = await fetch("/api/billing/portal", {
      method: "POST",
      credentials: "include",
    });
    if (res.ok) {
      const { url } = (await res.json()) as { url: string };
      window.location.href = url;
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card title="Subscription">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="Plan">Pro</Descriptions.Item>
          <Descriptions.Item label="Renews">2026-06-24</Descriptions.Item>
          <Descriptions.Item label="Seats">3 / 5</Descriptions.Item>
          <Descriptions.Item label="Billing email">accounts@example.com</Descriptions.Item>
        </Descriptions>
        <Button
          type="primary"
          icon={<CreditCard size={14} />}
          style={{ marginTop: 16 }}
          onClick={openPortal}
        >
          Open billing portal
        </Button>
      </Card>

      <Card title="Usage this month">
        <Descriptions column={2} size="small">
          <Descriptions.Item label="Strategies">12</Descriptions.Item>
          <Descriptions.Item label="Paper runs">87</Descriptions.Item>
          <Descriptions.Item label="Iceberg storage">42 GB / 200 GB</Descriptions.Item>
          <Descriptions.Item label="Agent calls">3,241 / 10,000</Descriptions.Item>
        </Descriptions>
      </Card>

      <div className="text-xs" style={{ color: "var(--text-muted)" }}>
        Billing is processed by Stripe.{" "}
        <a
          href="/legal/privacy"
          style={{ color: "var(--text-secondary)" }}
          className="inline-flex items-center gap-1"
        >
          Privacy <ExternalLink size={12} />
        </a>
      </div>
    </div>
  );
}
