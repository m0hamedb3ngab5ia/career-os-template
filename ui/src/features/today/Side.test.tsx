import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { NextScheduled } from "./NextScheduled";
import { PausedBanner } from "./PausedBanner";
import { PipelineChart } from "./PipelineChart";
import { RecentRuns } from "./RecentRuns";
import { defaultRoutes, mockApi, NOW, renderWithApp, status } from "./testing";
import type { CatchUp } from "./types";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("RecentRuns", () => {
  it("lists runs with kind, stop-reason chip, detail and time; links to all runs", () => {
    mockApi(defaultRoutes());
    renderWithApp(<RecentRuns runs={status.recent_runs!} now={NOW} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(within(items[0]!).getByText("Scout")).toBeInTheDocument();
    expect(within(items[0]!).getByText("Done")).toBeInTheDocument();
    expect(within(items[0]!).getByText("38 new of 412 scanned")).toBeInTheDocument();
    expect(within(items[0]!).getByText("8:02 AM")).toBeInTheDocument();
    expect(within(items[1]!).getByText("Interrupted")).toBeInTheDocument();
    expect(within(items[1]!).getByText("1 of 2 jobs")).toBeInTheDocument();
    const unknown = within(items[2]!).getByText("Mystery reason");
    expect(unknown).toHaveAttribute("data-tone", "gray");
    expect(within(items[2]!).getByText("Mon 4:40 PM")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All runs" })).toHaveAttribute("href", "/runs");
  });

  it("shows at most five runs", () => {
    mockApi(defaultRoutes());
    const many = Array.from({ length: 7 }, (_, i) => ({ ...status.recent_runs![0]!, id: `r${i}` }));
    renderWithApp(<RecentRuns runs={many} now={NOW} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });

  it("says No runs yet when empty", () => {
    mockApi(defaultRoutes());
    renderWithApp(<RecentRuns runs={[]} now={NOW} />);
    expect(screen.getByText("No runs yet")).toBeInTheDocument();
  });
});

const catchUp: CatchUp = {
  created_at: "2026-09-25T06:00:00Z",
  kinds: {
    score: { first_missed: "2026-09-25T01:00:00Z", slots: 1, last_missed: "2026-09-25T06:00:00Z" },
    prepare: { first_missed: "2026-09-25T02:00:00Z", slots: 2, last_missed: "2026-09-25T06:00:00Z" },
  },
};

describe("NextScheduled", () => {
  it("lists each job's next time and 'off' when disabled; links to the run schedule", () => {
    mockApi(defaultRoutes());
    renderWithApp(<NextScheduled schedule={status.schedule!} catchUp={null} now={NOW} />);
    const row = (name: string) => screen.getByText(name).closest("div")!;
    expect(within(row("Scout")).getByText("12:00 PM")).toBeInTheDocument();
    expect(within(row("Score")).getByText("Tomorrow, 1:00 AM")).toBeInTheDocument();
    expect(within(row("Inbox sync")).getByText("off")).toBeInTheDocument();
    expect(within(row("Prune + storage check")).getByText("Sun 3:00 AM")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run schedule" })).toHaveAttribute("href", "/runs");
    expect(screen.queryByText(/runs missed/)).not.toBeInTheDocument();
  });

  it("shows the schedule error instead of times", () => {
    mockApi(defaultRoutes());
    renderWithApp(
      <NextScheduled schedule={{ next: {}, error: "schedule: bad time '25:00'" }} catchUp={null} now={NOW} />,
    );
    expect(screen.getByText(/schedule: bad time/)).toBeInTheDocument();
  });

  it("catch-up banner lists the missed runs; Catch up now posts dismiss:false and reports", async () => {
    const user = userEvent.setup();
    const calls = mockApi({ ...defaultRoutes(), "POST /api/runs/catch-up": { pending: true, kinds: ["score"], started: true } });
    renderWithApp(<NextScheduled schedule={status.schedule!} catchUp={catchUp} now={NOW} />);
    expect(screen.getByText("3 runs missed")).toBeInTheDocument();
    expect(screen.getByText(/Score: 1 missed since 1:00 AM/)).toBeInTheDocument();
    expect(screen.getByText(/Prepare: 2 missed since 2:00 AM/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Catch up now" }));
    expect(await screen.findByText("Catch-up run started.")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/runs/catch-up");
    expect(post?.body).toEqual({ dismiss: false });
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("Skip missed runs posts dismiss:true and says when they run", async () => {
    const user = userEvent.setup();
    const calls = mockApi({ ...defaultRoutes(), "POST /api/runs/catch-up": { status: "ok", dismissed: true } });
    renderWithApp(<NextScheduled schedule={status.schedule!} catchUp={catchUp} now={NOW} />);
    await user.click(screen.getByRole("button", { name: "Skip missed runs" }));
    expect(await screen.findByText("Missed runs skipped. They run at their next scheduled time.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/runs/catch-up")?.body).toEqual({ dismiss: true });
  });

  it("shows the server's reason when catch-up is refused", async () => {
    const user = userEvent.setup();
    mockApi({ ...defaultRoutes(), "POST /api/runs/catch-up": { $status: 409, body: { detail: "A batch is already running" } } });
    renderWithApp(<NextScheduled schedule={status.schedule!} catchUp={catchUp} now={NOW} />);
    await user.click(screen.getByRole("button", { name: "Catch up now" }));
    expect(await screen.findByText(/A batch is already running/)).toBeInTheDocument();
  });

  it("has no axe violations with the banner", async () => {
    mockApi(defaultRoutes());
    const { container } = renderWithApp(<NextScheduled schedule={status.schedule!} catchUp={catchUp} now={NOW} />);
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("PipelineChart", () => {
  it("draws bars to scale of the largest column with the numbers as text", () => {
    mockApi(defaultRoutes());
    const { container } = renderWithApp(<PipelineChart columns={status.pipeline!.columns!} />);
    expect(screen.getByText("Bars to scale of 412 (Found)")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual(["Found412", "Queued23", "Applied41", "Offer0"]);
    const fills = container.querySelectorAll<HTMLElement>("[data-bar]");
    expect(fills[0]!.style.width).toBe("100%");
    expect(fills[2]!.style.width).toBe(`${(41 / 412) * 100}%`);
    expect(fills[3]!.style.width).toBe("0%");
    for (const f of fills) expect(f.closest("[aria-hidden='true']")).not.toBeNull();
  });

  it("uses column names from the config and colours by the column's first status", () => {
    mockApi(defaultRoutes());
    const { container } = renderWithApp(
      <PipelineChart columns={[{ name: "Talking", statuses: ["interview", "screening"], count: 3 }, { name: "Odd", statuses: ["weird"], count: 1 }]} />,
    );
    expect(screen.getByText("Talking")).toBeInTheDocument();
    const fills = container.querySelectorAll<HTMLElement>("[data-bar]");
    expect(fills[0]).toHaveAttribute("data-tone", "purple");
    expect(fills[1]).toHaveAttribute("data-tone", "gray");
  });

  it("says there is nothing yet when every column is empty", () => {
    mockApi(defaultRoutes());
    renderWithApp(<PipelineChart columns={[{ name: "Found", statuses: ["found"], count: 0 }]} />);
    expect(screen.getByText("No jobs yet")).toBeInTheDocument();
  });
});

describe("PausedBanner", () => {
  it("says until when and resumes", async () => {
    const user = userEvent.setup();
    const calls = mockApi({ ...defaultRoutes(), "POST /api/runs/resume": { resumed: true } });
    renderWithApp(<PausedBanner paused={{ until: "2026-09-25T14:00:00Z", reason: "" }} now={NOW} />);
    expect(screen.getByText("Runs paused until 2:00 PM")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/runs/resume")).toBe(true));
  });

  it("without an end time says until you resume", () => {
    mockApi(defaultRoutes());
    renderWithApp(<PausedBanner paused={{ until: null }} now={NOW} />);
    expect(screen.getByText("Runs paused until you resume")).toBeInTheDocument();
  });
});
