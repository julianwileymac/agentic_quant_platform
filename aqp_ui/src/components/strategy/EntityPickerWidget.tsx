"use client";

import type { WidgetProps } from "@rjsf/utils";

import { EntityPicker, type CacheCategory } from "@/components/common/EntityPicker";

/**
 * RJSF custom widget that delegates to EntityPicker.
 *
 * Bound to schema fields via uiSchema `"ui:widget": "EntityPickerWidget"`.
 *
 * AGENTS rule 8: credentials and other entity-typed fields MUST use a
 * whitelist-backed picker. This widget is the bridge between RJSF and
 * the cache-backed picker that aqp_client uses everywhere.
 */
export function EntityPickerWidget(props: WidgetProps) {
  const kind = (props.options?.kind as CacheCategory | undefined) ?? "credentials";
  return (
    <EntityPicker
      kind={kind}
      value={(props.value as string | undefined) ?? null}
      onChange={(value) => props.onChange(value ?? "")}
      disabled={props.disabled || props.readonly}
    />
  );
}
