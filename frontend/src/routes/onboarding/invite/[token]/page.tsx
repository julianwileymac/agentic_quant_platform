import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { InviteAcceptScreen } from "@/components/onboarding/InviteAcceptScreen";
import { acceptInviteToken } from "@/lib/api/invites";

type InviteStatus = "loading" | "success" | "failure";

export function InviteAcceptRoute() {
  const { token } = useParams<{ token: string }>();
  const [status, setStatus] = useState<InviteStatus>("loading");
  const [redirectUrl, setRedirectUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("failure");
      return;
    }
    let cancelled = false;
    const run = async () => {
      try {
        const response = await acceptInviteToken(token);
        if (cancelled) return;
        setRedirectUrl(response.redirect_url);
        setStatus("success");
        window.location.assign(response.redirect_url);
      } catch {
        if (!cancelled) setStatus("failure");
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const orgName = useMemo(() => {
    if (!redirectUrl) return null;
    try {
      const url = new URL(redirectUrl, window.location.origin);
      return url.searchParams.get("org_name");
    } catch {
      return null;
    }
  }, [redirectUrl]);

  return (
    <InviteAcceptScreen
      status={status}
      orgName={orgName}
      redirectUrl={redirectUrl}
      onContinue={() => {
        if (redirectUrl) window.location.assign(redirectUrl);
      }}
    />
  );
}
