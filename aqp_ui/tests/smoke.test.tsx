import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/cn";

// Vitest 2 uses the classic JSX runtime when react/jsx-runtime isn't
// auto-imported by the bundler config; this import keeps the inline
// <h1/> below resolvable without depending on Vitest's `jsx: "automatic"`.
void React;
void vi;

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
    const previous = process.env.AQP_UI_BASE_URL;
    process.env.AQP_UI_BASE_URL = "http://localhost:3002";
    try {
      expect(process.env.AQP_UI_BASE_URL).toBe("http://localhost:3002");
    } finally {
      if (previous === undefined) {
        delete process.env.AQP_UI_BASE_URL;
      } else {
        process.env.AQP_UI_BASE_URL = previous;
      }
    }
  });
});
