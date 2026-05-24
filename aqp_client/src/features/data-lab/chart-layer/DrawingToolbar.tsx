import {
  MousePointer,
  Pen,
  Square,
  Trash2,
  TrendingUp,
  Triangle,
  Wand2,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";

export type DrawingTool =
  | "select"
  | "support_resistance"
  | "trendline"
  | "swing"
  | "regime_band"
  | "pattern"
  | "annotation";

interface DrawingToolbarProps {
  labId: string | null;
  vtSymbol: string | null;
  activeTool: DrawingTool;
  onToolChange: (tool: DrawingTool) => void;
  /** Optional run id to bind the in-progress drawing to a run row. */
  runId?: string | null;
}

const TOOLS: Array<{ id: DrawingTool; label: string; Icon: typeof Pen }> = [
  { id: "select", label: "Select", Icon: MousePointer },
  { id: "support_resistance", label: "Support / Resistance", Icon: Pen },
  { id: "trendline", label: "Trendline", Icon: TrendingUp },
  { id: "swing", label: "Swing pick", Icon: Triangle },
  { id: "regime_band", label: "Regime band", Icon: Square },
  { id: "pattern", label: "Pattern polygon", Icon: Pen },
  { id: "annotation", label: "Free annotation", Icon: Pen },
];

/**
 * Drawing toolbar overlay rendered above the OHLC chart.
 *
 * Phase 5 ships the tool palette + the "Train labeler" wizard
 * trigger (which reuses the existing ``POST /lab/labelers/train``
 * endpoint). The chart canvas itself (lightweight-charts) listens to
 * mouse events when ``activeTool`` is non-select; the toolbar is
 * intentionally tiny — it owns the tool state and the
 * train-labeler action, nothing else.
 */
export function DrawingToolbar({
  labId,
  vtSymbol,
  activeTool,
  onToolChange,
  runId,
}: DrawingToolbarProps) {
  const [training, setTraining] = useState(false);

  const handleTrainLabeler = async () => {
    if (!labId) {
      toast.error("Select a lab before training a labeler.");
      return;
    }
    if (!vtSymbol) {
      toast.error("Pick a symbol on the chart first.");
      return;
    }
    setTraining(true);
    try {
      const graph = await apiFetch<{ id: string; name: string }>(
        "/lab/labelers/train",
        {
          method: "POST",
          body: JSON.stringify({
            lab_id: labId,
            vt_symbol: vtSymbol,
            label_kind: activeTool === "select" ? "swing" : activeTool,
          }),
        },
      );
      toast.success(
        `Train-labeler graph ${graph.name} created — open Testing mode to inspect.`,
      );
    } catch (err) {
      toast.error(
        `Train labeler failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    } finally {
      setTraining(false);
    }
  };

  return (
    <div className="pointer-events-auto flex items-center gap-1 rounded-md border bg-background/95 p-1 shadow">
      {TOOLS.map(({ id, label, Icon }) => (
        <Button
          key={id}
          variant={activeTool === id ? "default" : "ghost"}
          size="sm"
          className="h-7 gap-1 px-2"
          onClick={() => onToolChange(id)}
          title={label}
        >
          <Icon className="h-3.5 w-3.5" />
        </Button>
      ))}
      <div className="ml-1 h-5 w-px bg-border" />
      <Button
        variant="ghost"
        size="sm"
        className="h-7 gap-1 px-2"
        disabled={training || !labId || !vtSymbol}
        onClick={handleTrainLabeler}
        title="Train a meta-labeler on the labels you've drawn for this symbol."
      >
        <Wand2 className="h-3.5 w-3.5" /> Train
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 gap-1 px-2"
        onClick={() => onToolChange("select")}
        title="Clear active tool"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
      {runId ? (
        <Badge variant="outline" className="ml-2 font-mono text-[10px]">
          run {runId.slice(0, 8)}
        </Badge>
      ) : null}
    </div>
  );
}

export default DrawingToolbar;
