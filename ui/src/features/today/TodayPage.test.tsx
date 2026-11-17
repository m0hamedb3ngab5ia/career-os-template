import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { TodayPage } from "./TodayPage";
import { formatRelative } from "../../lib/format";
import { defaultRoutes, mockApi, NOW, renderWithApp, today, type Routes } from "./testing";

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
  it("has the large title, the local date and one lead sentence", async () => {
    setup();
    expect(screen.getByRole("heading", { level: 1, name: "Today" })).toBeInTheDocument();
    expect(await screen.findByText("One application is ready to send. 3 other things need a look.")).toBeInTheDocument();
    expect(screen.getByText(/Friday, September 25/)).toBeInTheDocument();
    expect(document.title).toBe("Today · career-os");
  });

  it("is one column: sections, one quiet footer; no activity or job-search panels, runs, schedule or run buttons", async () => {
    setup();
    expect(await screen.findByRole("heading", { level: 2, name: /Needs you/ })).toBeInTheDocument();
    for (const gone of ["Recent activity", "Job search", "Recent runs", "Next scheduled", "Pipeline", "Top picks"])
      expect(screen.queryByRole("heading", { name: gone })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run scout|Prepare queued/ })).not.toBeInTheDocument();
  });

  it("footer shows counts, the last run in plain words, and a link to all jobs", async () => {
    setup();
    const footer = (await screen.findByText(/applications in progress/)).closest("footer")!;
    expect(footer).toHaveTextContent("41 applications in progress · 412 new matches · All jobs");
    expect(within(footer).getByRole("link", { name: "All jobs" })).toHaveAttribute("href", "/jobs");
    expect(footer).toHaveTextContent(/Last run: found 38 new matching jobs/);
    expect(footer).not.toHaveTextContent(/\b(scout|prepare|score)\b/i);
  });

  const pick = (id: string, over = {}) => ({ job_id: id, title: `Role ${id}`, company: "Acme", location: "Remote", fit: 88, tier: "A",
    found_at: "2026-09-24", reasons: { covered: 7, total: 10, missing: ["Go", "Kubernetes", "Rust"] }, ...over });
  const ready = { ready: true, items: [{ id: "a", label: "Item a", must: true, done: true, fix_link: "/nope" }] };
  const pstate = { stage: "scored", next_action: "start", next_kind: "prepare", active_run_id: null, failures: null };

  it("shows Top picks when there are some, with each pick's age from found_at (REQ-130)", async () => {
    setup({ "GET /api/readiness": ready, "GET /api/today": { ...today, top_picks: [pick("j1")] }, "GET /api/jobs/j1/pipeline": pstate });
    expect(await screen.findByRole("heading", { name: "Top picks" })).toBeInTheDocument();
    expect(await screen.findByText(`Acme · Remote · ${formatRelative("2026-09-24", NOW)}`)).toBeInTheDocument();
  });

  it("hides Top picks when there are none", async () => {
    setup({ "GET /api/readiness": ready });
    await screen.findByText(/ready to send/);
    expect(screen.queryByRole("heading", { name: "Top picks" })).not.toBeInTheDocument();
    expect(screen.queryByText("No new picks right now")).not.toBeInTheDocument();
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
    expect(await screen.findByText("You’re all caught up.")).toBeInTheDocument();
    expect(await screen.findByText(/^Nothing needs you\./)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("contentinfo")).toHaveTextContent("0 applications in progress · 0 new matches"));
    expect(screen.queryByRole("heading", { name: "Top picks" })).not.toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByText(/ready to send/);
    expect(await axeViolations(container)).toEqual([]);
  });
});
