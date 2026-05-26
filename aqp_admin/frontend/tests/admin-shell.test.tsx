import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AdminShell } from "@/components/layout/AdminShell";

describe("<AdminShell />", () => {
  it("renders the brand + every nav entry", () => {
    render(
      <AdminShell>
        <div>content</div>
      </AdminShell>,
    );
    expect(screen.getByText("AQP Admin")).toBeInTheDocument();
    // Sample nav entries:
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Secrets")).toBeInTheDocument();
    expect(screen.getByText("Lineage")).toBeInTheDocument();
    expect(screen.getByText("RBAC")).toBeInTheDocument();
    expect(screen.getByText("Audit")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
  });
});
