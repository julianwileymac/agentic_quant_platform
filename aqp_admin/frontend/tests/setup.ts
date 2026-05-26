import "@testing-library/jest-dom/vitest";

// Stub Next.js navigation hooks for component tests that import the
// AdminShell — under jsdom we don't have a real router context.
import * as React from "react";
import { vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  redirect: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) =>
    React.createElement(
      "a",
      { href: typeof href === "string" ? href : "#" },
      children,
    ),
}));
