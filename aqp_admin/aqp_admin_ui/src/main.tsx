import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { setBearerProvider } from "./lib/api";
import { AuthProvider } from "./lib/auth/AuthProvider";
import { useAuth } from "./lib/auth/useAuth";
import "./styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

function ApiBearerBridge({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  useEffect(() => {
    setBearerProvider(() => auth.getAccessToken());
    return () => setBearerProvider(null);
  }, [auth]);
  return <>{children}</>;
}

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("root container not found");
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ApiBearerBridge>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ApiBearerBridge>
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
