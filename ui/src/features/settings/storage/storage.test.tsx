import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../../test/axe";
import { type Call, field, mockApi, renderSettings, route, sectionRoutes } from "../testing";
import type { Advice, SectionData, Snapshot, StorageData } from "../types";
import { weeklySnapshots } from "./StorageChart";

const MB = 1024 * 1024;

function snap(at: string, shots: number): Snapshot {
  return {
    at,
    bytes: { screenshots: shots * MB, postings: 5 * MB, resumes_pdfs: MB, run_logs: MB, tracker: MB / 2, other: MB / 2 },
    total: (shots + 8) * MB,
  };
}

function storageSection(): SectionData {
  const budget = field({ file: "pipeline", key: "storage.budget_mb", control: "number", label: "Storage budget", default: 1024, unit: "MB" });
  return {
    section: {
      id: "storage",
      title: "Storage & efficiency",
      help: "",
      files: ["pipeline"],
      groups: [{ id: "limits", title: "Storage limits", help: "", items: [budget] }],
    },
    values: { [budget.id]: 1024 },
    defaults: {},
    files: { pipeline: "config/pipeline.yaml" },
    version: "v1",
  };
}

function storage(snapshots: Snapshot[]): StorageData {
  return {
    bytes: { screenshots: 20 * MB, postings: 5 * MB },
    total: 25 * MB,
    disk: { total: 500 * 1024 * MB, free: 20 * 1024 * MB, free_pct: 4 },
    snapshots,
    config: {
      storage: { budget_mb: 1024, warn_at_pct: 80, disk_free_warn_pct: 10 },
      advisor: { advise_after_days: 14, min_runs: 5, window_days: 30 },
    },
  };
}

const READY: Advice = {
  storage: { ready: true, days: 21, need_days: 14, current: 25 * MB, rate_per_day: MB, projection: { "30d": 55 * MB, "90d": 115 * MB }, budget: 1024 * MB },
  runs: {
    ready: true,
    min_runs: 5,
    metrics: {
      score: { runs: 6, attempts: 60, avg_job_s: 52, p90_job_s: 80, failure_rate: 0.1, failed: 7, budget_used: 0.8, stops: { usage_limit: 2 }, prepare_share: 0.18 },
    },
  },
  recommendations: [
    {
      id: "tighten-screenshots_after_closed_days",
      kind: "storage",
      severity: "warn",
      title: "Prune screenshots sooner",
      why: "screenshots are the biggest part",
      change: { file: "config/pipeline.yaml", path: "retention.screenshots_after_closed_days", from: 30, to: 14 },
    },
    { id: "failures-score", kind: "runs", severity: "warn", title: "score jobs fail often", why: "30% failed", change: null },
  ],
};

const EMPTY: Advice = {
  storage: { ready: false, days: 3, need_days: 14 },
  runs: { ready: false, min_runs: 5, metrics: {} },
  recommendations: [],
};

function setup(adv: Advice = READY, snaps: Snapshot[] = [snap("2026-09-01T10:00:00Z", 10), snap("2026-09-09T10:00:00Z", 14)], extra: Parameters<typeof mockApi> = []) {
  const calls = mockApi(
    ...sectionRoutes(storageSection()),
    route("GET", "/api/storage", storage(snaps)),
    route("GET", "/api/advise", adv),
    ...extra,
  );
  const utils = renderSettings("/settings/storage");
  return { calls, ...utils };
}

beforeEach(() => {
  try {
    window.localStorage.clear();
  } catch {
    /* ignore */
  }
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("weeklySnapshots", () => {
  it("keeps the last snapshot of each week, oldest first, with Other folded", () => {
    const weeks = weeklySnapshots(
      [snap("2026-09-09T10:00:00Z", 14), snap("2026-09-01T10:00:00Z", 10), snap("2026-09-02T10:00:00Z", 11)],
      "en-US",
    );
    expect(weeks.map((w) => w.label)).toEqual(["Aug 31", "Sep 7"]);
    expect(weeks[0]!.values).toEqual([11, 5, 1, 1, 1]);
    expect(weeks[1]!.total).toBeCloseTo(22);
  });
});

describe("Storage & efficiency", () => {
  it("shows tiles, the chart with focusable bars and a table view in the URL", async () => {
    const user = userEvent.setup();
    const { router } = setup();
    expect(await screen.findByRole("region", { name: "career-os data" }, { timeout: 10_000 })).toHaveTextContent("25 MB");
    expect(screen.getByRole("region", { name: "Mac disk free" })).toHaveTextContent("below your 10% warning");
    expect(await screen.findByRole("region", { name: "Failure rate" })).toHaveTextContent("7 of 60 jobs");
    const plot = await screen.findByRole("group", { name: /Storage by week/ });
    const bars = within(plot).getAllByRole("button");
    expect(bars.map((b) => b.getAttribute("tabindex"))).toEqual(["-1", "0"]);
    bars[1]!.focus();
    await user.keyboard("{ArrowLeft}");
    expect(bars[0]).toHaveFocus();
    expect(bars[0]).toHaveAccessibleName(/Week of .*: 18 MB\. Screenshots 10/);
    expect(screen.getByText(/Week of .* · 18 MB/)).toBeInTheDocument(); // tooltip on focus
    await user.click(screen.getByText("Show as table"));
    await waitFor(() => expect(router.state.location.search).toBe("?table=storage"));
    expect(screen.getByRole("table", { name: "Storage by week, in MB" })).toBeInTheDocument();
  });

  it("Apply calls advise apply; Dismiss hides with Undo; advice-only rows say Got it", async () => {
    const user = userEvent.setup();
    const { calls } = setup(READY, undefined, [
      route("POST", "/api/advise/tighten-screenshots_after_closed_days/apply", {
        id: "tighten-screenshots_after_closed_days", path: "retention.screenshots_after_closed_days", from: 30, to: 14,
      }),
    ]);
    expect(await screen.findByText("retention.screenshots_after_closed_days: 30 → 14")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Apply: Prune screenshots sooner" }));
    expect(await screen.findByText("Applied retention.screenshots_after_closed_days: 30 → 14.")).toBeInTheDocument();
    const apply = calls.find((c) => c.method === "POST" && c.url.includes("/apply"));
    expect(apply?.headers.get("X-CareerOS")).toBe("1");
    await waitFor(() => expect(calls.filter((c) => c.url === "/api/advise").length).toBeGreaterThan(1));

    await user.click(screen.getByRole("button", { name: "Got it: score jobs fail often" }));
    expect(screen.queryByText("score jobs fail often")).not.toBeInTheDocument();
    expect(screen.getByText("Dismissed: score jobs fail often")).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem("careeros.settings.dismissed-advice")!)).toEqual(["failures-score"]);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.getByText("score jobs fail often")).toBeInTheDocument();
  });

  it("still works when localStorage throws", async () => {
    const user = userEvent.setup();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    setup();
    await user.click(await screen.findByRole("button", { name: "Dismiss: Prune screenshots sooner" }));
    expect(screen.queryByText("Prune screenshots sooner")).not.toBeInTheDocument();
  });

  it("empty data: no snapshots, no runs, collecting advice", async () => {
    setup(EMPTY, []);
    expect(await screen.findByRole("heading", { name: "No storage snapshots yet" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "No score or prepare runs yet" })).toBeInTheDocument();
    expect(screen.getByText("Collecting data: 3 of 14 days of storage snapshots")).toBeInTheDocument();
    expect(screen.getByText(/All caught up/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Growth" })).toHaveTextContent("—");
  });

  it("Prune now lists the dry run, confirms, then starts the step", async () => {
    const user = userEvent.setup();
    const { calls } = setup(EMPTY, [], [
      route("POST", "/api/prune", (c: Call) =>
        (c.body as { dry_run: boolean }).dry_run
          ? {
              dry_run: true,
              items: [{ job_id: "acme-1", action: "delete_screenshots", paths: ["a.png"], bytes: 2 * MB, run_id: "" }],
              summary: { jobs: 1, runs: 0, files: 1, bytes: 2 * MB },
            }
          : { kind: "prune", started: true, pid: 1 },
      ),
    ]);
    await user.click(await screen.findByRole("button", { name: "See what would be removed" }));
    const list = await screen.findByRole("list", { name: "What prune would remove" });
    expect(list).toHaveTextContent("Screenshots of a closed job");
    const confirm = screen.getByRole("alertdialog", { name: /Remove 1 file \(2(\.0)? MB\)\?/ });
    await user.click(within(confirm).getByRole("button", { name: "Prune" }));
    expect(await screen.findByText("Prune started. Progress is on the Runs page.")).toBeInTheDocument();
    expect(calls.filter((c) => c.url === "/api/prune").map((c) => c.body)).toEqual([{ dry_run: true }, { dry_run: false }]);
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByRole("group", { name: /Storage by week/ });
    await screen.findByText("Prune screenshots sooner");
    expect(await axeViolations(container)).toEqual([]);
  });
});
