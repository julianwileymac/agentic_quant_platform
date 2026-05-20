import { ArrowLeft, MessageSquareQuote, Scale } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useApiQuery } from "@/lib/api/hooks";

interface DebateTurn {
  role: "bull" | "bear" | "portfolio_manager" | "moderator";
  content: string;
  confidence?: number | null;
  timestamp?: string;
  rationale?: string;
}

interface DebateRecord {
  id: string;
  bot_id: string;
  proposed_alpha?: Record<string, unknown> | null;
  simulation_verdict?: Record<string, unknown> | null;
  bull_argument?: DebateTurn | null;
  bear_argument?: DebateTurn | null;
  portfolio_verdict?: Record<string, unknown> | null;
  status?: string;
  created_at?: string;
}

/**
 * Bot Lab debate transcript viewer.
 *
 * Reads the dialectical debate trace produced by
 * :func:`build_dialectical_debate_graph` (Phase 4) and shows a
 * side-by-side bull / bear transcript with the portfolio manager's
 * synthesised verdict at the bottom.
 *
 * The endpoint shape ``GET /bots/{id}/debate`` is part of the
 * generic agent-runs API: when the route returns 404 the page
 * gracefully degrades to a "no debate runs yet" empty state.
 */
export function BotDebateRoute() {
  const params = useParams<{ id: string }>();
  const botId = params.id ?? "";

  const debateQuery = useApiQuery<DebateRecord[]>({
    queryKey: ["bots", botId, "debate"],
    path: `/bots/${encodeURIComponent(botId)}/debate`,
    select: (raw) => (Array.isArray(raw) ? (raw as DebateRecord[]) : []),
    enabled: Boolean(botId),
  });

  const debates = debateQuery.data ?? [];
  const latest = debates[0];

  return (
    <PageContainer
      title="Dialectical debate"
      subtitle={`Bull / Bear / PortfolioManager transcript for bot ${botId}`}
      extra={
        <Button asChild variant="outline" size="sm">
          <Link to={`/bots/${encodeURIComponent(botId)}`}>
            <ArrowLeft className="h-4 w-4" /> Back to bot
          </Link>
        </Button>
      }
    >
      {debateQuery.isPending ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-[var(--text-muted)]">
            Loading debate transcripts…
          </CardContent>
        </Card>
      ) : !latest ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-12 text-center">
            <MessageSquareQuote className="h-8 w-8 text-[var(--text-muted)]" />
            <div className="text-sm font-medium">No debates recorded yet</div>
            <div className="max-w-md text-xs text-[var(--text-muted)]">
              Trigger the dialectical-debate agent graph from the bot detail page,
              or run an iterative-optimisation cycle. The bull / bear / portfolio
              manager transcript will appear here.
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Scale className="h-4 w-4" /> Latest debate verdict
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Verdict verdict={latest.portfolio_verdict ?? null} />
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <DebateColumn
              title="Bull case"
              tone="positive"
              turn={latest.bull_argument ?? null}
            />
            <DebateColumn
              title="Bear case"
              tone="negative"
              turn={latest.bear_argument ?? null}
            />
          </div>

          {debates.length > 1 ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Earlier debates</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-xs">
                {debates.slice(1, 6).map((row) => (
                  <div
                    key={row.id}
                    className="flex items-center justify-between rounded border border-[var(--border-default)] p-2"
                  >
                    <span className="font-mono">{row.id}</span>
                    <Badge variant="secondary">{row.status ?? "completed"}</Badge>
                    <span className="text-[var(--text-muted)]">
                      {row.created_at ?? ""}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}
    </PageContainer>
  );
}

function DebateColumn({
  title,
  tone,
  turn,
}: {
  title: string;
  tone: "positive" | "negative";
  turn: DebateTurn | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-sm">
          <span>{title}</span>
          <Badge variant={tone}>{tone === "positive" ? "BULL" : "BEAR"}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {turn ? (
          <>
            {typeof turn.confidence === "number" ? (
              <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                <span>Confidence</span>
                <span className="font-mono">{(turn.confidence * 100).toFixed(0)}%</span>
              </div>
            ) : null}
            {turn.rationale ? (
              <p className="whitespace-pre-wrap text-sm">{turn.rationale}</p>
            ) : null}
            {turn.content ? (
              <>
                <Separator />
                <p className="whitespace-pre-wrap text-xs text-[var(--text-secondary)]">
                  {turn.content}
                </p>
              </>
            ) : null}
          </>
        ) : (
          <span className="text-xs text-[var(--text-muted)]">No turn recorded</span>
        )}
      </CardContent>
    </Card>
  );
}

function Verdict({ verdict }: { verdict: Record<string, unknown> | null }) {
  if (!verdict) {
    return <span className="text-xs text-[var(--text-muted)]">No verdict yet</span>;
  }
  const action = String((verdict as { action?: string }).action ?? "hold");
  const rationale = String((verdict as { rationale?: string }).rationale ?? "");
  const bull = (verdict as { bull_confidence?: number }).bull_confidence;
  const bear = (verdict as { bear_confidence?: number }).bear_confidence;
  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex items-center gap-2">
        <Badge
          variant={action === "buy" ? "positive" : action === "sell" ? "negative" : "secondary"}
          className="uppercase"
        >
          {action}
        </Badge>
        <span className="text-xs text-[var(--text-muted)]">
          bull {(typeof bull === "number" ? bull * 100 : 0).toFixed(0)}% / bear{" "}
          {(typeof bear === "number" ? bear * 100 : 0).toFixed(0)}%
        </span>
      </div>
      {rationale ? <p className="whitespace-pre-wrap">{rationale}</p> : null}
    </div>
  );
}
