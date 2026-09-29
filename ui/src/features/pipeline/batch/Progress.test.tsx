import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../../app/routes";
import { FakeEventSource } from "../../../test/fakeEventSource";
import { META, mockApi, renderRoutes } from "../../../test/mockApi";
import { today } from "../../today/testing";
import type { Batch } from "./api";
import { countsLine } from "./Progress";

// Fictional companies only.
function job(job_id: string, company: string, state: string | null, reason: string | null = null) {
  return { job_id, company, title: "Backend Engineer", status: "scored", fit: 80, score: 1, why: "", rank: 1,
    stage: "apply", stages: ["apply"], auto_submit: false, submit_reason: "", state, reason };
}

function batch(status: string, selected = [job("j-acme", "Acme Robotics", "working")], over: Partial<Batch> = {}): Batch {
  return { id: "b-1", name: "New grad SWE", status, dry_run: false, stop_at: "fill", kind: "apply", selected, excluded: [], ...over };
}

function setup(b: Batch | (() => Batch), path = "/pipeline/batch/b-1", extra: Record<string, unknown> = {}) {
  const calls = mockApi({
    "GET /api/meta": META,
    "GET /api/status": {},
    "GET /api/batches/b-1": b,
    "POST /api/batches/b-1/pause": { ...(typeof b === "function" ? b() : b), requested: "pause" },
    "POST /api/batches/b-1/cancel": batch("cancelled", [job("j-acme", "Acme Robotics", "cancelled", "batch cancelled")]),
    "POST /api/batches/b-1/retry": batch("paused", [job("j-acme", "Acme Robotics", "pending")]),
    "POST /api/batches/b-1/start": batch("running"),
    ...extra,
  });
  return { calls, ...renderRoutes(routes, path) };
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const opts = { timeout: 8000 };
const posts = (calls: { method: string; url: string }[]) => calls.filter((c) => c.method === "POST").map((c) => c.url);

describe("countsLine", () => {
  it("buckets job states, not-started and pending as waiting, zeros left out", () => {
    const rows = [job("a", "A", "done"), job("b", "B", null), job("c", "C", "pending"), job("d", "D", "needs_you")];
    expect(countsLine(rows)).toBe("4 selected · 1 done · 1 need you · 2 waiting");
  });
});

describe("Batch progress", () => {
  it("running: shows counts and pauses after the current job", async () => {
    const { calls } = setup(batch("running", [job("j-acme", "Acme Robotics", "working", "filling"), job("j-hooli", "Hooli", null)]));
    expect(await screen.findByText(/Running · 2 selected · 1 working · 1 waiting/, {}, opts)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Hooli · Backend Engineer" })).toHaveAttribute("href", "/jobs/j-hooli");
    await userEvent.click(screen.getByRole("button", { name: "Pause after this job" }));
    expect(await screen.findByText("Pausing after the current job…")).toBeInTheDocument();
    expect(posts(calls)).toEqual(["/api/batches/b-1/pause"]);
  });

  it("paused: shows the reason and resumes", async () => {
    const { calls } = setup(batch("paused", undefined, { reason: "usage_limit: batch paused" }));
    expect(await screen.findByText(/Paused · usage_limit: batch paused/, {}, opts)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(posts(calls)).toEqual(["/api/batches/b-1/start"]));
  });

  it("cancel asks first, then cancels", async () => {
    const { calls } = setup(batch("running"));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel batch" }, opts));
    expect(posts(calls)).toEqual([]);
    expect(screen.getByText("Cancel this batch?")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Cancel batch" }).at(-1)!);
    expect(await screen.findByText(/^Cancelled ·/)).toBeInTheDocument();
    expect(posts(calls)).toEqual(["/api/batches/b-1/cancel"]);
  });

  it("done with failures: retries the failed jobs and restarts the driver", async () => {
    const { calls } = setup(batch("done", [job("j-acme", "Acme Robotics", "failed", "timeout"), job("j-hooli", "Hooli", "done", "submitted")]));
    expect(await screen.findByText(/Done · 2 selected · 1 done · 1 failed/, {}, opts)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel batch" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry 1 job" }));
    await waitFor(() => expect(posts(calls)).toEqual(["/api/batches/b-1/retry", "/api/batches/b-1/start"]));
  });

  it("needs review: links to Today filtered by the batch, which shows only its jobs", async () => {
    setup(batch("done", [job("j-acme", "Acme Robotics", "needs_you", "staged: review and submit it yourself")]), undefined,
      { "GET /api/today": today });
    expect(await screen.findByText("staged: review and submit it yourself", {}, opts)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Review 1 in Today" }));
    expect(await screen.findByText(/Only jobs in/, {}, opts)).toBeInTheDocument();
    expect(await screen.findByText("Acme Robotics", {}, opts)).toBeInTheDocument();
    expect(screen.queryByText("Globex")).toBeNull();
  });

  it("refetches when the SSE changed event names the batch", async () => {
    let b = batch("running");
    setup(() => b);
    expect(await screen.findByText(/Running/, {}, opts)).toBeInTheDocument();
    b = batch("done", [job("j-acme", "Acme Robotics", "done", "submitted")]);
    act(() => FakeEventSource.last.dispatch("changed", { batches: ["b-1"] }));
    expect(await screen.findByText(/Done · 1 selected · 1 done/, {}, opts)).toBeInTheDocument();
  });
});
