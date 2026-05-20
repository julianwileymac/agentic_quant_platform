import { useEffect, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ConfirmFrictionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmationText: string;
  confirmationLabel?: string;
  destructiveLabel?: string;
  onConfirm: () => Promise<void>;
}

export function ConfirmFrictionDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmationText,
  confirmationLabel,
  destructiveLabel,
  onConfirm,
}: ConfirmFrictionDialogProps) {
  const [typed, setTyped] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!open) {
      setTyped("");
      setPending(false);
    }
  }, [open]);

  const isMatch = typed === confirmationText;

  const handleConfirm = async () => {
    if (!isMatch || pending) return;
    setPending(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setPending(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-2">
          <Label htmlFor="confirmation-input">
            {confirmationLabel ?? "Type the confirmation text to continue"}
          </Label>
          <Input
            id="confirmation-input"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder={confirmationText}
            autoComplete="off"
            spellCheck={false}
            className="font-mono"
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={!isMatch || pending}
            onClick={(event) => {
              event.preventDefault();
              void handleConfirm();
            }}
            className="bg-[var(--neg-fg)] text-white hover:bg-[var(--neg-fg)]/90"
          >
            {pending ? "Working..." : destructiveLabel ?? "Confirm"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
