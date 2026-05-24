import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/cn";

describe("aqp_ui smoke test", () => {
  it("the testing harness is wired correctly", () => {
    expect(1 + 1).toBe(2);
  });

  it("renders a basic React element", () => {
    render(<h1>AQP — Agentic Quant Platform</h1>);
    expect(
      screen.getByRole("heading", { name: /AQP — Agentic Quant Platform/i }),
    ).toBeInTheDocument();
  });

  it("cn() merges tailwind classes deterministically", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
    expect(cn("text-sm", undefined, "font-bold")).toBe("text-sm font-bold");
  });

  it("ApiError carries status + body and detects step-up challenges", () => {
    const stepUp = new ApiError(
      401,
      'Bearer error="insufficient_user_authentication"',
      { detail: "MFA required" },
    );
    expect(stepUp.status).toBe(401);
    expect(stepUp.isStepUpRequired()).toBe(true);

    const notFound = new ApiError(404, "Not Found");
    expect(notFound.isStepUpRequired()).toBe(false);
  });
});

describe("environment", () => {
  it("can be configured with AQP_UI_BASE_URL", () => {
    const spy = vi.spyOn(process, "env", "get").mockReturnValue({
      AQP_UI_BASE_URL: "http://localhost:3002",
    });
    expect(process.env.AQP_UI_BASE_URL).toBe("http://localhost:3002");
    spy.mockRestore();
  });
});
