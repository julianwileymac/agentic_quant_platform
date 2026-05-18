import { Navigate } from "react-router-dom";

export function AccountRoute() {
  return <Navigate to="/auth/profile" replace />;
}
