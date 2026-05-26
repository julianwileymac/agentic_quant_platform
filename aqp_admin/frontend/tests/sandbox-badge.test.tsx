import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SandboxBadge } from "@/components/common/SandboxBadge";

describe("<SandboxBadge />", () => {
  it("renders nothing when no sandbox env var is set", () => {
    const original = process.env.NEXT_PUBLIC_AQP_SANDBOX;
    process.env.NEXT_PUBLIC_AQP_SANDBOX = "";
    const { container } = render(<SandboxBadge />);
    expect(container).toBeEmptyDOMElement();
    process.env.NEXT_PUBLIC_AQP_SANDBOX = original;
  });

  it("renders the badge when the env var is truthy", () => {
    const original = process.env.NEXT_PUBLIC_AQP_SANDBOX;
    process.env.NEXT_PUBLIC_AQP_SANDBOX = "dev-1";
    render(<SandboxBadge />);
    expect(screen.getByText(/SANDBOX: dev-1/)).toBeInTheDocument();
    process.env.NEXT_PUBLIC_AQP_SANDBOX = original;
  });
});
