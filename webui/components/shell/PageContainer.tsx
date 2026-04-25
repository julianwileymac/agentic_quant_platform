"use client";

import { Space, Typography } from "antd";
import type { ReactNode } from "react";

const { Title, Text } = Typography;

interface PageContainerProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  full?: boolean;
}

export function PageContainer({ title, subtitle, extra, children, full }: PageContainerProps) {
  return (
    <div
      style={{
        padding: full ? 0 : 24,
        display: "flex",
        flexDirection: "column",
        gap: 16,
        minHeight: "calc(100vh - 52px)",
      }}
    >
      {(title || subtitle || extra) && !full ? (
        <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
          <Space direction="vertical" size={2} style={{ flex: 1 }}>
            {title ? (
              <Title level={3} style={{ margin: 0 }}>
                {title}
              </Title>
            ) : null}
            {subtitle ? <Text type="secondary">{subtitle}</Text> : null}
          </Space>
          {extra ? <div>{extra}</div> : null}
        </div>
      ) : null}
      <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
    </div>
  );
}
