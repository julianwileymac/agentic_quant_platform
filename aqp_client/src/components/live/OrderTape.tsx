import { Numeric } from "@/components/common/Numeric";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useRecentEvents } from "@/store/market";
import { formatTime } from "@/lib/utils";

interface OrderTapeProps {
  symbol: string;
  /** Maximum rows shown. Defaults to 64. */
  rows?: number;
}

/**
 * Live order tape — flips through every event in the market store
 * for the selected symbol. Subscribes via `useRecentEvents` which uses
 * a shallow selector so the component only re-renders when the buffer
 * actually changes (not on unrelated symbols).
 */
export function OrderTape({ symbol, rows = 64 }: OrderTapeProps) {
  const events = useRecentEvents(rows);
  const filtered = events.filter((e) => e.vt_symbol === symbol).slice(-rows).reverse();

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Tape · {symbol}</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="max-h-72">
          <ul className="divide-y divide-[var(--border-subtle)]">
            {filtered.length === 0 ? (
              <li className="px-4 py-3 text-center text-xs text-[var(--text-secondary)]">
                Waiting for ticks…
              </li>
            ) : (
              filtered.map((e, idx) => {
                const ts = formatTime(e.timestamp);
                if (e.kind === "tick") {
                  return (
                    <li key={`${ts}-${idx}`} className="grid grid-cols-4 px-4 py-1 text-[11px] tabular">
                      <span className="text-[var(--text-secondary)]">{ts}</span>
                      <span>tick</span>
                      <span className="text-right">
                        <Numeric value={e.last} kind="decimal" digits={2} color="auto" />
                      </span>
                      <span className="text-right">
                        <Numeric value={e.volume} kind="integer" digits={0} color="neutral" />
                      </span>
                    </li>
                  );
                }
                if (e.kind === "quote") {
                  return (
                    <li key={`${ts}-${idx}`} className="grid grid-cols-4 px-4 py-1 text-[11px] tabular">
                      <span className="text-[var(--text-secondary)]">{ts}</span>
                      <span>quote</span>
                      <span className="text-right">
                        <Numeric value={e.bid_close} kind="decimal" digits={2} color="force-pos" />
                      </span>
                      <span className="text-right">
                        <Numeric value={e.ask_close} kind="decimal" digits={2} color="force-neg" />
                      </span>
                    </li>
                  );
                }
                if (e.kind === "bar") {
                  return (
                    <li key={`${ts}-${idx}`} className="grid grid-cols-4 px-4 py-1 text-[11px] tabular">
                      <span className="text-[var(--text-secondary)]">{ts}</span>
                      <span>bar</span>
                      <span className="text-right">
                        <Numeric value={e.close} kind="decimal" digits={2} color="auto" />
                      </span>
                      <span className="text-right">
                        <Numeric value={e.volume} kind="integer" digits={0} color="neutral" />
                      </span>
                    </li>
                  );
                }
                return (
                  <li key={`${ts}-${idx}`} className="grid grid-cols-4 px-4 py-1 text-[11px] tabular">
                    <span className="text-[var(--text-secondary)]">{ts}</span>
                    <span>signal</span>
                    <span className="text-right">{e.direction}</span>
                    <span className="text-right">
                      <Numeric value={e.confidence} kind="percent" digits={1} color="auto" />
                    </span>
                  </li>
                );
              })
            )}
          </ul>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
