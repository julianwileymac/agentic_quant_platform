import Link from "next/link";
import { AlertCircle, Building2, Clock, CheckCircle2 } from "lucide-react";

interface PageProps {
  searchParams: Promise<{ status?: string }>;
}

type LinkStatus = "missing" | "pending" | "active" | "revoked" | "suspended" | "unknown";

export default async function EntraTenantLinkPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const status = (params.status ?? "unknown") as LinkStatus;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Building2 size={24} style={{ color: "var(--accent-primary)" }} />
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Microsoft Entra tenant link
        </h1>
      </div>

      <StatusCard status={status} />

      <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
        AQP never auto-provisions an organization from a raw tenant ID — the{" "}
        <code>EntraTenantLink</code> table requires an AQP super-admin to
        approve your tenant before any data is provisioned. This is by design
        to protect cross-tenant data isolation.
      </div>

      <div className="flex flex-col gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
        <div>Next steps:</div>
        <ol className="ml-5 list-decimal space-y-1">
          <li>An AQP admin reviews your tenant link request.</li>
          <li>Once approved, you choose a tenancy strategy (RLS, schema-per-tenant, or db-per-enterprise).</li>
          <li>You receive an email; sign in again to enter the dashboard.</li>
        </ol>
      </div>

      <Link
        href="/"
        className="rounded-md border px-4 py-2 text-center text-sm"
        style={{
          borderColor: "var(--border-default)",
          color: "var(--text-primary)",
        }}
      >
        Return to home
      </Link>
    </div>
  );
}

function StatusCard({ status }: { status: LinkStatus }) {
  const config: Record<
    LinkStatus,
    {
      Icon: typeof AlertCircle;
      color: string;
      title: string;
      body: string;
    }
  > = {
    missing: {
      Icon: AlertCircle,
      color: "var(--warn-fg)",
      title: "No link found for your tenant",
      body: "Your Microsoft Entra tenant has not been registered with AQP. Contact your AQP account manager or sign up at /signup to create a new organization.",
    },
    pending: {
      Icon: Clock,
      color: "var(--info-fg)",
      title: "Your tenant link is pending approval",
      body: "We've received your request and an AQP super-admin will review it shortly. You'll receive an email when your tenant is approved.",
    },
    active: {
      Icon: CheckCircle2,
      color: "var(--pos-fg)",
      title: "Your tenant is linked and active",
      body: "Welcome to AQP — head to the dashboard to get started.",
    },
    revoked: {
      Icon: AlertCircle,
      color: "var(--neg-fg)",
      title: "Your tenant link has been revoked",
      body: "Access for this tenant has been revoked. Contact AQP support if you believe this is in error.",
    },
    suspended: {
      Icon: AlertCircle,
      color: "var(--warn-fg)",
      title: "Your tenant link is suspended",
      body: "Sign-in has been suspended for this tenant. Contact your AQP account manager.",
    },
    unknown: {
      Icon: AlertCircle,
      color: "var(--text-muted)",
      title: "We could not verify your tenant link",
      body: "We couldn't reach the AQP backend. Please retry sign-in, and contact support if the issue persists.",
    },
  };

  const c = config[status];

  return (
    <div
      className="flex items-start gap-3 rounded-md border p-4"
      style={{ borderColor: "var(--border-default)", background: "var(--bg-elevated)" }}
    >
      <c.Icon size={20} style={{ color: c.color, flexShrink: 0 }} />
      <div>
        <div className="text-sm font-semibold" style={{ color: c.color }}>
          {c.title}
        </div>
        <div className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          {c.body}
        </div>
      </div>
    </div>
  );
}
