import Link from "next/link";

import { authConfig } from "@/lib/auth/config";
import { ProviderPicker } from "@/components/auth/ProviderPicker";

interface PageProps {
  searchParams: Promise<{ returnTo?: string; org?: string }>;
}

export default async function LoginPage({ searchParams }: PageProps) {
  const params = await searchParams;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Welcome back
        </h1>
        <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
          Sign in with the same provider you used to create your account.
        </p>
      </div>

      <ProviderPicker
        mode="login"
        returnTo={params.returnTo}
        organization={params.org}
        auth0Enabled={authConfig.auth0.enabled}
        entraEnabled={authConfig.entra.enabled}
      />

      <div className="text-center text-sm" style={{ color: "var(--text-secondary)" }}>
        Don't have an account?{" "}
        <Link href="/signup" style={{ color: "var(--accent-primary)" }}>
          Sign up
        </Link>
      </div>
    </div>
  );
}
