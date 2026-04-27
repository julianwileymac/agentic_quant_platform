"use client";

import {
  CopyOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { Menu, type MenuProps } from "antd";
import { useEffect, useRef, type CSSProperties } from "react";

import type { PaletteItem, PaletteSection } from "./types";

export interface CanvasContextMenuProps {
  open: boolean;
  position: { x: number; y: number } | null;
  /** When non-null, the menu was opened on a node. */
  nodeId?: string | null;
  paletteSections?: PaletteSection[];
  onClose: () => void;
  onAddNode?: (item: PaletteItem) => void;
  onDeleteNode?: (nodeId: string) => void;
  onDuplicateNode?: (nodeId: string) => void;
  onDisconnectNode?: (nodeId: string) => void;
}

export function CanvasContextMenu(props: CanvasContextMenuProps) {
  const {
    open,
    position,
    nodeId,
    paletteSections = [],
    onClose,
    onAddNode,
    onDeleteNode,
    onDuplicateNode,
    onDisconnectNode,
  } = props;

  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!wrapperRef.current) return;
      if (e.target instanceof Node && wrapperRef.current.contains(e.target)) return;
      onClose();
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("mousedown", onDocClick);
    window.addEventListener("keydown", onEsc);
    return () => {
      window.removeEventListener("mousedown", onDocClick);
      window.removeEventListener("keydown", onEsc);
    };
  }, [open, onClose]);

  if (!open || !position) return null;

  const isNode = Boolean(nodeId);

  const addSubmenu: MenuProps["items"] = paletteSections.map((section) => ({
    key: `add-${section.title}`,
    label: section.title,
    children: section.items.map((item) => ({
      key: `add-${section.title}-${item.kind}`,
      label: item.label,
      onClick: () => {
        onAddNode?.(item);
        onClose();
      },
    })),
  }));

  const items: MenuProps["items"] = isNode
    ? [
        {
          key: "duplicate",
          icon: <CopyOutlined />,
          label: "Duplicate",
          onClick: () => {
            if (nodeId) onDuplicateNode?.(nodeId);
            onClose();
          },
        },
        {
          key: "disconnect",
          icon: <DisconnectOutlined />,
          label: "Disconnect",
          onClick: () => {
            if (nodeId) onDisconnectNode?.(nodeId);
            onClose();
          },
        },
        { type: "divider" as const },
        {
          key: "delete",
          icon: <DeleteOutlined />,
          danger: true,
          label: "Delete node",
          onClick: () => {
            if (nodeId) onDeleteNode?.(nodeId);
            onClose();
          },
        },
      ]
    : [
        {
          key: "add",
          icon: <PlusOutlined />,
          label: "Add node",
          children:
            addSubmenu.length > 0
              ? addSubmenu
              : [{ key: "empty", label: "Palette empty", disabled: true }],
        },
      ];

  const style: CSSProperties = {
    position: "fixed",
    top: position.y,
    left: position.x,
    zIndex: 1000,
    background: "var(--ant-color-bg-elevated, #1f2937)",
    boxShadow: "0 4px 16px rgba(0,0,0,0.35)",
    borderRadius: 6,
    minWidth: 220,
    padding: 4,
  };

  return (
    <div ref={wrapperRef} style={style} onContextMenu={(e) => e.preventDefault()}>
      <Menu mode="vertical" selectable={false} items={items} style={{ borderInlineEnd: 0 }} />
    </div>
  );
}
