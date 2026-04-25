"use client";

import { Layout } from "antd";
import dynamic from "next/dynamic";
import type { ReactNode } from "react";

import { CommandK } from "@/components/shell/CommandK";
import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";

const AssistantDrawer = dynamic(
  () => import("@/components/chat/AssistantDrawer").then((m) => m.AssistantDrawer),
  { ssr: false },
);

const { Content } = Layout;

export function ShellChrome({ children }: { children: ReactNode }) {
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sidebar />
      <Layout>
        <TopBar />
        <Content style={{ padding: 0, overflow: "auto" }}>{children}</Content>
      </Layout>
      <CommandK />
      <AssistantDrawer />
    </Layout>
  );
}
