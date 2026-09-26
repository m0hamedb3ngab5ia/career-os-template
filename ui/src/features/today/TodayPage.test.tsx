import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { TodayPage } from "./TodayPage";
import { defaultRoutes, json, mockApi, NOW, renderWithApp, status, today, type Routes } from "./testing";

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
    expect(await screen.findByText("Friday, September 25 · 4 items need you")).toBeInTheDocument();
    expect(document.title).toBe("Today · career-os");
  });

  it("renders every section from the API", async () => {
    setup();
    expect(await screen.findByRole("button", { name: /Applied this week/ })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /Needs you 4/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent runs" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Next scheduled" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Pipeline" })).toBeInTheDocument();
  });

  it("shows loading placeholders before data arrives", () => {
    setup({ "GET /api/status": () => new Promise<Response>(() => {}), "GET /api/today": () => new Promise<Response>(() => {}) });
    expect(screen.getByRole("img", { name: "Loading today’s numbers" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Loading action items" })).toBeInTheDocument();
  });

  it("shows the server's error with Retry when status can't load", async () => {
    setup({ "GET /api/status": { $status: 503, body: { detail: "config error: targets.yaml" } } });
    expect(await screen.findByText(/config error: targets\.yaml/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  describe("header actions", () => {
    it("Run scout posts, reads Starting… while pending, then confirms", async () => {
      const user = userEvent.setup();
      let release!: () => void;
      const { calls } = setup({
        "POST /api/runs/steps/scout": () =>
          new Promise<Response>((res) => {
            release = () => res(json({ kind: "scout", started: true, pid: 42 }));
          }),
      });
      await screen.findByText(/items need you/);
      await user.click(screen.getByRole("button", { name: "Run scout" }));
      expect(await screen.findByRole("button", { name: "Starting…" })).toBeDisabled();
      release();
      expect(await screen.findByText("Scout started.")).toBeInTheDocument();
      expect(calls.find((c) => c.path === "/api/runs/steps/scout")?.headers.get("X-CareerOS")).toBe("1");
    });

    it("a refused run shows the server's detail in a toast", async () => {
      const user = userEvent.setup();
      setup({ "POST /api/runs/steps/scout": { $status: 409, body: { detail: "scout is already running" } } });
      await screen.findByText(/items need you/);
      await user.click(screen.getByRole("button", { name: "Run scout" }));
      const msg = await screen.findByText(/scout is already running/);
      expect(msg.closest("[aria-live]")).not.toBeNull();
      expect(screen.getByRole("button", { name: "Run scout" })).toBeEnabled();
    });

    it("Prepare queued shows the queue size and posts the recommended preset", async () => {
      const user = userEvent.setup();
      const { calls } = setup({ "POST /api/runs/batches/prepare": { kind: "prepare", started: true } });
      const btn = await screen.findByRole("button", { name: "Prepare queued (3)" });
      await waitFor(() => expect(btn).toBeEnabled());
      await user.click(btn);
      expect(await screen.findByText("Prepare started.")).toBeInTheDocument();
      expect(calls.find((c) => c.path === "/api/runs/batches/prepare")?.body).toEqual({ preset: "medium" });
    });

    it("Prepare is disabled with a reason when nothing is queued", async () => {
      setup({ "GET /api/today": { ...today, prepare_queue: { total: 0, error: null } } });
      const btn = await screen.findByRole("button", { name: "Prepare queued (0)" });
      expect(btn).toBeDisabled();
      expect(screen.getByText("Nothing is queued to prepare.")).toBeInTheDocument();
      expect(btn).toHaveAccessibleDescription("Nothing is queued to prepare.");
    });

    it("Prepare is disabled with the server's reason when the queue size is unknown", async () => {
      setup({ "GET /api/today": { ...today, prepare_queue: { total: null, error: "Queue unavailable: no scores yet" } } });
      expect(await screen.findByText("Queue unavailable: no scores yet")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Prepare queued" })).toBeDisabled();
    });

    it("while runs are paused Prepare is disabled (scout still runs) and the banner offers Resume", async () => {
      setup({ "GET /api/status": { ...status, paused: { until: null, reason: "travelling" } } });
      expect(await screen.findByText("Runs paused until you resume")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Resume" })).toBeEnabled();
      expect(screen.getByRole("button", { name: "Prepare queued (3)" })).toBeDisabled();
      expect(screen.getByText("Runs are paused.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Run scout" })).toBeEnabled();
    });
  });

  it("shows the catch-up banner from status", async () => {
    setup({
      "GET /api/status": {
        ...status,
        catch_up: { kinds: { score: { first_missed: "2026-09-25T01:00:00Z", slots: 1 } } },
      },
    });
    const section = (await screen.findByRole("heading", { name: "Next scheduled" })).closest("section")!;
    expect(within(section).getByText("1 run missed")).toBeInTheDocument();
  });

  it("renders with an empty API (a fresh install) without inventing data", async () => {
    setup({ "GET /api/status": {}, "GET /api/today": {}, "GET /api/meta": {} });
    expect(await screen.findByText("Friday, September 25 · 0 items need you")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Nothing needs you" })).toBeInTheDocument();
    expect(screen.getByText("No runs yet")).toBeInTheDocument();
    expect(screen.getByText("No jobs yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Response rate/ })).toHaveTextContent("—");
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByText("Globex");
    expect(await axeViolations(container)).toEqual([]);
  });
});
