/**
 * KillSwitch fan-out test — verifies the friction-gate + API call.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KillSwitch } from "@/components/common/KillSwitch";
import { adminApi } from "@/lib/api";

describe("KillSwitch", () => {
  beforeEach(() => {
    vi.spyOn(adminApi, "haltAll").mockResolvedValue({
      triggered_at: new Date().toISOString(),
      user_id: "auth0|test",
      reason: "kill-switch",
      halted: [{ target: "workloads", result: { halted_count: 1 } }],
      failures: [],
    });
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the kill-switch button", () => {
    render(<KillSwitch />);
    expect(screen.getByRole("button", { name: /Kill switch/i })).toBeInTheDocument();
  });

  it("requires typing the confirm phrase before firing", async () => {
    render(<KillSwitch />);
    fireEvent.click(screen.getByRole("button", { name: /Kill switch/i }));
    const confirmBtn = await screen.findByRole("button", {
      name: /Confirm destructive action/i,
    });
    expect(confirmBtn).toBeDisabled();

    const input = screen.getByPlaceholderText("halt") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "halt" } });
    expect(confirmBtn).not.toBeDisabled();

    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(adminApi.haltAll).toHaveBeenCalledTimes(1);
    });
    expect(adminApi.haltAll).toHaveBeenCalledWith("kill-switch");
  });

  it("forwards the operator-supplied reason", async () => {
    render(<KillSwitch />);
    fireEvent.click(screen.getByRole("button", { name: /Kill switch/i }));
    const confirmInput = screen.getByPlaceholderText("halt") as HTMLInputElement;
    const reasonInput = screen.getByPlaceholderText("kill-switch") as HTMLInputElement;
    fireEvent.change(confirmInput, { target: { value: "halt" } });
    fireEvent.change(reasonInput, { target: { value: "drill" } });

    fireEvent.click(await screen.findByRole("button", { name: /Confirm destructive action/i }));
    await waitFor(() => {
      expect(adminApi.haltAll).toHaveBeenCalledWith("drill");
    });
  });
});
