"use client";

/**
 * Top-level client providers — TanStack Query + Auth.
 *
 * Auth is intentionally lightweight: the actual Auth0 / MSAL SDK is
 * dynamically imported once the runtime knows which provider is
 * active (read from `NEXT_PUBLIC_AQP_AUTH_PROVIDER`). For a first
 * paint without an IdP round-trip, the providers tree always
 * mounts; tokens land after the auth module resolves.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { AuthProvider } from "@/components/auth/AuthProvider";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
