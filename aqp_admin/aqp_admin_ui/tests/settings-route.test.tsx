import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CloudProviderWizard } from "@/components/settings/CloudProviderWizard";
import { FrameworkSettingsPanel } from "@/components/settings/FrameworkSettingsPanel";
import { adminApi } from "@/lib/api";
import { SettingsRoute } from "@/routes/settings";

function renderWithQuery(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("SettingsRoute", () => {
  beforeEach(() => {
    vi.spyOn(adminApi, "getFrameworkSettings").mockResolvedValue({
      service_id: "aqp-admin",
      namespace: null,
      runtime_settings: { api_url: "http://localhost:8900" },
      persisted_config: { values: {} },
      persisted_config_error: null,
    });
    vi.spyOn(adminApi, "cloudStatus").mockResolvedValue({
      terraform_providers: [],
      control_plane_health: null,
      cloudflare_health: null,
      errors: [],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the settings page and provider tabs", async () => {
    renderWithQuery(<SettingsRoute />);

    expect(screen.getByText("Settings")).toBeInTheDocument();
    await waitFor(() => {
      expect(adminApi.getFrameworkSettings).toHaveBeenCalled();
    });

    expect(screen.getByRole("button", { name: "aws" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "azure" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "gcp" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "cloudflare" })).toBeInTheDocument();
  });
});

describe("CloudProviderWizard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submits an AWS provider payload", async () => {
    const onConnected = vi.fn();
    const connectSpy = vi
      .spyOn(adminApi, "connectCloudProvider")
      .mockResolvedValue({ provider: { id: "provider-1", kind: "aws" }, audit_run_id: "audit-1" });

    renderWithQuery(<CloudProviderWizard providerKind="aws" onConnected={onConnected} />);

    fireEvent.change(screen.getByPlaceholderText("aws-primary"), {
      target: { value: "aws-prod" },
    });
    fireEvent.change(screen.getByPlaceholderText("AWS production"), {
      target: { value: "AWS prod" },
    });
    fireEvent.change(screen.getByPlaceholderText("us-east-1"), {
      target: { value: "us-east-1" },
    });
    fireEvent.change(screen.getByPlaceholderText("idp:aws:prod"), {
      target: { value: "idp:aws:prod" },
    });
    fireEvent.change(screen.getByPlaceholderText('{"environment":"production"}'), {
      target: { value: '{"environment":"production"}' },
    });

    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    fireEvent.click(await screen.findByRole("button", { name: "Connect AWS" }));

    await waitFor(() => {
      expect(connectSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          provider_kind: "aws",
          slug: "aws-prod",
          name: "AWS prod",
          default_region: "us-east-1",
          credential_key: "idp:aws:prod",
          config_json: { environment: "production" },
        }),
      );
    });
    await waitFor(() => {
      expect(onConnected).toHaveBeenCalled();
    });
  });
});

describe("FrameworkSettingsPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submits persisted settings patch payload", async () => {
    const saveSpy = vi
      .spyOn(adminApi, "patchFrameworkSettings")
      .mockResolvedValue({
        service_id: "aqp-admin",
        namespace: null,
        result: { status: "ok" },
        audit_run_id: "audit-2",
      });

    renderWithQuery(
      <FrameworkSettingsPanel
        data={{
          service_id: "aqp-admin",
          namespace: null,
          runtime_settings: {},
          persisted_config: { values: { AQP_ADMIN_API_URL: "http://localhost:8900" } },
          persisted_config_error: null,
        }}
        isLoading={false}
        error={null}
        onRefresh={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Save framework settings" }));

    await waitFor(() => {
      expect(saveSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          service_id: "aqp-admin",
          values: { AQP_ADMIN_API_URL: "http://localhost:8900" },
          trigger_restart: true,
        }),
      );
    });
  });
});
