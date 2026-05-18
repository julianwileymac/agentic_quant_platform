import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { MetadataLineageGraph } from "@/components/metadata/MetadataLineageGraph";
import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  metadataLineage,
  type LineageDirection,
} from "@/lib/api/metadata-aspects";

export function MetadataAspectLineageRoute() {
  const { urn: rawUrn = "" } = useParams<{ urn: string }>();
  const urn = safeDecode(rawUrn);
  const [depth, setDepth] = useState(3);
  const [direction, setDirection] = useState<LineageDirection>("both");
  const lineageQuery = useQuery({
    queryKey: ["metadata-aspects", "lineage", urn, depth, direction],
    queryFn: () =>
      metadataLineage(urn, {
        depth,
        direction,
      }),
    enabled: urn.length > 0,
  });

  return (
    <PageContainer
      title="Metadata Lineage Graph"
      subtitle={urn}
      extra={
        <Button asChild variant="outline" size="sm">
          <Link to={`/metadata/aspects/${encodeURIComponent(urn)}`}>
            Back to entity
          </Link>
        </Button>
      }
    >
      <div className="flex h-full min-h-0 flex-col gap-3">
        <Card>
          <CardHeader>
            <CardTitle>Traversal Controls</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <div className="min-w-[260px]">
              <p className="text-xs text-[var(--text-muted)]">
                Depth: <span className="font-mono tabular-nums">{depth}</span>
              </p>
              <input
                type="range"
                min={1}
                max={10}
                value={depth}
                onChange={(event) => setDepth(Number(event.target.value))}
                className="w-full"
              />
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant={direction === "upstream" ? "secondary" : "outline"}
                size="sm"
                onClick={() => setDirection("upstream")}
              >
                Upstream
              </Button>
              <Button
                variant={direction === "downstream" ? "secondary" : "outline"}
                size="sm"
                onClick={() => setDirection("downstream")}
              >
                Downstream
              </Button>
              <Button
                variant={direction === "both" ? "secondary" : "outline"}
                size="sm"
                onClick={() => setDirection("both")}
              >
                Both
              </Button>
            </div>
          </CardContent>
        </Card>
        <MetadataLineageGraph lineage={lineageQuery.data ?? null} />
      </div>
    </PageContainer>
  );
}

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
