"use client";

import { Avatar, Button, Card, Descriptions, Tag } from "antd";
import { LogOut } from "lucide-react";

import { useAuth } from "@/hooks/useAuth";

export default function ProfileSettingsPage() {
  const { user, provider, claims } = useAuth();

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex items-center gap-4">
          <Avatar size={64}>
            {(user?.name ?? user?.email ?? "?")[0]?.toUpperCase()}
          </Avatar>
          <div>
            <div className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
              {user?.name ?? user?.email ?? "Unknown user"}
            </div>
            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
              {user?.email}
            </div>
            <div className="mt-2 flex items-center gap-2 text-xs">
              <Tag>{provider}</Tag>
              {claims?.roles?.slice(0, 3).map((r) => (
                <Tag key={r} color="blue">
                  {r}
                </Tag>
              ))}
            </div>
          </div>
        </div>
      </Card>

      <Card title="Identity claims">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="User ID">
            <code>{user?.id ?? "—"}</code>
          </Descriptions.Item>
          <Descriptions.Item label="Provider">{provider ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="Organization">
            <code>{claims?.orgId ?? "—"}</code>
          </Descriptions.Item>
          <Descriptions.Item label="Workspace">
            <code>{claims?.workspaceId ?? "—"}</code>
          </Descriptions.Item>
          <Descriptions.Item label="Scopes">
            <div className="flex flex-wrap gap-1">
              {(claims?.scopes ?? []).map((s) => (
                <Tag key={s}>{s}</Tag>
              ))}
            </div>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Session">
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Sign out clears the AQP UI session cookie and redirects you to the
          provider's logout endpoint to terminate the upstream IdP session.
        </p>
        <Button
          danger
          icon={<LogOut size={14} />}
          style={{ marginTop: 12 }}
          onClick={() => {
            window.location.href = "/api/auth/logout?returnTo=/";
          }}
        >
          Sign out
        </Button>
      </Card>
    </div>
  );
}
