import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";

interface Props {
  /** ``null`` means the wrapper is disabled (no truncation penalty). */
  value: number | null;
  onChange: (value: number | null) => void;
}

/**
 * Phase B control for the FinRL-X "stop properly" penalty
 * coefficient (`coef in [0, 1]`). Native range input — no shadcn
 * slider primitive exists in this codebase. ``coef=null`` disables
 * the wrapper entirely; ``coef=0`` zeroes truncated rewards;
 * ``coef=1`` is a no-op (telemetry only).
 */
export function StopProperlyPenaltyControl({ value, onChange }: Props) {
  const enabled = value !== null;
  const numericValue = enabled ? Math.max(0, Math.min(1, value as number)) : 0;
  const label = enabled
    ? numericValue === 0
      ? "draconian (zero)"
      : numericValue === 1
        ? "telemetry only"
        : `coef = ${numericValue.toFixed(2)}`
    : "disabled";
  return (
    <div className="grid gap-2 rounded border border-[var(--border-default)] p-3">
      <div className="flex items-center justify-between">
        <Label htmlFor="stop-properly-coef" className="text-sm">
          Stop-properly penalty
        </Label>
        <Badge variant={enabled ? "secondary" : "outline"}>{label}</Badge>
      </div>
      <div className="flex items-center gap-2">
        <input
          id="stop-properly-toggle"
          type="checkbox"
          checked={enabled}
          onChange={(e) => onChange(e.target.checked ? 0.0 : null)}
          className="h-4 w-4"
        />
        <span className="text-xs text-[var(--text-secondary)]">enable</span>
        <input
          id="stop-properly-coef"
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={numericValue}
          onChange={(e) => onChange(Number(e.target.value))}
          disabled={!enabled}
          className="flex-1"
        />
        <span className="w-12 text-right font-mono text-xs">
          {numericValue.toFixed(2)}
        </span>
      </div>
      <p className="text-[11px] text-[var(--text-secondary)]">
        Scales the reward of any truncated step (hard risk breach) by the
        chosen coefficient. <code>0</code> = draconian zeroing,{" "}
        <code>1</code> = telemetry-only, anywhere between for graceful
        degradation.
      </p>
    </div>
  );
}
