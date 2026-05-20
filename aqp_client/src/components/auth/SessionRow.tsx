import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import {
  Clock3,
  Laptop,
  MapPin,
  Monitor,
  Smartphone,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Session } from "@/lib/api/me";
import { cn } from "@/lib/utils";

dayjs.extend(relativeTime);

interface SessionRowProps {
  session: Session;
  isCurrent: boolean;
  onRevoke: () => Promise<void> | void;
}

function DeviceIcon({ session }: { session: Session }) {
  const haystack = `${session.device ?? ""} ${session.user_agent ?? ""}`.toLowerCase();
  if (haystack.includes("iphone") || haystack.includes("android") || haystack.includes("mobile")) {
    return <Smartphone className="size-4 text-[var(--text-secondary)]" />;
  }
  if (haystack.includes("windows") || haystack.includes("mac") || haystack.includes("linux")) {
    return <Laptop className="size-4 text-[var(--text-secondary)]" />;
  }
  return <Monitor className="size-4 text-[var(--text-secondary)]" />;
}

export function SessionRow({ session, isCurrent, onRevoke }: SessionRowProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState(false);

  const handleRevoke = async () => {
    if (pending) return;
    setPending(true);
    try {
      await onRevoke();
      setConfirmOpen(false);
    } finally {
      setPending(false);
    }
  };

  const activityLabel = session.last_activity
    ? dayjs(session.last_activity).fromNow()
    : "No recent activity";
  const deviceLabel = session.device ?? "Unknown device";
  const locationLabel = session.location ?? "Unknown location";

  return (
    <div
      className={cn(
        "relative grid gap-3 rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center",
        isCurrent && "border-[var(--info-fg)]",
      )}
    >
      <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <DeviceIcon session={session} />
            <span className="text-sm font-medium">{deviceLabel}</span>
            {isCurrent ? <Badge variant="outline">This session</Badge> : null}
          </div>
          <div className="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
            <MapPin className="size-3.5" />
            <span>{locationLabel}</span>
          </div>
        </div>

        <div className="space-y-1 text-xs text-[var(--text-secondary)]">
          <div>
            IP:{" "}
            <span className="font-mono text-[var(--text-primary)]">{session.ip ?? "Unknown"}</span>
          </div>
          <div className="flex items-center gap-1">
            <Clock3 className="size-3.5" />
            <span>{activityLabel}</span>
          </div>
        </div>
      </div>

      <div className="relative justify-self-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setConfirmOpen((value) => !value)}
          disabled={pending}
          className="border-[var(--neg-fg)] text-[var(--neg-fg)] hover:bg-[var(--neg-bg)]"
        >
          Revoke
        </Button>

        {confirmOpen ? (
          <div className="absolute right-0 z-10 mt-2 w-56 rounded-md border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 shadow-lg">
            <div className="mb-2 text-xs text-[var(--text-secondary)]">Sign out this session?</div>
            <div className="flex items-center justify-end gap-2">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setConfirmOpen(false)}
                disabled={pending}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                variant="destructive"
                onClick={() => void handleRevoke()}
                disabled={pending}
              >
                {pending ? "Revoking..." : "Revoke"}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
