import { Wrench } from "lucide-react";
import type { ReactElement } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import type { NavItem } from "@/components/shell/nav-config";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Sentinel "should never reach" placeholder. Every entry in `NAV_ITEMS`
 * is now mapped to a real route in `REAL_ROUTES` (verified by the
 * coverage check at `aqp_client/check-coverage.mjs`); if this component
 * ever renders, it means a new nav entry was added without wiring its
 * route. It logs a console warning so the gap is obvious during dev.
 */
export function stubRoute(item: NavItem): ReactElement {
  if (typeof window !== "undefined") {
    // eslint-disable-next-line no-console
    console.warn(
      `[aqp] route stub rendered for ${item.href} — add a REAL_ROUTES entry in src/routes.tsx`,
    );
  }
  return (
    <PageContainer
      title={item.label}
      subtitle="Route not yet wired in the new frontend. Add it to REAL_ROUTES in src/routes.tsx to fix."
      extra={<Badge variant="warn">missing route</Badge>}
    >
      <Card className="max-w-2xl">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Wrench className="h-4 w-4 text-[var(--warn-fg)]" />
            <CardTitle>Route placeholder</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-[var(--text-secondary)]">
          <p>
            <span className="font-medium text-[var(--text-primary)]">Group:</span> {item.group}
            {item.submenu ? ` / ${item.submenu}` : ""}
          </p>
          <p>
            <span className="font-medium text-[var(--text-primary)]">Path:</span>{" "}
            <code className="rounded bg-[var(--bg-app)] px-1 font-mono text-xs">{item.href}</code>
          </p>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
