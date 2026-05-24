import { Navigate, Route, Routes } from "react-router-dom";

import { AdminShell } from "./components/layout/AdminShell";
import { AccountsRoute } from "./routes/accounts";
import { DashboardRoute } from "./routes/dashboard";
import { ServicesRoute } from "./routes/services";

export function App() {
  return (
    <AdminShell>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardRoute />} />
        <Route path="/accounts" element={<AccountsRoute />} />
        <Route path="/services" element={<ServicesRoute />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AdminShell>
  );
}
