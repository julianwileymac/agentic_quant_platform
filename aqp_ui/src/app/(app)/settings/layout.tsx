import Link from "next/link";
import { Card } from "antd";

import { cn } from "@/lib/cn";

const SETTINGS_NAV = [
  { href: "/settings/team", label: "Team" },
  { href: "/settings/brokers", label: "Brokers" },
  { href: "/settings/billing", label: "Billing" },
  { href: "/settings/profile", label: "Profile" },
];

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
        Settings
      </h1>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[200px_1fr]">
        <Card size="small" styles={{ body: { padding: 8 } }}>
          <nav className="flex flex-col gap-1">
            {SETTINGS_NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded px-3 py-1.5 text-sm transition-colors hover:bg-white/5",
                )}
                style={{ color: "var(--text-primary)" }}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </Card>
        <div>{children}</div>
      </div>
    </div>
  );
}
