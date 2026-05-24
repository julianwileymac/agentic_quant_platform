import Link from "next/link";
import { TrendingUp } from "lucide-react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ background: "var(--bg-app)" }}
    >
      <header className="flex items-center justify-between px-6 py-4">
        <Link
          href="/"
          className="flex items-center gap-2"
          style={{ color: "var(--text-primary)" }}
        >
          <TrendingUp size={20} />
          <span className="text-lg font-semibold tracking-tight">AQP</span>
        </Link>
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          Secure authentication
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center px-6 py-12">
        <div
          className="w-full max-w-md rounded-lg border p-8"
          style={{
            background: "var(--bg-surface)",
            borderColor: "var(--border-default)",
          }}
        >
          {children}
        </div>
      </main>
    </div>
  );
}
