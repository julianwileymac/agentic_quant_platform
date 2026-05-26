import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KillSwitch } from "@/components/common/KillSwitch";

vi.mock("@/lib/api/client", () => ({
  adminApi: {
    haltAll: vi.fn().mockResolvedValue({
      halted: [{ target: "/agents/halt" }],
      failures: [],
    }),
  },
}));

describe("<KillSwitch />", () => {
  it("renders the topbar STOP button", () => {
    render(<KillSwitch />);
    expect(screen.getByText("Kill switch")).toBeInTheDocument();
  });

  it("opens the friction dialog when clicked", () => {
    render(<KillSwitch />);
    fireEvent.click(screen.getByText("Kill switch"));
    expect(screen.getByText(/Engage the kill switch/)).toBeInTheDocument();
  });

  it("does not fire without the verbatim phrase", () => {
    render(<KillSwitch />);
    fireEvent.click(screen.getByText("Kill switch"));
    const confirm = screen.getByText("Confirm destructive action");
    expect(confirm).toBeDisabled();
  });
});
