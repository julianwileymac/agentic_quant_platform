import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AdminCrudPage } from "@/components/admin/AdminCrudPage";

interface Org {
  id: string;
  slug: string;
  name: string;
}

const ROWS: Org[] = [
  { id: "org-1", slug: "acme", name: "Acme" },
  { id: "org-2", slug: "globex", name: "Globex" },
];

function renderPage(overrides: { onDelete?: ReturnType<typeof vi.fn> } = {}) {
  const onDelete = overrides.onDelete ?? vi.fn().mockResolvedValue(undefined);
  const onRefresh = vi.fn();

  const utils = render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AdminCrudPage<Org>
          title="Organizations"
          subtitle="Top-level tenancy entities."
          rows={ROWS}
          loading={false}
          onRefresh={onRefresh}
          rowKey={(r) => r.id}
          columns={[
            { key: "slug", header: "Slug", render: (r) => <span>{r.slug}</span> },
            { key: "name", header: "Name", render: (r) => <span>{r.name}</span> },
          ]}
          confirmDeletePhrase={(r) => r.slug}
          deleteTitle={(r) => `Delete ${r.slug}`}
          deleteConsequence="This is irreversible."
          onDelete={onDelete}
          createSheet={() => null}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...utils, onDelete, onRefresh };
}

describe("<AdminCrudPage />", () => {
  it("renders rows from the supplied list", async () => {
    renderPage();
    // Async queries give the virtualizer's ResizeObserver microtask a
    // chance to fire (see tests/unit/setup.ts).
    expect(await screen.findByText("acme")).toBeInTheDocument();
    expect(screen.getByText("globex")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });

  it("opens the friction-gated delete dialog and gates submission on the typed phrase", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn().mockResolvedValue(undefined);
    renderPage({ onDelete });

    await screen.findByText("acme");

    // The "acme" row has its own Delete button as a Cell action.
    const acmeRow = screen.getByText("acme").closest("div.grid");
    expect(acmeRow).not.toBeNull();
    const rowDelete = within(acmeRow as HTMLElement).getByRole("button", { name: /delete/i });
    await user.click(rowDelete);

    // ConfirmFrictionDialog mounts as a Radix `alertdialog`.
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/Delete acme/i)).toBeInTheDocument();

    const submit = within(dialog).getByRole("button", { name: /^Delete$/ });
    expect(submit).toBeDisabled();

    const phraseInput = within(dialog).getByLabelText(/Type/i, { selector: "input" });
    await user.type(phraseInput, "acme");
    await waitFor(() => expect(submit).not.toBeDisabled());

    await user.click(submit);
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(ROWS[0]));
  });
});
