import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
import { FakeEventSource } from "../../test/fakeEventSource";
import { fakeLayout } from "../runs/testUtils";
import { PipelineCard } from "./PipelineCard";
import { renderWithProviders } from "./testUtils";
import type { PipelineState } from "./types";

const base: PipelineState = {
  stage: "prepare",
  next_action: "continue",
  next_label: "Continue pipeline",
  next_kind: "prepare",
  force: false,
  blocked_reason: null,
  review_reasons: [],
  active_run_id: null,
  queued_in_run: null,
};

let restore: () => void;
beforeEach(() => {
  restore = fakeLayout();
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => {
  restore();
  vi.unstubAllGlobals();
});

function setup(state: Partial<PipelineState>, extra: Parameters<typeof mockApi>[0] = {}) {
  let current: PipelineState = { ...base, ...state };
  const api = mockApi({
    "GET /api/jobs/j1/pipeline": () => current,
    "POST /api/jobs/j1/pipeline": () => {
      current = { ...current, active_run_id: "20260927-100000-apply-ab12" };
      return { run_id: "20260927-100000-apply-ab12", kind: "apply" };
    },
    "POST /api/runs/cancel": { cancelled: true },
    ...extra,
  });
  renderWithProviders(<PipelineCard jobId="j1" />);
  return api;
}

describe("PipelineCard", () => {
  it("highlights the stage and offers Start pipeline for a found job", async () => {
    setup({ stage: "score", next_action: "start", next_label: "Start pipeline", next_kind: "score" });
    const btn = await screen.findByRole("button", { name: "Start pipeline" });
    expect(btn).toBeEnabled();
    const steps = within(screen.getByRole("list", { name: "Pipeline stages" })).getAllByRole("listitem");
    expect(steps.map((s) => s.getAttribute("data-state"))).toEqual(["current", "upcoming", "upcoming", "upcoming", "upcoming"]);
    expect(steps[0]).toHaveAttribute("aria-current", "step");
  });

  it("lists the review reasons with Approve & continue for a needs_review job", async () => {
    setup({
      stage: "review",
      next_action: "approve_continue",
      next_label: "Approve & continue",
      next_kind: "apply",
      review_reasons: ["QA warning: long letter", "Open action item: Review and submit"],
    });
    expect(await screen.findByRole("button", { name: "Approve & continue" })).toHaveAttribute(
      "title",
      "Approves the current documents and lets the pipeline continue to the next step.",
    );
    expect(screen.getByText("Waiting on you")).toBeInTheDocument();
    expect(screen.getByText("Open action item: Review and submit")).toBeInTheDocument();
    const steps = within(screen.getByRole("list", { name: "Pipeline stages" })).getAllByRole("listitem");
    expect(steps.map((s) => s.getAttribute("data-state"))).toEqual(["done", "done", "done", "current", "upcoming"]);
  });

  it("disables the button with the blocked reason as its title (Tier A)", async () => {
    setup({ stage: "apply", next_action: null, next_label: null, next_kind: null,
            blocked_reason: "Tier A: never auto-applied; apply manually" });
    const btn = await screen.findByRole("button", { name: "Continue pipeline" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "Tier A: never auto-applied; apply manually");
    expect(screen.getByText("Tier A: never auto-applied; apply manually")).toBeInTheDocument();
  });

  it("says there is nothing to run for an applied job", async () => {
    setup({ stage: "apply", next_action: null, next_label: null, next_kind: null });
    expect(await screen.findByText("Nothing left to run for this job.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue pipeline" })).toBeDisabled();
  });

  it("starts the run, streams its output with Cancel, and refreshes when the stream ends", async () => {
    const api = setup({ stage: "apply", next_action: "continue", next_kind: "apply" });
    await userEvent.click(await screen.findByRole("button", { name: "Continue pipeline" }));
    expect(api.callsTo("POST /api/jobs/j1/pipeline")[0]?.body).toEqual({ action: "continue" });
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    expect(FakeEventSource.last.url).toBe("/api/runs/20260927-100000-apply-ab12/stream");
    act(() => {
      FakeEventSource.last.open();
      FakeEventSource.last.dispatch("event", { type: "log", text: "start apply (manual)" });
      FakeEventSource.last.dispatch("event", { type: "tool", text: "apply-job: filling the form", attempt: 1 });
    });
    expect(await screen.findByText("start apply (manual)")).toBeInTheDocument();
    expect(screen.getByText("apply-job: filling the form")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(api.callsTo("POST /api/runs/cancel")[0]?.body).toEqual({ run_id: "20260927-100000-apply-ab12" });
    const before = api.callsTo("GET /api/jobs/j1/pipeline").length;
    act(() => FakeEventSource.last.dispatch("end", { state: "finished", stop_reason: "completed" }));
    await waitFor(() => expect(api.callsTo("GET /api/jobs/j1/pipeline").length).toBeGreaterThan(before));
    expect(FakeEventSource.last.closed).toBe(true);
  });

  /** Start on a found job; the first POST scores it, the stream end flips the server state to `after`. */
  async function scoreThen(after: Partial<PipelineState>, stopAfter = false) {
    let current: PipelineState = { ...base, stage: "score", next_action: "start", next_label: "Start pipeline", next_kind: "score" };
    let n = 0;
    const api = mockApi({
      "GET /api/jobs/j1/pipeline": () => current,
      "POST /api/jobs/j1/pipeline": () => {
        n += 1;
        const kind = n === 1 ? "score" : "prepare";
        current = { ...current, active_run_id: `run-${n}-${kind}` };
        return { run_id: `run-${n}-${kind}`, kind };
      },
    });
    renderWithProviders(<PipelineCard jobId="j1" />);
    if (stopAfter) await userEvent.click(await screen.findByRole("checkbox", { name: "Stop after this stage" }));
    await userEvent.click(await screen.findByRole("button", { name: "Start pipeline" }));
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    expect(FakeEventSource.last.url).toBe("/api/runs/run-1-score/stream");
    current = { ...base, ...after, active_run_id: null };
    act(() => FakeEventSource.last.dispatch("end", { state: "finished", stop_reason: "completed" }));
    return api;
  }

  it("chains a scored job straight into prepare after Start pipeline", async () => {
    const api = await scoreThen({ stage: "prepare", next_action: "continue", next_kind: "prepare", force: false });
    await waitFor(() => expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(2));
    expect(api.callsTo("POST /api/jobs/j1/pipeline")[1]?.body).toEqual({ action: "continue" });
    expect(await screen.findByText(/Scored — continuing to prepare…/)).toBeInTheDocument();
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(2));
    expect(FakeEventSource.last.url).toBe("/api/runs/run-2-prepare/stream");
    act(() => FakeEventSource.last.dispatch("end", { state: "finished", stop_reason: "completed" }));
    await waitFor(() => expect(screen.queryByText(/Scored — continuing to prepare…/)).not.toBeInTheDocument());
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(2);
  });

  it("never chains into apply", async () => {
    const api = await scoreThen({ stage: "apply", next_action: "continue", next_kind: "apply", force: false });
    expect(await screen.findByRole("button", { name: "Continue pipeline" })).toBeEnabled();
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(1);
  });

  it("does not chain when score blocked the job", async () => {
    const api = await scoreThen({ stage: "prepare", next_action: null, next_label: null, next_kind: null,
                                  blocked_reason: "Skipped by score: fit 20 below threshold" });
    expect(await screen.findByText("Skipped by score: fit 20 below threshold")).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(1);
  });

  it("does not chain when Stop after this stage is on", async () => {
    const api = await scoreThen({ stage: "prepare", next_action: "continue", next_kind: "prepare", force: false }, true);
    expect(await screen.findByRole("button", { name: "Continue pipeline" })).toBeEnabled();
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(1);
  });

  it("recovers when the run ends before the first poll and shows its stop reason", async () => {
    let current: PipelineState = { ...base, stage: "apply", next_action: "continue", next_kind: "apply" };
    const api = mockApi({
      "GET /api/jobs/j1/pipeline": () => current,
      "POST /api/jobs/j1/pipeline": () => {
        // The run failed at once (doctor): status.json unchanged, active_run_id never set.
        current = { ...current, review_reasons: ["Flag: doctor failed"] };
        return { run_id: "run-fast", kind: "apply" };
      },
      "GET /api/runs/run-fast": () => ({
        id: "run-fast", kind: "apply", trigger: "manual", status: "finished", state: "finished",
        stop_reason: "doctor", detail: "careeros doctor failed", started_at: "2026-09-27T10:00:00Z",
        ended_at: "2026-09-27T10:00:01Z", attempts: [], budget: {}, counters: {},
      }),
    });
    renderWithProviders(<PipelineCard jobId="j1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Continue pipeline" }));
    expect(await screen.findByText(/Run run-fast ended: doctor — careeros doctor failed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue pipeline" })).toBeEnabled();
    expect(screen.getByText("Flag: doctor failed")).toBeInTheDocument();
    expect(api.callsTo("GET /api/runs/run-fast").length).toBeGreaterThan(0);
  });

  it("streams the returned run even before the pipeline reports it as active", async () => {
    const api = setup({ stage: "apply", next_action: "continue", next_kind: "apply" }, {
      "POST /api/jobs/j1/pipeline": () => ({ run_id: "run-late", kind: "apply" }),
      "GET /api/runs/run-late": () => ({ status: 404, body: { detail: "no run 'run-late'" } }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Continue pipeline" }));
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    expect(FakeEventSource.last.url).toBe("/api/runs/run-late/stream");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(1);
  });

  it("shows a queued-in-batch job as blocked without Cancel", async () => {
    setup({ stage: "prepare", next_action: null, next_label: null, next_kind: null,
            blocked_reason: "Queued in batch run 20260927-090000-prepare-11aa",
            queued_in_run: "20260927-090000-prepare-11aa" });
    expect(await screen.findByText("Queued in batch run 20260927-090000-prepare-11aa")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue pipeline" })).toBeDisabled();
  });

  it("shows the server's refusal as a toast", async () => {
    setup({ next_action: "continue", next_kind: "apply" }, {
      "POST /api/jobs/j1/pipeline": { status: 409, body: { detail: "Another run is already running (prepare, pid 4)." } },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Continue pipeline" }));
    expect(await screen.findByText("Another run is already running (prepare, pid 4).")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue pipeline" })).toBeEnabled();
  });
});
