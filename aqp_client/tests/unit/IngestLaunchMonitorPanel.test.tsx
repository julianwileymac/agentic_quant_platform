import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IngestLaunchMonitorPanel } from "@/components/data/ingest/IngestLaunchMonitorPanel";

describe("<IngestLaunchMonitorPanel />", () => {
  it("shows stream metadata and renders timeline events", async () => {
    const user = userEvent.setup();
    const onLaunch = vi.fn();
    const onClear = vi.fn();
    render(
      <IngestLaunchMonitorPanel
        launchLabel="Launch"
        launchDescription="Dispatch run"
        launching={false}
        launchError={null}
        launchSummary={[
          { label: "task_id", value: "abc-123" },
          { label: "mode", value: "preset" },
        ]}
        taskId="abc-123"
        streamStatus="open"
        streamError={null}
        streamDone={false}
        events={[
          {
            task_id: "abc-123",
            stage: "running",
            message: "Dispatch accepted",
            timestamp: "2026-05-17T00:00:00Z",
          },
        ]}
        onLaunch={onLaunch}
        onClear={onClear}
      />,
    );

    expect(screen.getByText(/stream: open/i)).toBeInTheDocument();
    expect(screen.getByText(/task_id: abc-123/i)).toBeInTheDocument();
    expect(await screen.findByText(/Dispatch accepted/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Launch$/i }));
    await user.click(screen.getByRole("button", { name: /Clear run state/i }));
    expect(onLaunch).toHaveBeenCalledTimes(1);
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
