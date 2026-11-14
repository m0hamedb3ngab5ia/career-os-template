import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { TodayPage } from "./TodayPage";
import { formatRelative } from "../../lib/format";
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

  it("recent activity shows at most 3 outcomes, no run names,", async () => {
    const run = (id: string, kind: string, over = {}) => ({ ...status.recent_runs![0]!, id, kind, detail: "", ...over });
    setup({ "GET /api/status": { ...status, recent_runs: [
      run("a", "scout", { detail: "38 new of 412 scanned" }), run("b", "prepare", { ok: 2 }), run("c", "inbox_sync"),
      run("d", "apply", { ok: 1 }), run("e", "score", { ok: 5 }),
    ] } });
    const section = (await screen.findByRole("heading", { name: "Recent activity" })).closest("section")!;
    expect(within(section).getAllByRole("listitem").map((li) => li.firstChild?.textContent)).toEqual([
      "Found 38 new matching jobs", "Prepared 2 applications", "Filled 1 application"]);
    expect(within(section).queryByText(/\b(scout|prepare|score|apply)\b/i)).not.toBeInTheDocument();
  });

  it("job search is one line of counts with a pipeline link", async () => {
    setup();
    const section = (await screen.findByRole("heading", { name: "Job search" })).closest("section")!;
    expect(within(section).getByText("412 new matches · 0 need review · 41 applications active")).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "View pipeline" })).toHaveAttribute("href", "/pipeline");
  });

  const item = (id: string, must: boolean, done: boolean, fix = "/nope") => ({ id, label: `Item ${id}`, must, done, fix_link: fix });
  const pick = (id: string, over = {}) => ({ job_id: id, title: `Role ${id}`, company: "Acme", location: "Remote", fit: 88, tier: "A",
    found_at: "2026-09-24", reasons: { covered: 7, total: 10, missing: ["Go", "Kubernetes", "Rust"] }, ...over });
  const ready = { ready: true, items: [item("a", true, true)] };



  const pstate = (over = {}) => ({ stage: "scored", next_action: "start", next_kind: "prepare", active_run_id: null, failures: null, ...over });
  const picksSetup = (routes: Routes = {}) =>
    setup({ "GET /api/readiness": ready, "GET /api/today": { ...today, top_picks: [pick("j1")] }, "GET /api/jobs/j1/pipeline": pstate(), ...routes });



  it("each pick shows its age from found_at (REQ-130)", async () => {
    picksSetup();
    expect(await screen.findByText(`Acme · Remote · ${formatRelative("2026-09-24", NOW)}`)).toBeInTheDocument();
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
