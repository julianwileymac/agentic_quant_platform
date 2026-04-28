"use client";

import { Button, Card, Space, Tabs, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";

import { DagsterAssetsPane } from "@/components/workflows/DagsterAssetsPane";
import { DataWorkflowPage } from "@/components/workflows/DataWorkflowPage";

export function DataWorkflowsTabs() {
  const [active, setActive] = useState<string>("flow");
  return (
    <Tabs
      activeKey={active}
      onChange={setActive}
      items={[
        {
          key: "flow",
          label: "Flow editor",
          children: <DataWorkflowPage />,
        },
        {
          key: "dagster",
          label: "Dagster assets",
          children: <DagsterAssetsPane />,
        },
        {
          key: "dbt",
          label: "dbt project",
          children: <DbtProjectTab />,
        },
      ]}
    />
  );
}

function DbtProjectTab() {
  return (
    <Card size="small">
      <Space direction="vertical" size={8}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          dbt modeling project
        </Typography.Title>
        <Typography.Text type="secondary">
          Export AQP entities and datasets into the local DuckDB-backed dbt project, then inspect and build models.
        </Typography.Text>
        <Link href="/data/dbt">
          <Button type="primary">Open dbt Models</Button>
        </Link>
      </Space>
    </Card>
  );
}
