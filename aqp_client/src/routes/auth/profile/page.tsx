import * as Tabs from "@radix-ui/react-tabs";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { ConnectionsTab } from "@/components/account/ConnectionsTab";
import { DangerZoneTab } from "@/components/account/DangerZoneTab";
import { NotificationsTab } from "@/components/account/NotificationsTab";
import { ProfileTab } from "@/components/account/ProfileTab";
import { SecurityTab } from "@/components/account/SecurityTab";
import { SessionsTab } from "@/components/account/SessionsTab";
import { TenancyTab } from "@/components/account/TenancyTab";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TAB_IDS = [
  "profile",
  "security",
  "sessions",
  "connections",
  "tenancy",
  "notifications",
  "danger-zone",
] as const;

type TabId = (typeof TAB_IDS)[number];

function parseTab(value: string | null): TabId {
  return TAB_IDS.includes((value ?? "") as TabId) ? ((value ?? "profile") as TabId) : "profile";
}

export function ProfileRoute() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = useMemo(() => parseTab(searchParams.get("tab")), [searchParams]);

  const onTabChange = (value: string) => {
    const parsed = parseTab(value);
    const next = new URLSearchParams(searchParams);
    next.set("tab", parsed);
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="mx-auto w-full max-w-6xl p-6">
      <Card>
        <CardHeader>
          <CardTitle>Account settings</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs.Root value={tab} onValueChange={onTabChange}>
            <Tabs.List className="flex flex-wrap gap-2 border-b border-[var(--border-subtle)] pb-3">
              <TabTrigger value="profile">Profile</TabTrigger>
              <TabTrigger value="security">Security</TabTrigger>
              <TabTrigger value="sessions">Sessions</TabTrigger>
              <TabTrigger value="connections">Connections</TabTrigger>
              <TabTrigger value="tenancy">Tenancy</TabTrigger>
              <TabTrigger value="notifications">Notifications</TabTrigger>
              <TabTrigger value="danger-zone">Danger Zone</TabTrigger>
            </Tabs.List>

            <Tabs.Content value="profile" className="pt-4">
              <ProfileTab />
            </Tabs.Content>
            <Tabs.Content value="security" className="pt-4">
              <SecurityTab />
            </Tabs.Content>
            <Tabs.Content value="sessions" className="pt-4">
              <SessionsTab />
            </Tabs.Content>
            <Tabs.Content value="connections" className="pt-4">
              <ConnectionsTab />
            </Tabs.Content>
            <Tabs.Content value="tenancy" className="pt-4">
              <TenancyTab />
            </Tabs.Content>
            <Tabs.Content value="notifications" className="pt-4">
              <NotificationsTab />
            </Tabs.Content>
            <Tabs.Content value="danger-zone" className="pt-4">
              <DangerZoneTab />
            </Tabs.Content>
          </Tabs.Root>
        </CardContent>
      </Card>
    </div>
  );
}

function TabTrigger({ value, children }: { value: TabId; children: string }) {
  return (
    <Tabs.Trigger
      value={value}
      className="rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-1.5 text-sm data-[state=active]:border-[var(--info-fg)] data-[state=active]:text-[var(--info-fg)]"
    >
      {children}
    </Tabs.Trigger>
  );
}
