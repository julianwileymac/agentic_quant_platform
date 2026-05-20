import { useVirtualizer } from "@tanstack/react-virtual";
import { type CSSProperties, useMemo, useRef } from "react";

import { Numeric } from "@/components/common/Numeric";
import { useLatestEvent } from "@/store/market";
import { cn } from "@/lib/utils";

export interface OrderBookLevel {
  price: number;
  size: number;
  /** Cumulative size at and through this level — drives the depth bar. */
  cumulative?: number;
}

interface OrderBookProps {
  symbol: string;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
  /** Number of rows shown per side. Excess levels are virtualized. */
  rowsVisible?: number;
}

/**
 * Virtualized two-sided order book. Each side mounts a separate
 * `useVirtualizer` so renders stay surgical. The mid-market price row
 * subscribes via `useLatestEvent(symbol)` so only the centre stripe
 * re-renders on tick — depth rows update only when the parent passes
 * a fresh book snapshot.
 */
export function OrderBook({ symbol, bids, asks, rowsVisible = 12 }: OrderBookProps) {
  const askParent = useRef<HTMLDivElement | null>(null);
  const bidParent = useRef<HTMLDivElement | null>(null);

  const sortedAsks = useMemo(() => [...asks].sort((a, b) => a.price - b.price), [asks]);
  const sortedBids = useMemo(() => [...bids].sort((a, b) => b.price - a.price), [bids]);
  const maxSize = useMemo(() => {
    const max = Math.max(
      0,
      ...sortedAsks.map((l) => l.cumulative ?? l.size),
      ...sortedBids.map((l) => l.cumulative ?? l.size),
    );
    return max || 1;
  }, [sortedAsks, sortedBids]);

  const askVirtualizer = useVirtualizer({
    count: sortedAsks.length,
    getScrollElement: () => askParent.current,
    estimateSize: () => 22,
    overscan: 6,
  });
  const bidVirtualizer = useVirtualizer({
    count: sortedBids.length,
    getScrollElement: () => bidParent.current,
    estimateSize: () => 22,
    overscan: 6,
  });

  const latest = useLatestEvent(symbol);
  const mid = useMemo(() => {
    if (!latest) return null;
    if (latest.kind === "quote") return (latest.bid_close + latest.ask_close) / 2;
    if (latest.kind === "tick") return latest.last;
    if (latest.kind === "bar") return latest.close;
    return null;
  }, [latest]);

  const askMaxHeight = rowsVisible * 22;
  const bidMaxHeight = rowsVisible * 22;

  return (
    <div className="flex h-full flex-col text-xs">
      <div className="grid grid-cols-3 border-b border-[var(--border-default)] px-3 py-1.5 text-[10px] uppercase tracking-wider text-[var(--text-secondary)]">
        <span>Price</span>
        <span className="text-right">Size</span>
        <span className="text-right">Depth</span>
      </div>
      <div ref={askParent} className="overflow-auto" style={{ maxHeight: askMaxHeight }}>
        <div style={{ height: askVirtualizer.getTotalSize() }} className="relative">
          {askVirtualizer.getVirtualItems().map((row) => {
            const level = sortedAsks[row.index];
            if (!level) return null;
            return (
              <DepthRow
                key={`a-${row.index}`}
                level={level}
                side="ask"
                maxSize={maxSize}
                style={{ position: "absolute", top: row.start, height: row.size, width: "100%" }}
              />
            );
          })}
        </div>
      </div>
      <div className="border-y border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-[var(--text-secondary)]">Mid</span>
          <Numeric value={mid} kind="decimal" digits={2} color="auto" />
        </div>
      </div>
      <div ref={bidParent} className="overflow-auto" style={{ maxHeight: bidMaxHeight }}>
        <div style={{ height: bidVirtualizer.getTotalSize() }} className="relative">
          {bidVirtualizer.getVirtualItems().map((row) => {
            const level = sortedBids[row.index];
            if (!level) return null;
            return (
              <DepthRow
                key={`b-${row.index}`}
                level={level}
                side="bid"
                maxSize={maxSize}
                style={{ position: "absolute", top: row.start, height: row.size, width: "100%" }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

interface DepthRowProps {
  level: OrderBookLevel;
  side: "bid" | "ask";
  maxSize: number;
  style: CSSProperties;
}

function DepthRow({ level, side, maxSize, style }: DepthRowProps) {
  const cumulative = level.cumulative ?? level.size;
  const fraction = Math.min(1, cumulative / maxSize);
  return (
    <div
      style={style}
      className={cn(
        "relative grid grid-cols-3 items-center px-3 text-xs tabular",
        "border-b border-[var(--border-subtle)]",
      )}
    >
      <span
        aria-hidden
        className="absolute inset-y-0 right-0"
        style={{
          width: `${(fraction * 100).toFixed(2)}%`,
          background: side === "ask" ? "rgba(239,68,68,0.10)" : "rgba(16,185,129,0.10)",
        }}
      />
      <Numeric
        value={level.price}
        kind="decimal"
        digits={2}
        color={side === "ask" ? "force-neg" : "force-pos"}
        className="relative z-10"
      />
      <span className="relative z-10 text-right text-[var(--text-primary)]">
        <Numeric value={level.size} kind="integer" digits={0} color="neutral" />
      </span>
      <span className="relative z-10 text-right text-[var(--text-secondary)]">
        <Numeric value={cumulative} kind="integer" digits={0} color="neutral" />
      </span>
    </div>
  );
}
