import { useApiQuery } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

import { Label } from "@/components/ui/label";

export interface DeploymentRow {
  id: string;
  name: string;
  status: string;
  alpha_class?: string | null;
}

interface DeploymentPickerProps {
  value: string;
  onChange: (id: string) => void;
  label?: string;
  placeholder?: string;
  className?: string;
  /** Optional id of a deployment to exclude (used by compare side-B). */
  exclude?: string | null;
}

const SELECT_CLASSES =
  "h-9 w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm text-[var(--text-primary)]";

export function DeploymentPicker({
  value,
  onChange,
  label,
  placeholder = "Pick an active deployment",
  className,
  exclude,
}: DeploymentPickerProps) {
  const deployments = useApiQuery<DeploymentRow[]>({
    queryKey: ["ml", "deployments"],
    path: "/ml/deployments",
    select: (raw) => (Array.isArray(raw) ? (raw as DeploymentRow[]) : []),
    staleTime: 30_000,
  });
  const items = (deployments.data ?? []).filter((d) => d.id !== exclude);

  return (
    <div className={cn("space-y-1", className)}>
      {label ? <Label>{label}</Label> : null}
      <select
        className={SELECT_CLASSES}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{placeholder}</option>
        {items.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name} ({d.status})
          </option>
        ))}
      </select>
    </div>
  );
}
