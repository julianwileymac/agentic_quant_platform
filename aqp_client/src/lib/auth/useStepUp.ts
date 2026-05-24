/**
 * Step-up MFA — frontend integration for AGENTS hard rule 52.
 *
 * The backend ``require_step_up`` dep (see :mod:`aqp.api.security_stepup`)
 * rejects requests that lack a recent MFA-bound token with HTTP 401 and
 * an RFC 9470 ``WWW-Authenticate`` header carrying ``acr_values`` and
 * ``max_age``. This module:
 *
 * 1. Parses the header so ``apiFetch`` can decide between "the user
 *    must re-auth" vs "the SDK silent refresh will resolve it".
 * 2. Exposes a ``useStepUp`` hook that wraps the IdP SDK's interactive
 *    prompt (Auth0 ``loginWithPopup`` / MSAL ``acquireTokenPopup``) so
 *    a sensitive button can pre-flight the step-up *before* the
 *    destructive operation fires.
 * 3. Exposes a ``runWithStepUp`` helper that drives the
 *    pre-flight-then-call pattern for the KillSwitch and similar
 *    one-click flows.
 *
 * The hook supports both Auth0 and MSAL because the underlying step-up
 * getter is installed by whichever provider booted (see
 * :mod:`aqp_client/src/lib/auth/AuthProvider.tsx`).
 */
import { useCallback, useMemo, useState } from "react";

import {
  hasStepUpSupport,
  requestStepUpToken,
  type StepUpHint,
} from "@/lib/auth/tokenStore";

/** OIDC ``acr_values`` URI for MFA. */
export const ACR_MFA =
  "http://schemas.openid.net/pape/policies/2007/06/multi-factor";

/**
 * Parsed RFC 9470 ``WWW-Authenticate`` challenge.
 *
 * ``insufficientUserAuthentication`` is true when the server returned
 * ``error="insufficient_user_authentication"``. ``maxAge`` is the
 * server-provided window (seconds) and ``acrValues`` is the policy URI
 * the client must satisfy on its next token request.
 */
export type StepUpChallenge = {
  insufficientUserAuthentication: boolean;
  maxAge?: number;
  acrValues?: string;
  errorDescription?: string;
};

/**
 * Parse the value of a ``WWW-Authenticate`` header into a structured
 * challenge. Tolerates header values with mixed quoting and additional
 * whitespace. Returns ``null`` for non-``Bearer`` schemes.
 */
export function parseWwwAuthenticate(value: string | null | undefined): StepUpChallenge | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed.toLowerCase().startsWith("bearer")) return null;
  const params: Record<string, string> = {};
  const rx = /(\w[\w-]*)\s*=\s*("((?:\\.|[^"\\])*)"|[^\s,]+)/g;
  let m: RegExpExecArray | null;
  while ((m = rx.exec(trimmed)) !== null) {
    const key = m[1]?.toLowerCase();
    const quoted = m[3];
    const bare = m[2];
    if (!key) continue;
    params[key] = (quoted ?? bare ?? "").replace(/\\(.)/g, "$1");
  }
  const error = params.error?.toLowerCase();
  return {
    insufficientUserAuthentication: error === "insufficient_user_authentication",
    maxAge: params.max_age ? Number.parseInt(params.max_age, 10) : undefined,
    acrValues: params.acr_values,
    errorDescription: params.error_description,
  };
}

export type UseStepUpResult = {
  /**
   * True when the active IdP provider supports interactive step-up.
   * Local-dev (``AQP_AUTH_PROVIDER=local``) returns false.
   */
  isSupported: boolean;
  /**
   * True while the IdP popup / redirect is in flight. Use to disable
   * the sensitive button so the user can't double-fire while we wait.
   */
  isStepUpInFlight: boolean;
  /**
   * Trigger a step-up prompt. Returns the freshly minted token, or
   * ``null`` when the user cancelled or the prompt failed.
   *
   * ``hint.acr_values`` defaults to :const:`ACR_MFA`; ``hint.max_age``
   * defaults to ``0`` (force re-auth regardless of session age).
   */
  requestStepUp: (hint?: StepUpHint) => Promise<string | null>;
};

/**
 * React hook for sensitive components.
 *
 * Example::
 *
 *     const { isSupported, isStepUpInFlight, requestStepUp } = useStepUp();
 *     const onKill = async () => {
 *       if (isSupported) {
 *         const token = await requestStepUp();
 *         if (!token) return; // user cancelled
 *       }
 *       await runHalt();
 *     };
 */
export function useStepUp(): UseStepUpResult {
  const [isStepUpInFlight, setStepUpInFlight] = useState(false);
  const isSupported = useMemo(() => hasStepUpSupport(), []);

  const requestStepUp = useCallback(
    async (hint?: StepUpHint): Promise<string | null> => {
      const merged: StepUpHint = {
        acr_values: hint?.acr_values ?? ACR_MFA,
        max_age: hint?.max_age ?? 0,
      };
      setStepUpInFlight(true);
      try {
        return await requestStepUpToken(merged);
      } finally {
        setStepUpInFlight(false);
      }
    },
    [],
  );

  return { isSupported, isStepUpInFlight, requestStepUp };
}

/**
 * Helper for the common "pre-flight step-up, then run the call" pattern.
 *
 * - On a supported IdP: prompts for MFA, then runs ``op``.
 * - On a local-dev deployment with no IdP: just runs ``op``.
 * - Returns ``null`` when the user cancelled the MFA prompt; the caller
 *   should surface a toast.
 */
export async function runWithStepUp<T>(
  requestStepUp: UseStepUpResult["requestStepUp"],
  isSupported: boolean,
  op: () => Promise<T>,
  hint?: StepUpHint,
): Promise<T | null> {
  if (isSupported) {
    const token = await requestStepUp(hint);
    if (!token) return null;
  }
  return op();
}
