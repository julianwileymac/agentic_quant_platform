/**
 * Sandbox indicator badge.
 *
 * Mirrors the aqp_client SandboxBadge so operators can tell at a
 * glance whether they're looking at production data or a dev
 * sandbox. Reads `NEXT_PUBLIC_AQP_SANDBOX` (Next.js convention) and
 * the legacy `VITE_AQP_SANDBOX` fallback for tooling parity. The
 * badge stays invisible when unset so prod renders cleanly.
 */
export function SandboxBadge() {
  const sandbox =
    process.env.NEXT_PUBLIC_AQP_SANDBOX ||
    process.env.NEXT_PUBLIC_ADMIN_SANDBOX ||
    process.env.VITE_AQP_SANDBOX;
  if (!sandbox) return null;
  return (
    <span className="ml-2 inline-flex items-center rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
      SANDBOX{sandbox === "1" || sandbox === "true" ? "" : `: ${sandbox}`}
    </span>
  );
}
