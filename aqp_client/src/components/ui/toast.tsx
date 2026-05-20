import { Toaster as SonnerToaster, toast as sonnerToast } from "sonner";

/**
 * AQP toaster — sonner with the dark / semantic palette baked in. Mounted
 * once at the App root so any module can call `toast.*` from anywhere.
 */
export function Toaster() {
  return (
    <SonnerToaster
      position="top-right"
      richColors
      closeButton
      duration={4_000}
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-[var(--bg-elevated)] group-[.toaster]:text-[var(--text-primary)] group-[.toaster]:border-[var(--border-default)] group-[.toaster]:shadow-lg",
          description: "group-[.toast]:text-[var(--text-secondary)]",
          actionButton: "group-[.toast]:bg-[var(--info-fg)] group-[.toast]:text-white",
          cancelButton:
            "group-[.toast]:bg-[var(--bg-surface)] group-[.toast]:text-[var(--text-primary)]",
          error:
            "group-[.toaster]:!border-[var(--neg-fg)] group-[.toaster]:!bg-[var(--neg-bg)]",
          success:
            "group-[.toaster]:!border-[var(--pos-fg)] group-[.toaster]:!bg-[var(--pos-bg)]",
          warning:
            "group-[.toaster]:!border-[var(--warn-fg)] group-[.toaster]:!bg-[var(--warn-bg)]",
        },
      }}
    />
  );
}

export const toast = sonnerToast;
