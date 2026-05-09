import { ArrowLeft, FlaskConical, NotebookPen } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { BOT_NODE_ACCENTS, BOT_PALETTE } from "@/components/bots/botPalette";
import { deserializeBotSpec, serializeBotSpec, slugify } from "@/components/bots/botSerializer";
import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { BotsApi, type BotDetail, type BotKind } from "@/lib/api/bots";
import { useTenancyStore } from "@/store/tenancy";

const KIND_OPTIONS: BotKind[] = ["trading", "research"];

interface PendingSave {
  graph: FlowGraph;
  run: boolean;
}

export function BotBuilderRoute() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const mode = useTenancyStore((s) => s.mode);
  const id = searchParams.get("id");

  const bot = useApiQuery<BotDetail>({
    queryKey: ["bot-builder", id],
    path: `/bots/${encodeURIComponent(id ?? "")}`,
    enabled: Boolean(id),
  });

  const [name, setName] = useState("");
  const [kind, setKind] = useState<BotKind>("trading");
  const [description, setDescription] = useState("");
  const [pending, setPending] = useState<PendingSave | null>(null);
  const [saving, setSaving] = useState(false);

  // Hydrate metadata + initial graph once the bot loads.
  const initialGraph = useMemo<FlowGraph | undefined>(() => {
    if (!bot.data) return undefined;
    if (!name) setName(bot.data.name);
    if (kind !== bot.data.kind && KIND_OPTIONS.includes(bot.data.kind as BotKind)) {
      setKind(bot.data.kind as BotKind);
    }
    if (!description && bot.data.description) setDescription(bot.data.description);
    return deserializeBotSpec(bot.data.spec ?? {});
  }, [bot.data, name, kind, description]);

  const submit = async () => {
    if (!pending) return;
    if (!name.trim()) {
      toast.error("Provide a bot name before saving");
      return;
    }
    setSaving(true);
    try {
      const spec = serializeBotSpec(pending.graph, {
        name: name.trim(),
        slug: slugify(name.trim()),
        kind,
        description: description.trim(),
      });
      let saved: BotDetail;
      if (id) {
        saved = await BotsApi.update(id, { spec });
        toast.success(`${saved.name} updated`);
      } else {
        saved = await BotsApi.create(spec);
        toast.success(`${saved.name} created`);
      }
      if (pending.run) {
        await BotsApi.backtest(saved.id);
        toast.success("Backtest queued");
      }
      navigate(`/bots/${saved.id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Save failed: ${msg}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageContainer
      title={id ? `Bot Builder — ${name || id}` : "New bot (visual builder)"}
      subtitle={
        <span className="font-mono text-xs">
          {id ? `editing ${id}` : "drop palette tiles to compose a BotSpec"}
        </span>
      }
      extra={
        <div className="flex items-center gap-2">
          <Badge variant={mode === "live" ? "warn" : "secondary"} className="uppercase">
            {mode}
          </Badge>
          <Button asChild variant="ghost" size="sm">
            <Link to="/bots/new">
              <NotebookPen className="h-4 w-4" /> Form mode
            </Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link to={id ? `/bots/${id}` : "/bots"}>
              <ArrowLeft className="h-4 w-4" /> {id ? "Bot detail" : "All bots"}
            </Link>
          </Button>
        </div>
      }
      bleed
    >
      <div className="flex h-[calc(100vh-160px)] flex-col gap-3 px-6 pb-6">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
          <div className="flex flex-col gap-1">
            <Label htmlFor="bb-name">Name</Label>
            <Input id="bb-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label>Kind</Label>
            <div className="grid grid-cols-2 gap-1">
              {KIND_OPTIONS.map((opt) => (
                <Button
                  key={opt}
                  type="button"
                  size="sm"
                  variant={kind === opt ? "default" : "outline"}
                  onClick={() => setKind(opt)}
                  className="capitalize"
                >
                  {opt}
                </Button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="bb-desc">Description</Label>
            <Input id="bb-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          {bot.isPending && id ? (
            <span className="self-end text-xs text-[var(--text-secondary)]">Loading bot…</span>
          ) : null}
        </div>

        <div className="min-h-0 flex-1">
          <WorkflowEditor
            domain="bot"
            paletteSections={BOT_PALETTE}
            accentByKind={BOT_NODE_ACCENTS}
            {...(initialGraph ? { initialGraph } : {})}
            onSave={async (graph) => setPending({ graph, run: false })}
            onRun={async (graph) => setPending({ graph, run: true })}
            saving={saving}
          />
        </div>
      </div>

      {pending ? (
        <ConfirmFrictionDialog
          open={pending != null}
          onOpenChange={(open) => {
            if (!open) setPending(null);
          }}
          title={pending.run ? `Save and run backtest — ${name}` : `Save bot — ${name}`}
          consequence={
            pending.run
              ? "Persists the spec as a new immutable bot_versions row, then queues a backtest against the current configuration."
              : id
                ? "Persists a new immutable bot_versions row with the current spec hash. Existing version rows are not modified."
                : "Creates a new bot with the current spec. The spec is hashed and stored on bot_versions; lifecycle actions are available from the bot detail page."
          }
          details={[
            { label: "Name", value: name },
            { label: "Kind", value: kind },
            { label: "Nodes", value: pending.graph.nodes.length },
            { label: "Edges", value: pending.graph.edges.length },
            { label: "Mode", value: mode.toUpperCase(), tone: mode === "live" ? "warn" : "neutral" },
          ]}
          confirmPhrase=""
          confirmLabel={pending.run ? "Save and queue backtest" : id ? "Save bot" : "Create bot"}
          confirmVariant="default"
          onConfirm={submit}
        >
          {pending.run ? (
            <p className="text-xs text-[var(--text-secondary)]">
              <FlaskConical className="mr-1 inline h-3 w-3" /> Backtest task id will be returned in
              the toast; tail progress on the bot detail page.
            </p>
          ) : null}
        </ConfirmFrictionDialog>
      ) : null}
    </PageContainer>
  );
}
