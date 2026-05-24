import Link from "next/link";

import { authConfig } from "@/lib/auth/config";
import { ProviderPicker } from "@/components/auth/ProviderPicker";

interface PageProps {
  searchParams: Promise<{ returnTo?: string; org?: string }>;
}

export default async function SignupPage({ searchParams }: PageProps) {
  const params = await searchParams;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Create your AQP account
        </h1>
        <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          Self-signup with email creates a new organization for you. If your
          company already uses Microsoft Entra ID for sign-in, choose the
          enterprise option and an admin will link your tenant.
        </p>
      </div>

      <ProviderPicker
        mode="signup"
        returnTo={params.returnTo}
        organization={params.org}
        auth0Enabled={authConfig.auth0.enabled}
        entraEnabled={authConfig.entra.enabled}
      />

      <div className="text-center text-sm" style={{ color: "var(--text-secondary)" }}>
        Already have an account?{" "}
        <Link href="/login" style={{ color: "var(--accent-primary)" }}>
          Log in
        </Link>
      </div>

      <div className="rounded-md border p-3 text-xs" style={{ borderColor: "var(--border-default)", color: "var(--text-muted)" }}>
        By creating an account you agree to our{" "}
        <Link href="/legal/terms" style={{ color: "var(--text-secondary)" }}>
          Terms of Service
        </Link>{" "}
        and{" "}
        <Link href="/legal/privacy" style={{ color: "var(--text-secondary)" }}>
          Privacy Policy
        </Link>
        .
      </div>
    </div>
  );
}
