import { redirect } from "next/navigation";

import { getSession } from "@/lib/auth/session";
import { AppShell } from "@/components/shell/AppShell";

/**
 * Protected layout for the operator dashboard.
 *
 * AGENTS rule 11 (CVE-2025-29927): middleware.ts is not the only gate.
 * Every (app)/* route runs through this layout's server-side getSession()
 * check, and every /api/* handler re-checks again.
 */
export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getSession();
  if (!session) {
    redirect("/login?returnTo=/dashboard");
  }
  if (!session.claims.orgId) {
    redirect("/login?error=missing_org");
  }

  return <AppShell>{children}</AppShell>;
}
