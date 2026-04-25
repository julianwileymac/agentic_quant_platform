"use client";

import { Select, Space, Tag, Typography } from "antd";

import { useFeatureSets, type FeatureSetSummary } from "@/lib/api/featureSets";

const { Text } = Typography;

interface FeatureSetPickerProps {
  value?: string | null;
  onChange?: (id: string | null, summary?: FeatureSetSummary) => void;
  placeholder?: string;
  width?: number | string;
  allowClear?: boolean;
}

export function FeatureSetPicker({
  value,
  onChange,
  placeholder = "Select a feature set",
  width = 320,
  allowClear = true,
}: FeatureSetPickerProps) {
  const { data, isLoading } = useFeatureSets();
  const items = data ?? [];

  return (
    <Select
      style={{ width }}
      placeholder={placeholder}
      loading={isLoading}
      allowClear={allowClear}
      value={value ?? undefined}
      onChange={(id) => {
        if (!id) {
          onChange?.(null);
          return;
        }
        const summary = items.find((it) => it.id === id);
        onChange?.(id, summary);
      }}
      optionLabelProp="label"
      options={items.map((it) => ({
        value: it.id,
        label: it.name,
        children: (
          <Space>
            <Text strong>{it.name}</Text>
            <Tag color="blue">v{it.version}</Tag>
            <Tag>{it.kind}</Tag>
            <Text type="secondary">{it.specs.length} specs</Text>
          </Space>
        ),
      }))}
    />
  );
}
