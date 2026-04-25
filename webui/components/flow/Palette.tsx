"use client";

import { Card, Typography } from "antd";
import type { DragEvent } from "react";

import type { PaletteItem, PaletteSection } from "./types";

const { Text } = Typography;

interface PaletteProps {
  sections: PaletteSection[];
  /** MIME type used for HTML5 drag-and-drop. */
  dragMime?: string;
}

export const PALETTE_DRAG_MIME = "application/aqp-palette";

export function Palette({ sections, dragMime = PALETTE_DRAG_MIME }: PaletteProps) {
  function onDragStart(event: DragEvent<HTMLDivElement>, item: PaletteItem) {
    event.dataTransfer.setData(dragMime, JSON.stringify(item));
    event.dataTransfer.effectAllowed = "move";
  }

  return (
    <div
      style={{
        width: 260,
        height: "100%",
        overflowY: "auto",
        padding: 12,
        borderRight: "1px solid var(--ant-color-border, #1f2937)",
        background: "var(--ant-color-bg-container, #0b0f1a)",
      }}
    >
      <Text strong style={{ display: "block", marginBottom: 8 }}>
        Palette
      </Text>
      {sections.map((section) => (
        <div key={section.title} style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1 }}>
            {section.title}
          </Text>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
            {section.items.map((item) => (
              <Card
                key={item.kind}
                size="small"
                hoverable
                draggable
                onDragStart={(e) => onDragStart(e as DragEvent<HTMLDivElement>, item)}
                style={{
                  borderLeft: `3px solid ${item.accent ?? "#3b82f6"}`,
                  cursor: "grab",
                }}
                styles={{ body: { padding: "8px 10px" } }}
              >
                <Text strong style={{ fontSize: 12, display: "block" }}>
                  {item.label}
                </Text>
                {item.description ? (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {item.description}
                  </Text>
                ) : null}
              </Card>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
