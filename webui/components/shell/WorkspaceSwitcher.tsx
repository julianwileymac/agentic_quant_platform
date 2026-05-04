"use client";

import { ApartmentOutlined, ExperimentOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { Dropdown, Space, Tag } from "antd";
import type { MenuProps } from "antd";

import { useWorkspace } from "@/lib/tenancy/use-workspace";

/**
 * Header chip — switch active org / workspace / project / lab.
 *
 * The chip emits `X-AQP-Workspace`, `X-AQP-Project`, and `X-AQP-Lab`
 * headers via the api client middleware, so every subsequent fetch is
 * automatically scoped to the selected tenancy.
 */
export function WorkspaceSwitcher() {
  const {
    org,
    workspace,
    project,
    lab,
    orgs,
    workspaces,
    projects,
    labs,
    switchOrg,
    switchWorkspace,
    switchProject,
    switchLab,
  } = useWorkspace();

  const orgMenu: MenuProps = {
    items: orgs.map((o) => ({
      key: o.id,
      label: `${o.name} (${o.slug})`,
      onClick: () => switchOrg(o.id),
    })),
  };
  const wsMenu: MenuProps = {
    items: workspaces.map((w) => ({
      key: w.id,
      label: `${w.name} ${w.archived ? "(archived)" : ""}`,
      onClick: () => switchWorkspace(w.id),
    })),
  };
  const projMenu: MenuProps = {
    items: [
      { key: "__none__", label: "(no project)", onClick: () => switchProject(null) },
      ...projects.map((p) => ({
        key: p.id,
        label: p.name,
        onClick: () => switchProject(p.id),
      })),
    ],
  };
  const labMenu: MenuProps = {
    items: [
      { key: "__none__", label: "(no lab)", onClick: () => switchLab(null) },
      ...labs.map((l) => ({
        key: l.id,
        label: l.name,
        onClick: () => switchLab(l.id),
      })),
    ],
  };

  return (
    <Space size={4} wrap={false}>
      <Dropdown menu={orgMenu} trigger={["click"]}>
        <Tag icon={<ApartmentOutlined />} style={{ cursor: "pointer", margin: 0 }}>
          {org?.slug ?? "default"}
        </Tag>
      </Dropdown>
      <Dropdown menu={wsMenu} trigger={["click"]}>
        <Tag icon={<FolderOpenOutlined />} color="blue" style={{ cursor: "pointer", margin: 0 }}>
          {workspace?.slug ?? "default"}
        </Tag>
      </Dropdown>
      <Dropdown menu={projMenu} trigger={["click"]}>
        <Tag color="geekblue" style={{ cursor: "pointer", margin: 0 }}>
          {project?.slug ?? "—"}
        </Tag>
      </Dropdown>
      <Dropdown menu={labMenu} trigger={["click"]}>
        <Tag icon={<ExperimentOutlined />} color="purple" style={{ cursor: "pointer", margin: 0 }}>
          {lab?.slug ?? "—"}
        </Tag>
      </Dropdown>
    </Space>
  );
}
