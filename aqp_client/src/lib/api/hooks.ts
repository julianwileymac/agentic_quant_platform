import {
  type DefaultError,
  type Query,
  useMutation,
  type UseMutationOptions,
  useQuery,
} from "@tanstack/react-query";

import { apiFetch } from "./client";

type RefetchInterval<TData> =
  | number
  | false
  | ((query: Query<TData, Error, TData, ReadonlyArray<unknown>>) => number | false | undefined);

interface ApiQueryArgs<TData> {
  queryKey: ReadonlyArray<unknown>;
  path: string;
  query?: Record<string, string | number | boolean | undefined | null>;
  enabled?: boolean;
  refetchInterval?: RefetchInterval<TData>;
  refetchIntervalInBackground?: boolean;
  refetchOnWindowFocus?: boolean | "always";
  staleTime?: number;
  /**
   * Optional projector. Receives the raw `apiFetch` response (`unknown`)
   * and returns the typed `TData` shape consumers expect. Lets the
   * legacy webui ports keep their `select: (raw) => ...` calls without
   * fighting the new wrapper.
   */
  select?: (data: unknown) => TData;
  retry?: boolean | number;
}

/**
 * Thin wrapper around TanStack Query that hands the request to
 * `apiFetch` and inherits the global retry / staleTime defaults from
 * the QueryClient configured in `App.tsx`.
 */
export function useApiQuery<TData = unknown>(args: ApiQueryArgs<TData>) {
  const { queryKey, path, query, select } = args;
  // `exactOptionalPropertyTypes: true` rejects `undefined` for optional
  // fields, so we build the options object with only the keys the
  // caller actually supplied.
  const options: Record<string, unknown> = {
    queryKey: query ? [...queryKey, query] : queryKey,
    queryFn: async () => {
      const raw = await apiFetch<unknown>(path, query ? { query } : {});
      return (select ? select(raw) : raw) as TData;
    },
  };
  if (args.enabled !== undefined) options.enabled = args.enabled;
  if (args.refetchInterval !== undefined) options.refetchInterval = args.refetchInterval;
  if (args.refetchIntervalInBackground !== undefined)
    options.refetchIntervalInBackground = args.refetchIntervalInBackground;
  if (args.refetchOnWindowFocus !== undefined)
    options.refetchOnWindowFocus = args.refetchOnWindowFocus;
  if (args.staleTime !== undefined) options.staleTime = args.staleTime;
  if (args.retry !== undefined) options.retry = args.retry;
  return useQuery<TData, Error, TData, ReadonlyArray<unknown>>(
    options as unknown as Parameters<
      typeof useQuery<TData, Error, TData, ReadonlyArray<unknown>>
    >[0],
  );
}

interface ApiMutationOptions<TData, TBody = unknown>
  extends Omit<UseMutationOptions<TData, DefaultError, TBody, unknown>, "mutationFn"> {
  path: string | ((input: TBody) => string);
  method?: "POST" | "PUT" | "PATCH" | "DELETE";
}

export function useApiMutation<TData = unknown, TBody = unknown>({
  path,
  method = "POST",
  ...rest
}: ApiMutationOptions<TData, TBody>) {
  return useMutation<TData, DefaultError, TBody>({
    mutationFn: async (input) => {
      const resolvedPath = typeof path === "function" ? path(input) : path;
      const init: { method: typeof method; body?: BodyInit | null } = { method };
      if (input != null) init.body = JSON.stringify(input);
      return apiFetch<TData>(resolvedPath, init);
    },
    ...rest,
  });
}
