import { Navigate, Route, Routes } from "react-router-dom";

import { AdminShell } from "./components/layout/AdminShell";
import { AccountsRoute } from "./routes/accounts";
import { BuildsIndex } from "./routes/builds/index";
import { BuildDetail } from "./routes/builds/detail";
import { DashboardRoute } from "./routes/dashboard";
import { RunbooksIndex } from "./routes/runbooks/index";
import { SettingsRoute } from "./routes/settings/index";
import { ServicesRoute } from "./routes/services";
import { TenantDetail } from "./routes/tenants/detail";
import { TenantVendingWizard } from "./routes/tenants/new";

export function App() {
  return (
    <AdminShell>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardRoute />} />
        <Route path="/accounts" element={<AccountsRoute />} />
        <Route path="/accounts/:orgId" element={<TenantDetail />} />
        <Route path="/services" element={<ServicesRoute />} />
        <Route path="/settings" element={<SettingsRoute />} />
        <Route path="/tenants/new" element={<TenantVendingWizard />} />
        <Route path="/builds" element={<BuildsIndex />} />
        <Route path="/builds/:jobName" element={<BuildDetail />} />
        <Route path="/runbooks" element={<RunbooksIndex />} />
        <Route path="/audit" element={<AuditPlaceholder />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AdminShell>
  );
}

function AuditPlaceholder() {
  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-semibold tracking-tight">Audit</h1>
      <p className="text-sm text-muted-foreground">
        Live tail of admin audit rows. Reads from
        <code> AQP_ADMIN_AUDIT_JSONL_PATH</code> when the BFF runs in
        JSONL mode; otherwise the monolith owns the query API.
      </p>
    </section>
  );
}
