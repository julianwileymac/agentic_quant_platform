import { Loader2 } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

interface MicrosoftButtonProps {
  onClick: () => void | Promise<void>;
  variant?: "signin" | "continue" | "signup";
  disabled?: boolean;
  className?: string;
}

const LABELS: Record<NonNullable<MicrosoftButtonProps["variant"]>, string> = {
  signin: "Sign in with Microsoft",
  continue: "Continue with Microsoft",
  signup: "Sign up with Microsoft",
};

export function MicrosoftButton({
  onClick,
  variant = "continue",
  disabled,
  className,
}: MicrosoftButtonProps) {
  const [pending, setPending] = useState(false);

  const handleClick = async () => {
    if (pending || disabled) return;
    setPending(true);
    try {
      await onClick();
    } finally {
      setPending(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={disabled || pending}
      className={cn(
        "flex h-11 w-full items-center justify-center gap-2 rounded-md border border-[#8C8C8C] bg-white px-4 text-sm font-medium text-[#5E5E5E] transition-colors hover:bg-[#F3F3F3] disabled:cursor-not-allowed disabled:opacity-70 dark:border-0 dark:bg-[#2F2F2F] dark:text-white dark:hover:bg-[#3A3A3A]",
        className,
      )}
      style={{ fontFamily: "Segoe UI, system-ui, sans-serif" }}
    >
      {pending ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <svg
          aria-hidden="true"
          viewBox="0 0 23 23"
          className="size-4"
          role="img"
        >
          <rect width="10" height="10" x="1" y="1" fill="#F25022" />
          <rect width="10" height="10" x="12" y="1" fill="#7FBA00" />
          <rect width="10" height="10" x="1" y="12" fill="#00A4EF" />
          <rect width="10" height="10" x="12" y="12" fill="#FFB900" />
        </svg>
      )}
      <span>{LABELS[variant]}</span>
    </button>
  );
}
