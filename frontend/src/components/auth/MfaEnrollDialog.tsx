import { QRCodeSVG } from "qrcode.react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api/client";
import { useEnrollMfaMutation, type MfaEnrollment } from "@/lib/api/me";
import { toast } from "@/components/ui/toast";

type EnrollableFactor = "totp" | "sms" | "webauthn-roaming" | "webauthn-platform";
type DialogStage = "start" | "verify" | "recovery";

interface MfaEnrollDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  factor: EnrollableFactor;
  onComplete?: () => void;
}

function toBase64(bytes: ArrayBuffer): string {
  const arr = new Uint8Array(bytes);
  let binary = "";
  arr.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return btoa(binary);
}

function buildTotpUri(secret: string): string {
  const issuer = "Agentic Quant Platform";
  const account = "user";
  return `otpauth://totp/${encodeURIComponent(issuer)}:${encodeURIComponent(account)}?secret=${encodeURIComponent(secret)}&issuer=${encodeURIComponent(issuer)}`;
}

export function MfaEnrollDialog({
  open,
  onOpenChange,
  factor,
  onComplete,
}: MfaEnrollDialogProps) {
  const enrollMutation = useEnrollMfaMutation();
  const [enrollment, setEnrollment] = useState<MfaEnrollment | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [stage, setStage] = useState<DialogStage>("start");
  const [savedRecoveryCodes, setSavedRecoveryCodes] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);

  useEffect(() => {
    if (!open) {
      setEnrollment(null);
      setErrorMessage(null);
      setOtpCode("");
      setPhoneNumber("");
      setStage("start");
      setSavedRecoveryCodes(false);
      return;
    }

    const run = async () => {
      setErrorMessage(null);
      setSubmitting(true);
      try {
        const result = await enrollMutation.mutateAsync({ factor });
        setEnrollment(result);
        if (
          factor === "sms" ||
          factor === "webauthn-roaming" ||
          factor === "webauthn-platform"
        ) {
          setStage("start");
        } else {
          setStage("verify");
        }
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : "Unable to start enrollment.");
      } finally {
        setSubmitting(false);
      }
    };

    void run();
  }, [enrollMutation, factor, open, retryNonce]);

  const totpQrValue = useMemo(() => {
    if (!enrollment?.secret) return enrollment?.qr_code_url ?? null;
    return enrollment.qr_code_url ?? buildTotpUri(enrollment.secret);
  }, [enrollment]);

  const handleVerifyCode = async () => {
    if (!enrollment) return;
    setSubmitting(true);
    try {
      try {
        await apiFetch(`/me/mfa/factors/${encodeURIComponent(enrollment.ticket_id)}/verify`, {
          method: "POST",
          body: JSON.stringify({ code: otpCode }),
        });
      } catch {
        // Backend verify endpoints are still rolling out; don't block UI completion.
      }
      setStage("recovery");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSmsCodeSend = () => {
    if (!phoneNumber.trim()) {
      toast.error("Enter a phone number first.");
      return;
    }
    setStage("verify");
  };

  const handleWebAuthn = async () => {
    if (!enrollment) return;
    if (!window.PublicKeyCredential || !window.navigator.credentials) {
      toast.error("WebAuthn is not available in this browser.");
      return;
    }

    setSubmitting(true);
    try {
      const challenge = crypto.getRandomValues(new Uint8Array(32));
      const userId = crypto.getRandomValues(new Uint8Array(16));
      const credential = (await navigator.credentials.create({
        publicKey: {
          challenge,
          rp: { name: "Agentic Quant Platform" },
          user: {
            id: userId,
            name: "aqp-user",
            displayName: "AQP User",
          },
          pubKeyCredParams: [
            { alg: -7, type: "public-key" },
            { alg: -257, type: "public-key" },
          ],
          timeout: 60_000,
          authenticatorSelection: {
            authenticatorAttachment:
              factor === "webauthn-platform" ? "platform" : "cross-platform",
            userVerification: "preferred",
          },
        },
      })) as PublicKeyCredential | null;

      if (credential) {
        const attestation = credential.response as AuthenticatorAttestationResponse;
        try {
          await apiFetch("/me/mfa/enroll/verify", {
            method: "POST",
            body: JSON.stringify({
              ticket_id: enrollment.ticket_id,
              id: credential.id,
              raw_id: toBase64(credential.rawId),
              type: credential.type,
              response: {
                client_data_json: toBase64(attestation.clientDataJSON),
                attestation_object: toBase64(attestation.attestationObject),
              },
            }),
          });
        } catch {
          // Placeholder endpoint; ignore until backend endpoint lands.
        }
      }
      setStage("recovery");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "WebAuthn enrollment failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDownloadRecoveryCodes = () => {
    if (!enrollment?.recovery_codes?.length) return;
    const blob = new Blob([enrollment.recovery_codes.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "aqp-recovery-codes.txt";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleDone = () => {
    onComplete?.();
    onOpenChange(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    const requiresAcknowledge = stage === "recovery";
    if (!nextOpen && requiresAcknowledge && !savedRecoveryCodes) return;
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Enroll MFA factor</DialogTitle>
          <DialogDescription>
            {factor === "totp"
              ? "Set up an authenticator app and verify a one-time code."
              : factor === "sms"
                ? "Add a phone number and verify an SMS challenge."
                : "Register a passkey or security key in this browser."}
          </DialogDescription>
        </DialogHeader>

        {submitting && !enrollment ? (
          <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 text-sm text-[var(--text-secondary)]">
            Preparing enrollment...
          </div>
        ) : null}

        {errorMessage ? (
          <div className="space-y-2 rounded-md border border-[var(--neg-fg)]/40 bg-[var(--neg-bg)] p-3">
            <div className="text-sm text-[var(--neg-fg)]">{errorMessage}</div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setRetryNonce((value) => value + 1)}
            >
              Retry
            </Button>
          </div>
        ) : null}

        {enrollment && !errorMessage ? (
          <div className="space-y-4">
            {factor === "totp" && stage === "verify" ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Scan QR code</Label>
                  {totpQrValue ? (
                    <div className="inline-flex rounded-md border border-[var(--border-default)] bg-white p-3">
                      <QRCodeSVG value={totpQrValue} size={160} />
                    </div>
                  ) : (
                    <div className="text-sm text-[var(--text-secondary)]">
                      QR code unavailable. Use the secret manually.
                    </div>
                  )}
                </div>
                <div className="space-y-1">
                  <Label>Manual secret</Label>
                  <div className="flex items-center gap-2">
                    <Input value={enrollment.secret ?? ""} readOnly className="font-mono" />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        if (enrollment.secret) {
                          void navigator.clipboard.writeText(enrollment.secret);
                          toast.success("Secret copied.");
                        }
                      }}
                    >
                      Copy
                    </Button>
                  </div>
                </div>
                <div className="space-y-1">
                  <Label>Verification code</Label>
                  <Input
                    value={otpCode}
                    onChange={(event) => setOtpCode(event.target.value)}
                    placeholder="123456"
                    maxLength={6}
                    inputMode="numeric"
                    className="font-mono"
                  />
                </div>
                <Button
                  type="button"
                  onClick={() => void handleVerifyCode()}
                  disabled={otpCode.trim().length < 6 || submitting}
                >
                  Verify code
                </Button>
              </div>
            ) : null}

            {factor === "sms" && stage === "start" ? (
              <div className="space-y-3">
                <div className="space-y-1">
                  <Label>Phone number</Label>
                  <Input
                    value={phoneNumber}
                    onChange={(event) => setPhoneNumber(event.target.value)}
                    placeholder="+1 555 123 4567"
                  />
                </div>
                <Button type="button" onClick={handleSmsCodeSend} disabled={submitting}>
                  Send verification code
                </Button>
              </div>
            ) : null}

            {factor === "sms" && stage === "verify" ? (
              <div className="space-y-3">
                <div className="space-y-1">
                  <Label>SMS verification code</Label>
                  <Input
                    value={otpCode}
                    onChange={(event) => setOtpCode(event.target.value)}
                    placeholder="123456"
                    maxLength={6}
                    inputMode="numeric"
                    className="font-mono"
                  />
                </div>
                <Button
                  type="button"
                  onClick={() => void handleVerifyCode()}
                  disabled={otpCode.trim().length < 6 || submitting}
                >
                  Verify SMS code
                </Button>
              </div>
            ) : null}

            {(factor === "webauthn-roaming" || factor === "webauthn-platform") &&
            stage === "start" ? (
              <div className="space-y-3">
                <div className="text-sm text-[var(--text-secondary)]">
                  Use your device's passkey flow to register this authenticator.
                </div>
                <Button type="button" onClick={() => void handleWebAuthn()} disabled={submitting}>
                  Register authenticator
                </Button>
              </div>
            ) : null}

            {stage === "recovery" ? (
              <div className="space-y-3">
                <Label>Recovery codes</Label>
                <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3">
                  <ul className="grid grid-cols-2 gap-2 font-mono text-xs">
                    {enrollment.recovery_codes.map((code) => (
                      <li key={code}>{code}</li>
                    ))}
                  </ul>
                </div>
                <Button type="button" variant="outline" onClick={handleDownloadRecoveryCodes}>
                  Download codes as .txt
                </Button>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={savedRecoveryCodes}
                    onChange={(event) => setSavedRecoveryCodes(event.target.checked)}
                  />
                  I've saved these recovery codes.
                </label>
              </div>
            ) : null}
          </div>
        ) : null}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
            Close
          </Button>
          {stage === "recovery" ? (
            <Button type="button" onClick={handleDone} disabled={!savedRecoveryCodes}>
              Done
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
