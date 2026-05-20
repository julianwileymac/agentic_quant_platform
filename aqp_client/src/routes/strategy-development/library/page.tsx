import { Library } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";

interface ComponentRow {
  name: string;
  kind: string;
  module_path: string;
  source?: string | null;
  category?: string | null;
  tags?: string[];
}

/**
 * Registered strategy / alpha / portfolio / risk component browser.
 * Hits `GET /strategies/components` which the backend exposes as a
 * thin wrapper around `aqp.core.registry.list_by_kind`. Read-only.
 */
export function StrategyLibraryRoute() {
  const data = useApiQuery<ComponentRow[]>({
    queryKey: ["strategies", "components", "browser"],
    path: "/strategies/components",
    select: (raw): ComponentRow[] => {
      if (Array.isArray(raw)) return raw as ComponentRow[];
      const obj = raw as { components?: ComponentRow[] } | undefined;
      return Array.isArray(obj?.components) ? obj!.components! : [];
    },
    staleTime: 60_000,
  });

  const groupedByKind: Record<string, ComponentRow[]> = {};
  for (const row of data.data ?? []) {
    (groupedByKind[row.kind || "other"] ??= []).push(row);
  }

  return (
    <div className="h-full overflow-auto">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {Object.entries(groupedByKind)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([kind, rows]) => (
            <Card key={kind}>
              <CardHeader>
                <CardTitle>
                  <div className="flex items-center gap-2">
                    <Library className="h-3.5 w-3.5" />
                    <span>{kind}</span>
                    <Badge variant="outline" className="text-[10px]">
                      {rows.length}
                    </Badge>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col gap-1">
                  {rows.map((row) => (
                    <li
                      key={`${row.kind}:${row.name}`}
                      className="rounded-md border border-[var(--border-default)] p-2 text-[11px]"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-medium">{row.name}</span>
                        {row.source ? (
                          <Badge variant="secondary" className="text-[9px]">
                            {row.source}
                          </Badge>
                        ) : null}
                      </div>
                      <div className="truncate font-mono text-[10px] text-[var(--text-secondary)]">
                        {row.module_path}
                      </div>
                      {row.tags?.length ? (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {row.tags.slice(0, 4).map((t) => (
                            <Badge key={t} variant="outline" className="text-[9px]">
                              {t}
                            </Badge>
                          ))}
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        {data.isLoading ? (
          <Card>
            <CardContent className="py-12 text-center text-xs text-[var(--text-secondary)]">
              Loading components…
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
