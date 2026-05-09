import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";

describe("<ConfirmFrictionDialog />", () => {
  it("disables the confirm button until the user types the exact phrase", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmFrictionDialog
        open
        onOpenChange={() => {}}
        title="Halt all subsystems"
        consequence="This stops every running agent immediately."
        confirmPhrase="HALT"
        confirmLabel="Halt all"
        confirmVariant="destructive"
        onConfirm={onConfirm}
      />,
    );

    const button = await screen.findByRole("button", { name: /halt all/i });
    expect(button).toBeDisabled();

    const input = screen.getByLabelText(/Type/i, { selector: "input" });
    await user.type(input, "halt"); // wrong case
    expect(button).toBeDisabled();

    await user.clear(input);
    await user.type(input, "HALT");
    expect(button).not.toBeDisabled();
  });

  it("calls onConfirm and closes the dialog when confirmed", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    const onOpenChange = vi.fn();
    render(
      <ConfirmFrictionDialog
        open
        onOpenChange={onOpenChange}
        title="Submit order"
        consequence="Routes to live broker"
        confirmPhrase="FIRE"
        confirmLabel="Submit"
        confirmVariant="destructive"
        onConfirm={onConfirm}
      />,
    );

    const input = screen.getByLabelText(/Type/i, { selector: "input" });
    await user.type(input, "FIRE");
    const button = screen.getByRole("button", { name: /submit/i });
    await user.click(button);
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("renders consequence text and risk lines", () => {
    render(
      <ConfirmFrictionDialog
        open
        onOpenChange={() => {}}
        title="Submit"
        consequence="Capital at risk"
        details={[
          { label: "Notional", value: "$10,000", tone: "warn" },
          { label: "VaR", value: "$1,200", tone: "negative" },
        ]}
        confirmPhrase=""
        confirmLabel="Submit"
        confirmVariant="default"
        onConfirm={vi.fn()}
      />,
    );
    expect(screen.getByText(/Capital at risk/i)).toBeInTheDocument();
    expect(screen.getByText("Notional")).toBeInTheDocument();
    expect(screen.getByText("$10,000")).toBeInTheDocument();
    expect(screen.getByText("VaR")).toBeInTheDocument();
  });
});
