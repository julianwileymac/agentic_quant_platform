import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { groupByStage, ProgressTimeline } from "@/components/common/ProgressTimeline";
import type { ProgressEvent } from "@/lib/ws/types";

const sampleEvents: ProgressEvent[] = [
  { stage: "starting", message: "Booting agent runtime", timestamp: "2024-01-01T00:00:00Z" },
  {
    stage: "thinking",
    agent: "researcher",
    message: "Considering universe",
    timestamp: "2024-01-01T00:00:01Z",
  },
  {
    stage: "tool",
    agent: "researcher",
    tool: "yfinance.fetch",
    message: "fetching",
    timestamp: "2024-01-01T00:00:02Z",
  },
  { stage: "done", message: "Run finished", timestamp: "2024-01-01T00:00:03Z" },
];

describe("<ProgressTimeline />", () => {
  it("renders an empty-state when no events", () => {
    render(<ProgressTimeline events={[]} />);
    expect(screen.getByText(/waiting for events/i)).toBeInTheDocument();
  });

  it("shows stage labels and agent badges", async () => {
    render(<ProgressTimeline events={sampleEvents} height={400} />);
    // The virtualizer relies on a microtask-deferred ResizeObserver
    // callback (see tests/unit/setup.ts) so we need an async query for
    // the first assertion to give the observer a chance to fire.
    expect((await screen.findAllByText(/starting/i)).length).toBeGreaterThan(0);
    expect(screen.getByText(/Booting agent runtime/i)).toBeInTheDocument();
    expect(screen.getAllByText("researcher").length).toBeGreaterThan(0);
    expect(screen.getByText(/yfinance\.fetch/i)).toBeInTheDocument();
  });

  it("invokes onSelectEvent when a row is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ProgressTimeline events={sampleEvents} onSelectEvent={onSelect} height={400} />);
    const row = await screen.findByText(/Booting agent runtime/i);
    await user.click(row);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0]?.[0]?.stage).toBe("starting");
  });
});

describe("groupByStage", () => {
  it("counts occurrences per stage tag", () => {
    const counts = groupByStage(sampleEvents);
    expect(counts.starting).toBe(1);
    expect(counts.thinking).toBe(1);
    expect(counts.tool).toBe(1);
    expect(counts.done).toBe(1);
  });
});
