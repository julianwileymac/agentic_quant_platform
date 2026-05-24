"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState } from "react";

import type { ApiError } from "@/lib/api/errors";

/**
 * Creates a TanStack Query client with retry semantics matching
 * aqp_client/src/lib/api/query-client.ts:
 *   - staleTime 30s, gcTime 5min.
 *   - Skip 401 / 403 / 404 retries (they will never become 200).
 *   - Exponential backoff capped at 30s, max 3 attempts.
 *   - refetchOnWindowFocus disabled (we use WebSocket invalidation).
 */
function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          const status = (error as ApiError | undefined)?.status;
          if (status === 401 || status === 403 || status === 404) return false;
          return failureCount < 3;
        },
        retryDelay: (attemptIndex) =>
          Math.min(30_000, 500 * 2 ** attemptIndex) + Math.random() * 250,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(createQueryClient);

  return (
    <QueryClientProvider client={client}>
      {children}
      {process.env.NODE_ENV === "development" ? (
        <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
      ) : null}
    </QueryClientProvider>
  );
}
