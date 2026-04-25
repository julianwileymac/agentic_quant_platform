"use client";

import { AntdRegistry } from "@ant-design/nextjs-registry";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { App as AntdApp, ConfigProvider } from "antd";
import { useMemo, useState, type ReactNode } from "react";

import { buildTheme } from "@/lib/theme";
import { useUiStore } from "@/lib/store/ui";

interface Props {
  children: ReactNode;
}

export function Providers({ children }: Props) {
  const themeMode = useUiStore((s) => s.themeMode);
  const themeConfig = useMemo(() => buildTheme(themeMode), [themeMode]);

  const [queryClient] = useState(
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
    <AntdRegistry>
      <QueryClientProvider client={queryClient}>
        <ConfigProvider theme={themeConfig}>
          <AntdApp>{children}</AntdApp>
        </ConfigProvider>
        {process.env.NODE_ENV === "development" ? (
          <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-left" />
        ) : null}
      </QueryClientProvider>
    </AntdRegistry>
  );
}
