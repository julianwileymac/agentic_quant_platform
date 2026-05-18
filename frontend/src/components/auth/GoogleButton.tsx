import { Loader2 } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

interface GoogleButtonProps {
  onClick: () => void | Promise<void>;
  variant?: "signin" | "continue" | "signup";
  disabled?: boolean;
  className?: string;
}

const LABELS: Record<NonNullable<GoogleButtonProps["variant"]>, string> = {
  signin: "Sign in with Google",
  continue: "Continue with Google",
  signup: "Sign up with Google",
};

export function GoogleButton({
  onClick,
  variant = "continue",
  disabled,
  className,
}: GoogleButtonProps) {
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
        "flex h-11 w-full items-center justify-center gap-2 rounded-md border border-[#747775] bg-white px-4 text-sm font-medium text-[#1F1F1F] transition-colors hover:bg-[#F8F9FA] disabled:cursor-not-allowed disabled:opacity-70 dark:border-[#8E918F] dark:bg-[#131314] dark:text-[#E3E3E3] dark:hover:bg-[#1F1F1F]",
        className,
      )}
      style={{ fontFamily: "Roboto, system-ui, sans-serif", fontWeight: 500, fontSize: "14px" }}
    >
      {pending ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <svg
          aria-hidden="true"
          className="size-4"
          role="img"
          viewBox="0 0 24 24"
        >
          <path
            d="M23.49 12.27c0-.79-.07-1.55-.2-2.27H12v4.3h6.44a5.51 5.51 0 0 1-2.39 3.62v3.01h3.86c2.26-2.08 3.58-5.14 3.58-8.66Z"
            fill="#4285F4"
          />
          <path
            d="M12 24c3.24 0 5.95-1.07 7.94-2.91l-3.86-3.01c-1.07.72-2.44 1.14-4.08 1.14-3.14 0-5.8-2.12-6.75-4.97H1.26v3.11A12 12 0 0 0 12 24Z"
            fill="#34A853"
          />
          <path
            d="M5.25 14.25a7.2 7.2 0 0 1 0-4.5V6.64H1.26a12 12 0 0 0 0 10.72l3.99-3.11Z"
            fill="#FBBC05"
          />
          <path
            d="M12 4.77c1.76 0 3.34.61 4.58 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0A12 12 0 0 0 1.26 6.64l3.99 3.11c.95-2.85 3.61-4.98 6.75-4.98Z"
            fill="#EA4335"
          />
        </svg>
      )}
      <span>{LABELS[variant]}</span>
    </button>
  );
}
