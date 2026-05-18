import { QueryClient } from "@tanstack/react-query";

/**
 * Single QueryClient with sane defaults for an algorithmic trading
 * UI: 30 s stale window so navigating between routes never re-fetches
 * unnecessarily, exponential backoff retry that mitigates the
 * "Database Locked" stalls the SQLite-backed services occasionally
 * produce, and no refetch on focus (operators tab between charts and
 * docs constantly).
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: (failureCount, error) => {
          if (failureCount >= 3) return false;
          const status = (error as { status?: number } | undefined)?.status ?? 0;
          if (status === 401 || status === 403 || status === 404) return false;
          return true;
        },
        retryDelay: (attempt) => Math.min(8_000, 500 * 2 ** attempt),
        refetchOnWindowFocus: false,
        refetchOnReconnect: true,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}
