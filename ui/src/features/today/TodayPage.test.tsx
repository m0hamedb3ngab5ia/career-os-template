import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { TodayPage } from "./TodayPage";
import userEvent from "@testing-library/user-event";
import { defaultRoutes, mockApi, NOW, renderWithApp, status, today, type Routes } from "./testing";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function setup(routes: Routes = {}, path = "/") {
  const calls = mockApi({ ...defaultRoutes(), ...routes });
  return { ...renderWithApp(<TodayPage />, { path }), calls };
}

describe("TodayPage", () => {
  it("has the large title, the local date and how many items need you", async () => {
    setup();
    expect(screen.getByRole("heading", { level: 1, name: "Today" })).toBeInTheDocument();
    expect(await screen.findByText("Friday, September 25 · 4 jobs need you")).toBeInTheDocument();
    expect(document.title).toBe("Today · career-os");
  });

  it("is one column: tasks, recent activity and job search; no runs, schedule, chart or run buttons", async () => {
    setup();
    expect(await screen.findByRole("heading", { name: /Needs your attention/ })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Recent activity" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Job search" })).toBeInTheDocument();
    for (const gone of ["Recent runs", "Next scheduled", "Pipeline", "Before you apply"])
      expect(screen.queryByRole("heading", { name: gone })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run scout|Prepare queued/ })).not.toBeInTheDocument();
  });

  it("recent activity shows at most 3 outcomes, no run names, and links to all activity", async () => {
    const run = (id: string, kind: string, over = {}) => ({ ...status.recent_runs![0]!, id, kind, detail: "", ...over });
    setup({ "GET /api/status": { ...status, recent_runs: [
      run("a", "scout", { detail: "38 new of 412 scanned" }), run("b", "prepare", { ok: 2 }), run("c", "inbox_sync"),
      run("d", "apply", { ok: 1 }), run("e", "score", { ok: 5 }),
    ] } });
    const section = (await screen.findByRole("heading", { name: "Recent activity" })).closest("section")!;
    expect(within(section).getAllByRole("listitem").map((li) => li.firstChild?.textContent)).toEqual([
      "Found 38 new matching jobs", "Prepared 2 applications", "Filled 1 application"]);
    expect(within(section).queryByText(/\b(scout|prepare|score|apply)\b/i)).not.toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "View all activity" })).toHaveAttribute("href", "/runs");
  });

  it("job search is one line of counts with a pipeline link", async () => {
    setup();
    const section = (await screen.findByRole("heading", { name: "Job search" })).closest("section")!;
    expect(within(section).getByText("412 new matches · 0 need review · 41 applications active")).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "View pipeline" })).toHaveAttribute("href", "/pipeline");
  });

  const item = (id: string, must: boolean, done: boolean, fix = "/profile") => ({ id, label: `Item ${id}`, must, done, fix_link: fix });
  const pick = (id: string, over = {}) => ({ job_id: id, title: `Role ${id}`, company: "Acme", location: "Remote", fit: 88, tier: "A",
    found_at: "2026-09-24", reasons: { covered: 7, total: 10, missing: ["Go", "Kubernetes", "Rust"] }, ...over });
  const ready = { ready: true, items: [item("a", true, true)] };

  it("setup card (REQ-131): ring, one primary button to the first open item, show all", async () => {
    // E2E-015-05
    setup({ "GET /api/readiness": { ready: false, items: [item("a", true, true), item("b", true, false, "/profile#b"), item("c", true, false), item("d", true, true), item("e", true, true), item("f", false, false)] } });
    const card = (await screen.findByRole("heading", { name: "Finish setup" })).closest("section")!;
    expect(within(card).getByText("3/5")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Finish setup" })).toHaveAttribute("href", "/profile#b");
    expect(within(card).queryByText("To do: Item b")).not.toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Show all (5)" }));
    expect(within(card).getByText("To do: Item b")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Top picks/ })).not.toBeInTheDocument();
  });

  it("no setup card once every must-have is done; Top picks band instead (E2E-015-01, E2E-014-02)", async () => {
    setup({ "GET /api/readiness": ready, "GET /api/today": { ...today, top_picks: [pick("j1"), pick("j2", { fit: 70, reasons: null })] } });
    const band = (await screen.findByRole("heading", { name: "Top picks" })).closest("section")!;
    expect(screen.queryByRole("heading", { name: "Finish setup" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Next step" })).not.toBeInTheDocument();
    const links = within(band).getAllByRole("link").slice(1); // [0] = "All jobs"
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/jobs/j1", "/jobs/j2"]);
    expect(within(band).getByText("7/10 skills · missing: Go, Kubernetes, +1")).toBeInTheDocument();
    expect(within(band).getByText("Match pending")).toBeInTheDocument();
    expect(within(band).getByText("88")).toBeInTheDocument();
  });

  it("Top picks empty state links to the Jobs page", async () => {
    setup({ "GET /api/readiness": ready });
    const band = (await screen.findByRole("heading", { name: "Top picks" })).closest("section")!;
    expect(within(band).getByText("No new picks right now")).toBeInTheDocument();
    expect(within(band).getByRole("link", { name: "Browse all jobs" })).toHaveAttribute("href", "/jobs");
  });

  it("shows loading placeholders before data arrives", () => {
    setup({ "GET /api/status": () => new Promise<Response>(() => {}), "GET /api/today": () => new Promise<Response>(() => {}) });
    expect(screen.getByRole("img", { name: "Loading tasks" })).toBeInTheDocument();
  });

  it("shows the server's error with Retry when status can't load", async () => {
    setup({ "GET /api/status": { $status: 503, body: { detail: "config error: targets.yaml" } } });
    expect(await screen.findByText(/config error: targets\.yaml/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("while runs are paused the banner offers Resume", async () => {
    setup({ "GET /api/status": { ...status, paused: { until: null, reason: "travelling" } } });
    expect(await screen.findByText("Runs paused until you resume")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume" })).toBeEnabled();
  });

  it("renders with an empty API (a fresh install) without inventing data", async () => {
    setup({ "GET /api/status": {}, "GET /api/today": {}, "GET /api/meta": {} });
    expect(await screen.findByText("Friday, September 25 · nothing needs you")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Nothing needs you" })).toBeInTheDocument();
    expect(screen.getByText("Nothing yet")).toBeInTheDocument();
    expect(screen.getByText("0 new matches · 0 need review · 0 applications active")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByText("Interview invite: pick a slot");
    expect(await axeViolations(container)).toEqual([]);
  });
});
