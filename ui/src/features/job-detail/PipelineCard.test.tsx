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
  note: null,
  auto_submit: false,
  review_reasons: [],
  active_run_id: null,
  queued_in_run: null,
  failures: null,
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
      review_reasons: [
        { code: "qa_warning", text: "A document check left a warning", detail: "long letter" },
        { code: "action_review", text: "Review and submit the application", detail: "Review and submit" },
      ],
    });
    expect(await screen.findByRole("button", { name: "Approve & continue" })).toHaveAttribute(
      "title",
      "Approves the current documents and lets the pipeline continue to the next step.",
    );
    expect(screen.getByText("Needs your review: 2 things need attention.")).toBeInTheDocument();
    const needs = screen.getByRole("list", { name: "Needs you" });
    expect(within(needs).getByText("Review and submit the application")).toBeInTheDocument();
    expect(within(needs).queryByText(/long letter/)).not.toBeInTheDocument(); // codes/details only in Details
    const details = screen.getByText("Details").closest("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(within(details).getByText(/long letter/)).toBeInTheDocument();
    const steps = within(screen.getByRole("list", { name: "Pipeline stages" })).getAllByRole("listitem");
    expect(steps.map((s) => s.getAttribute("data-state"))).toEqual(["done", "done", "done", "current", "upcoming"]);
  });

  it("keeps the Approve & continue tooltip for a Tier B job even though auto_submit is off (STAGE_NOTE set)", async () => {
    // Regression: a Tier B/C needs_review job with qa_pass keeps its "Approve & continue" label (it approves the
    // docs, it does not stage/submit a form) even though STAGE_NOTE is shown under the button; the tooltip must
    // not fall back to the stageReview wording just because `note` is set.
    setup({ stage: "review", next_action: "approve_continue", next_label: "Approve & continue", next_kind: "apply",
            note: "auto_submit is off: the run fills and stages the form; you review and submit." });
    const btn = await screen.findByRole("button", { name: "Approve & continue" });
    expect(btn.getAttribute("title")).toBe(
      "Approves the current documents and lets the pipeline continue to the next step.",
    );
  });

  it("offers the assisted apply for a Tier A job with its note under the button", async () => {
    setup({ stage: "review", next_action: "approve_continue", next_label: "Prepare & stage for review",
            next_kind: "apply", note: "Tier A: the run fills and stages the form; you review and submit." });
    const btn = await screen.findByRole("button", { name: "Prepare & stage for review" });
    expect(btn).toBeEnabled();
    expect(btn.getAttribute("title")).toContain("stops before Submit");
    expect(screen.getByText("Tier A: the run fills and stages the form; you review and submit.")).toBeInTheDocument();
  });

  it("disables the button with the blocked reason as its title", async () => {
    setup({ stage: "apply", next_action: null, next_label: null, next_kind: null,
            blocked_reason: "A run is working on this job" });
    const btn = await screen.findByRole("button", { name: "Continue pipeline" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", "A run is working on this job");
    expect(screen.getByText("A run is working on this job")).toBeInTheDocument();
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
    act(() => FakeEventSource.last.dispatch("end", { state: "finished", stop_reason: "completed", counters: { ok: 1, failed: 0 } }));
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

  it("does not chain a score run into apply", async () => {
    const api = await scoreThen({ stage: "apply", next_action: "continue", next_kind: "apply", force: false });
    expect(await screen.findByRole("button", { name: "Continue pipeline" })).toBeEnabled();
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(1);
  });

  /** Continue on a scored job; the first POST prepares it, the stream end flips the server state to `after`. */
  async function prepareThen(after: Partial<PipelineState>, stopAfter = false, stopReason = "completed",
                             counters: Record<string, number> = { ok: 1, failed: 0 }) {
    let current: PipelineState = { ...base, ...after, active_run_id: null, stage: "prepare", next_action: "continue",
                                   next_label: "Continue pipeline", next_kind: "prepare", note: null };
    let n = 0;
    const api = mockApi({
      "GET /api/jobs/j1/pipeline": () => current,
      "POST /api/jobs/j1/pipeline": () => {
        n += 1;
        const kind = n === 1 ? "prepare" : "apply";
        current = { ...current, active_run_id: `run-${n}-${kind}` };
        return { run_id: `run-${n}-${kind}`, kind };
      },
    });
    renderWithProviders(<PipelineCard jobId="j1" />);
    if (stopAfter) await userEvent.click(await screen.findByRole("checkbox", { name: "Stop after this stage" }));
    await userEvent.click(await screen.findByRole("button", { name: "Continue pipeline" }));
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    expect(FakeEventSource.last.url).toBe("/api/runs/run-1-prepare/stream");
    current = { ...base, ...after, active_run_id: null };
    act(() => FakeEventSource.last.dispatch("end", { state: "finished", stop_reason: stopReason, counters }));
    return api;
  }

  it("does not chain a failed prepare run into apply even if it left runnable files", async () => {
    const api = await prepareThen({ stage: "apply", next_action: "continue", next_kind: "apply", auto_submit: false },
                                  false, "usage_limit");
    expect(await screen.findByRole("button", { name: "Continue pipeline" })).toBeEnabled();
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(1);
  });

  it("does not chain a completed prepare run into apply when its job failed", async () => {
    const api = await prepareThen({ stage: "apply", next_action: "continue", next_kind: "apply", auto_submit: false },
                                  false, "completed", { attempted: 1, ok: 0, failed: 1 });
    expect(await screen.findByRole("button", { name: "Continue pipeline" })).toBeEnabled();
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(1);
  });

  it("never chains past the review gate: Approve & continue stays with the human", async () => {
    const api = await prepareThen({ stage: "review", next_action: "approve_continue", next_kind: "apply",
                                    next_label: "Prepare & stage for review", auto_submit: false,
                                    review_reasons: [{ code: "prepare_action", text: "Document preparation left a step for you",
                                                      detail: "tier_a_review: review resume + cover letter" }] });
    expect(await screen.findByRole("button", { name: "Prepare & stage for review" })).toBeEnabled();
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(1);
  });

  it("chains a prepared job into the staged apply while auto_submit is off", async () => {
    const api = await prepareThen({ stage: "apply", next_action: "continue", next_kind: "apply",
                                    next_label: "Prepare & stage for review", auto_submit: false });
    await waitFor(() => expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(2));
    expect(api.callsTo("POST /api/jobs/j1/pipeline")[1]?.body).toEqual({ action: "continue" });
    expect(await screen.findByText(/Prepared — filling & staging for review…/)).toBeInTheDocument();
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(2));
    expect(FakeEventSource.last.url).toBe("/api/runs/run-2-apply/stream");
  });

  it("never chains into apply while auto_submit is on", async () => {
    const api = await prepareThen({ stage: "apply", next_action: "continue", next_kind: "apply", auto_submit: true });
    expect(await screen.findByRole("button", { name: "Continue pipeline" })).toBeEnabled();
    expect(api.callsTo("POST /api/jobs/j1/pipeline").length).toBe(1);
  });

  it("does not chain prepare into apply when Stop after this stage is on", async () => {
    const api = await prepareThen({ stage: "apply", next_action: "continue", next_kind: "apply", auto_submit: false }, true);
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
        current = { ...current, review_reasons: [{ code: "prepare_flag", text: "Document preparation flagged something to check", detail: "doctor failed" }] };
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
    expect(screen.getByText("Document preparation flagged something to check")).toBeInTheDocument();
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

  it("disables the button for a job out of retries and resets its failures", async () => {
    const failures = { kind: "apply", count: 2, max_attempts: 2, last_outcome: "invalid_result", last_detail: "bad",
      last_run: "r2", excluded: true };
    const reason = "Failed 2 times (last: invalid_result): runs skip this job until you reset its failures";
    const api = setup({ next_kind: "apply", blocked_reason: reason, failures }, {
      "POST /api/jobs/j1/failures/reset": { job_id: "j1", cleared: ["apply"], resolved: ["A1"] },
    });
    expect(await screen.findByRole("button", { name: "Continue pipeline" })).toBeDisabled();
    expect(screen.getByText(reason)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reset failures" }));
    await waitFor(() => expect(api.callsTo("POST /api/jobs/j1/failures/reset").length).toBe(1));
  });

  it("shows the run's own refusal when it never wrote a run record", async () => {
    setup({ next_action: "continue", next_kind: "apply" }, {
      "POST /api/jobs/j1/pipeline": { run_id: "20260927-100000-apply-ab12", kind: "apply" },
      "GET /api/runs/20260927-100000-apply-ab12": { status: 404, body: {
        detail: "Run 20260927-100000-apply-ab12 did not start: run apply: j1: status skipped" } },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Continue pipeline" }));
    expect(await screen.findByText(/did not start: run apply: j1: status skipped/)).toBeInTheDocument();
  });

  it("puts Fill application beside the next-step button; a failed fill shows the error and Retry", async () => {
    const api = setup({ stage: "review", next_action: "continue", next_label: "Continue pipeline", next_kind: "apply" }, {
      "GET /api/jobs/j1/application": { tab: "none", submitted: false, can_fill: true,
        fill_error: "playwright is not installed", fill_log: "Traceback\nplaywright is not installed" },
      "POST /api/jobs/j1/application/open": { status: 409, body: { detail: "Playwright's Chromium is missing" } },
    });
    const next = await screen.findByRole("button", { name: "Continue pipeline" });
    const retry = await screen.findByRole("button", { name: "Retry fill" });
    expect(retry.parentElement).toBe(next.parentElement);
    expect(screen.getByText("Fill failed")).toHaveAttribute("data-tone", "red");
    expect(screen.getByText(/Filling the application failed: playwright is not installed/)).toBeInTheDocument();
    expect(screen.getByText("Fill output")).toBeInTheDocument();
    await userEvent.click(retry);
    expect(await screen.findByText("Playwright's Chromium is missing")).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/j1/application/open")).toHaveLength(1);
  });

  it("hides the old error while a retry fills, then confirms the filled form", async () => {
    let tab: object = { tab: "none", submitted: false, can_fill: true, fill_error: "- fonts loaded" };
    setup({ stage: "review", next_action: null, next_label: null, next_kind: null }, {
      "GET /api/jobs/j1/application": () => tab,
      "POST /api/jobs/j1/application/open": () => {
        tab = { tab: "none", submitted: false, can_fill: true, filling: true };
        return { action: "filling" };
      },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Retry fill" }));
    expect(await screen.findByText("Filling…")).toHaveAttribute("data-tone", "blue");
    expect(screen.queryByText(/Filling the application failed/)).not.toBeInTheDocument();
    tab = { tab: "open", submitted: false, can_fill: true, fields_left: ["Race"] };
    expect(await screen.findByText(/Form filled, 1 field left for you/, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText("Tab open")).toHaveAttribute("data-tone", "green");
  }, 10_000);

  it("shows Connect Chrome + Retry when your Chrome is not connected, and retries the same request", async () => {
    const api = setup({ stage: "apply", next_action: null, next_label: null, next_kind: null }, {
      "GET /api/jobs/j1/application": { tab: "needs_refill", submitted: false, can_fill: true },
      "POST /api/jobs/j1/application/open": { status: 409, body: { detail: "Chrome not connected on http://127.0.0.1:9222: open Chrome, then retry" } },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Refill application" }));
    expect(await screen.findByText("Connect Chrome extension, then retry")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(api.callsTo("POST /api/jobs/j1/application/open")).toHaveLength(2);
  });

  it("says Connect Chrome instead of the raw error when the fill could not attach to the browser", async () => {
    setup({ stage: "apply", next_action: null, next_label: null, next_kind: null }, {
      "GET /api/jobs/j1/application": { tab: "none", submitted: false, can_fill: true,
        fill_error: "playwright._impl._errors.Error: BrowserType.connect_over_cdp: connect ECONNREFUSED 127.0.0.1:9222" },
    });
    expect(await screen.findByText("Connect Chrome extension, then retry")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry fill" })).toBeEnabled();
  });

  it("offers Open application with a Tab open chip for a live filled tab", async () => {
    setup({ stage: "apply", next_action: null, next_label: null, next_kind: null }, {
      "GET /api/jobs/j1/application": { tab: "open", submitted: false, can_fill: true },
    });
    expect(await screen.findByRole("button", { name: "Open application" })).toBeEnabled();
    expect(screen.getByText("Tab open")).toHaveAttribute("data-tone", "green");
  });

  it("keeps Refill beside a live tab and says how many fields are left", async () => {
    const api = setup({ stage: "apply", next_action: null, next_label: null, next_kind: null }, {
      "GET /api/jobs/j1/application": { tab: "open", submitted: false, can_fill: true, fields_left: ["Q1", "Q2"] },
      "POST /api/jobs/j1/application/open": { action: "filling" },
    });
    expect(await screen.findByText("2 fields left for you")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Refill" }));
    expect(api.callsTo("POST /api/jobs/j1/application/open")[0]?.body).toEqual({ refill: true });
  });
});
