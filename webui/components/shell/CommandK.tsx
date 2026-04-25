"use client";

import { Modal, Input, List, Tag } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useUiStore } from "@/lib/store/ui";

import { NAV_ITEMS } from "./nav-config";

export function CommandK() {
  const open = useUiStore((s) => s.commandPaletteOpen);
  const setOpen = useUiStore((s) => s.setCommandPaletteOpen);
  const router = useRouter();
  const [q, setQ] = useState("");
  const [highlight, setHighlight] = useState(0);

  useEffect(() => {
    if (open) {
      setQ("");
      setHighlight(0);
    }
  }, [open]);

  const matches = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return NAV_ITEMS.slice(0, 12);
    return NAV_ITEMS.filter(
      (n) =>
        n.label.toLowerCase().includes(term) ||
        n.group.toLowerCase().includes(term) ||
        n.href.toLowerCase().includes(term),
    ).slice(0, 12);
  }, [q]);

  function go(href: string) {
    setOpen(false);
    router.push(href);
  }

  return (
    <Modal
      open={open}
      onCancel={() => setOpen(false)}
      footer={null}
      destroyOnClose
      width={560}
      closable={false}
      styles={{ body: { padding: 0 } }}
    >
      <Input
        autoFocus
        bordered={false}
        size="large"
        placeholder="Jump to a page or run a command…"
        prefix={<span style={{ opacity: 0.6 }}>›</span>}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setHighlight(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setHighlight((h) => Math.min(h + 1, matches.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHighlight((h) => Math.max(0, h - 1));
          } else if (e.key === "Enter") {
            const target = matches[highlight];
            if (target) go(target.href);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        style={{ padding: "16px 18px", fontSize: 16 }}
      />
      <div style={{ borderTop: "1px solid var(--ant-color-border, #e5e7eb)", maxHeight: 360, overflowY: "auto" }}>
        <List
          dataSource={matches}
          locale={{ emptyText: "No matches" }}
          renderItem={(item, idx) => (
            <List.Item
              onClick={() => go(item.href)}
              onMouseEnter={() => setHighlight(idx)}
              style={{
                padding: "10px 18px",
                cursor: "pointer",
                background:
                  idx === highlight
                    ? "var(--ant-color-bg-elevated, #f5f7fa)"
                    : "transparent",
                borderBottom: "none",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", width: "100%", gap: 10 }}>
                <span style={{ fontSize: 16 }}>{item.icon}</span>
                <span style={{ flex: 1 }}>{item.label}</span>
                <Tag style={{ marginInlineEnd: 0 }}>{item.group}</Tag>
                <span style={{ opacity: 0.5, fontSize: 12 }}>{item.href}</span>
              </div>
            </List.Item>
          )}
        />
      </div>
    </Modal>
  );
}
