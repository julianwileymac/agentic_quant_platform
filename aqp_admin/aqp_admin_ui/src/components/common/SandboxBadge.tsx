/**
 * Sandbox indicator badge.
 *
 * Mirrors the aqp_client SandboxBadge so operators can tell at a
 * glance whether they're looking at production data or a dev
 * sandbox. Reads the same env var (``VITE_AQP_SANDBOX``); the badge
 * stays invisible when unset so prod renders cleanly.
 */
export function SandboxBadge() {
  const env = (import.meta as { env?: Record<string, string> }).env ?? {};
  const processEnv =
    (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ??
    {};
  const sandbox =
    env.VITE_AQP_SANDBOX ||
    env.VITE_ADMIN_SANDBOX ||
    processEnv.VITE_AQP_SANDBOX ||
    processEnv.VITE_ADMIN_SANDBOX;
  if (!sandbox) return null;
  return (
    <span className="ml-2 inline-flex items-center rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
      SANDBOX{sandbox === "1" || sandbox === "true" ? "" : `: ${sandbox}`}
    </span>
  );
}
