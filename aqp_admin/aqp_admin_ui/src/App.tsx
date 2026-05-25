import { Navigate, Route, Routes } from "react-router-dom";

import { AdminShell } from "./components/layout/AdminShell";
import { AccountsRoute } from "./routes/accounts";
import { AuditIndex } from "./routes/audit/index";
import { BuildsIndex } from "./routes/builds/index";
import { BuildDetail } from "./routes/builds/detail";
import { DashboardRoute } from "./routes/dashboard";
import { KubernetesIndex } from "./routes/kubernetes/index";
import { RunbooksIndex } from "./routes/runbooks/index";
import { SettingsRoute } from "./routes/settings/index";
import { ServicesRoute } from "./routes/services";
import { TerraformIndex } from "./routes/terraform/index";
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
        <Route path="/terraform" element={<TerraformIndex />} />
        <Route path="/kubernetes" element={<KubernetesIndex />} />
        <Route path="/settings" element={<SettingsRoute />} />
        <Route path="/tenants/new" element={<TenantVendingWizard />} />
        <Route path="/builds" element={<BuildsIndex />} />
        <Route path="/builds/:jobName" element={<BuildDetail />} />
        <Route path="/runbooks" element={<RunbooksIndex />} />
        <Route path="/audit" element={<AuditIndex />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AdminShell>
  );
}
