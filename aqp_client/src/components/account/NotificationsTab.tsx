import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

function DisabledToggle({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2">
      <span className="text-sm">{label}</span>
      <Switch checked={false} disabled />
    </div>
  );
}

export function NotificationsTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Notifications</CardTitle>
        <CardDescription>Notification preferences (coming soon).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <DisabledToggle label="Trade alerts" />
        <DisabledToggle label="Risk alerts" />
        <DisabledToggle label="Weekly digest" />
      </CardContent>
    </Card>
  );
}
