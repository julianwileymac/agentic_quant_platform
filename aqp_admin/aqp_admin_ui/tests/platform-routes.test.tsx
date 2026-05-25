import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { adminApi } from "@/lib/api";
import { KubernetesIndex } from "@/routes/kubernetes";
import { ServicesRoute } from "@/routes/services";
import { TerraformIndex } from "@/routes/terraform";

function renderWithQuery(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("managed platform routes", () => {
  beforeEach(() => {
    vi.spyOn(adminApi, "listServices").mockResolvedValue({
      services: [
        {
          id: "api",
          kind: "kubernetes",
          org_id: "acme",
          namespace: "tenant-acme",
          state: "Running",
          phase: "Running",
          image: "ghcr.io/aqp/api:dev",
          replicas_desired: 2,
          replicas_ready: 2,
        },
      ],
    });
    vi.spyOn(adminApi, "listTerraformProviders").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(adminApi, "listTerraformStacks").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(adminApi, "listTerraformWorkspaces").mockResolvedValue({
      items: [{ id: "ws-1", slug: "prod" }],
      total: 1,
    });
    vi.spyOn(adminApi, "listTerraformRuns").mockResolvedValue({ items: [], total: 0 });
    vi.spyOn(adminApi, "terraformHaltStatus").mockResolvedValue({ data: { active: false } });
    vi.spyOn(adminApi, "kubernetesStatus").mockResolvedValue({
      adapter: "in_cluster",
      status: "ok",
    });
    vi.spyOn(adminApi, "listKubernetesNamespaces").mockResolvedValue({
      namespaces: [{ namespace: "tenant-acme" }],
    });
    vi.spyOn(adminApi, "listPods").mockResolvedValue({
      namespace: "tenant-acme",
      pods: [{ name: "api-0", phase: "Running" }],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders managed services with control actions", async () => {
    renderWithQuery(<ServicesRoute />);

    expect(await screen.findByText("api")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Scale" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restart" })).toBeInTheDocument();
  });

  it("renders Terraform workspace controls", async () => {
    renderWithQuery(<TerraformIndex />);

    expect(await screen.findByText("Terraform")).toBeInTheDocument();
    await waitFor(() => expect(adminApi.listTerraformWorkspaces).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "plan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "destroy" })).toBeInTheDocument();
  });

  it("renders Kubernetes namespaces and pods", async () => {
    renderWithQuery(<KubernetesIndex />);

    const namespace = await screen.findByRole("button", { name: "tenant-acme" });
    fireEvent.click(namespace);
    const pod = await screen.findByRole("button", { name: "api-0 Running" });
    fireEvent.click(pod);
    expect(screen.getByRole("button", { name: "Exec with confirmation" })).toBeInTheDocument();
  });
});
