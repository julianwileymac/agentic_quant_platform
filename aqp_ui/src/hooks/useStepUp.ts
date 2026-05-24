"use client";

import { useCallback, useState } from "react";

import { ACR_MFA, isStepUpChallenge, parseWwwAuthenticate } from "@/lib/auth/stepUp";

/**
 * Client-side RFC 9470 step-up-MFA hook.
 *
 * Mirrors aqp_client/src/lib/auth/useStepUp.ts:
 *   - `requestStepUp` opens an Auth0 / Entra popup with `acr_values` +
 *     `max_age=0` to force a fresh MFA assertion.
 *   - `runWithStepUp` is the pre-flight wrapper for destructive buttons
 *     (kill switch, broker credential delete, invite revoke, etc.).
 *
 * When the upstream returns a step-up challenge in `WWW-Authenticate`,
 * `apiFetch` (called by client code that uses TanStack Query) retries
 * once after the user completes the MFA challenge.
 */

export interface StepUpHint {
  acrValues?: string;
  maxAge?: number;
}

export interface UseStepUpReturn {
  isSupported: boolean;
  isStepUpInFlight: boolean;
  requestStepUp: (hint?: StepUpHint) => Promise<void>;
}

export function useStepUp(): UseStepUpReturn {
  const [isStepUpInFlight, setStepUpInFlight] = useState(false);

  const requestStepUp = useCallback(async (hint?: StepUpHint) => {
    setStepUpInFlight(true);
    try {
      // Provider-agnostic step-up via the BFF: returns a redirect URL
      // and the client opens it in a popup. The BFF handler is added
      // in sprint 5 (`/api/auth/stepup`).
      const acr = hint?.acrValues ?? ACR_MFA;
      const maxAge = hint?.maxAge ?? 0;
      const url = `/api/auth/stepup?acr_values=${encodeURIComponent(acr)}&max_age=${maxAge}`;
      const popup = window.open(url, "aqp-stepup", "popup=yes,width=480,height=720");
      if (!popup) {
        throw new Error("Step-up popup blocked. Please allow popups for this site.");
      }
      await new Promise<void>((resolve, reject) => {
        const timer = setInterval(() => {
          if (popup.closed) {
            clearInterval(timer);
            resolve();
          }
        }, 250);
        const timeout = setTimeout(() => {
          clearInterval(timer);
          reject(new Error("Step-up timed out after 3 minutes"));
        }, 3 * 60_000);
        const cleanup = () => clearTimeout(timeout);
        popup.addEventListener?.("beforeunload", cleanup);
      });
    } finally {
      setStepUpInFlight(false);
    }
  }, []);

  return {
    isSupported: typeof window !== "undefined",
    isStepUpInFlight,
    requestStepUp,
  };
}

/**
 * Pre-flight a step-up popup, then run the destructive op. If the op
 * still throws a step-up error, retry once.
 */
export async function runWithStepUp<T>(
  requestStepUp: (hint?: StepUpHint) => Promise<void>,
  isSupported: boolean,
  op: () => Promise<T>,
  hint?: StepUpHint,
): Promise<T> {
  if (!isSupported) return op();

  try {
    return await op();
  } catch (err) {
    const challenge =
      err && typeof err === "object" && "headers" in err
        ? parseWwwAuthenticate(
            (err as { headers?: { get?: (k: string) => string | null } }).headers?.get?.(
              "www-authenticate",
            ) ?? null,
          )
        : null;
    if (!isStepUpChallenge(challenge)) throw err;

    await requestStepUp({
      acrValues: challenge?.acrValues ?? hint?.acrValues,
      maxAge: challenge?.maxAge ?? hint?.maxAge,
    });
    return op();
  }
}
