/**
 * SandboxBadge — present only when VITE_AQP_SANDBOX is set.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SandboxBadge } from "@/components/common/SandboxBadge";

describe("SandboxBadge", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("renders nothing when VITE_AQP_SANDBOX is unset", () => {
    vi.stubEnv("VITE_AQP_SANDBOX", "");
    vi.stubEnv("VITE_ADMIN_SANDBOX", "");
    const { container } = render(<SandboxBadge />);
    expect(container.firstChild).toBeNull();
  });

  it("renders SANDBOX when the env flag is on", () => {
    vi.stubEnv("VITE_AQP_SANDBOX", "1");
    render(<SandboxBadge />);
    expect(screen.getByText(/SANDBOX/i)).toBeInTheDocument();
  });

  it("appends the env name when not a bool literal", () => {
    vi.stubEnv("VITE_AQP_SANDBOX", "staging");
    render(<SandboxBadge />);
    expect(screen.getByText(/staging/i)).toBeInTheDocument();
  });
});
