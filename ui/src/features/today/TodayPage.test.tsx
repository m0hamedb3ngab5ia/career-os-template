import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { TodayPage } from "./TodayPage";
import { defaultRoutes, mockApi, NOW, renderWithApp, status, type Routes } from "./testing";

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

  it("shows the setup banner only while required items are left", async () => {
    const item = (id: string, must: boolean, done: boolean) => ({ id, label: id, must, done, fix_link: null });
    setup({ "GET /api/readiness": { ready: false, items: [item("a", true, false), item("b", true, false), item("c", false, false), item("d", true, true)] } });
    expect(await screen.findByText("Finish setup: 2 required items remaining")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Finish setup" })).toHaveAttribute("href", "/profile");
  });

  it("hides the setup banner when setup is complete", async () => {
    setup({ "GET /api/readiness": { ready: true, items: [{ id: "a", label: "a", must: true, done: true, fix_link: null }] } });
    await screen.findByRole("heading", { name: "Job search" });
    expect(screen.queryByText(/Finish setup/)).not.toBeInTheDocument();
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
