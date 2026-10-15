import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, type Call } from "../../test/apiMock";
import { axeViolations } from "../../test/axe";
import { renderApp } from "../../test/renderApp";
import { META, job } from "./fixtures";

const NOW = Date.now();
const daysAgo = (n: number) => new Date(NOW - n * 86_400_000).toISOString();
const ROWS = [
  job({ job_id: "q1", company: "Example Corp", title: "Platform Engineer", fit: null, status: null, selected: 0, prescore: 81, found_at: daysAgo(2) }),
  job({ job_id: "o2", company: "Sample Labs", title: "Data Engineer", fit: null, status: null, selected: 0, prescore: 74, found_at: daysAgo(40) }),
  job({ job_id: "l3", company: "Demo Inc", title: "Sales Engineer", fit: null, status: null, selected: 0, prescore: 18, found_at: daysAgo(1) }),
];
const TABS = { tabs: [
  { key: "recommended", label: "Recommended", count: 42 }, { key: "notscored", label: "Not scored", count: 3 },
  { key: "saved", label: "Saved", count: 3 }, { key: "applied", label: "Applied", count: 2 }] };

function setup(rows = ROWS, extra: Record<string, unknown> = {}) {
  const api = mockApi({
    "GET /api/status": {}, "GET /api/meta": META,
    "GET /api/jobs": () => ({ items: rows, total: rows.length, next_cursor: null }),
    "GET /api/jobs/tabs": TABS,
    "GET /api/ui-state": { tour_done: true },
    "POST /api/jobs/score": { run_id: "r-score-1", kind: "score" },
    "GET /api/settings/runs": { values: { "scoring.min_prescore": 20, "scoring.stale_days": 21 } },
    ...extra,
  });
  return { api, ...renderApp("/jobs?tab=notscored") };
}

beforeEach(() => vi.stubGlobal("scrollTo", vi.fn()));
afterEach(() => vi.unstubAllGlobals());

describe("Jobs › Not scored (REQ-136, E2E-017-05)", () => {
  it("shows the tab with its count and cards: quick match, reason, Score now", async () => {
    const { api } = setup();
    expect(await screen.findByRole("tab", { name: "Not scored (3)" })).toHaveAttribute("aria-selected", "true");
    const req = api.callsTo("GET /api/jobs")[0]!;
    expect(req.search.get("tab")).toBe("notscored");
    expect(req.search.get("sort")).toBe("-prescore");
    const a = (await screen.findByRole("link", { name: /Example Corp/ })).closest("li")!;
    expect(a).toHaveTextContent("Quick match 81");
    expect(a).toHaveTextContent("Queued");
    expect(within(a).getByRole("button", { name: "Score now" })).toBeInTheDocument();
    expect(a).not.toHaveTextContent(/Fit \d/);
    expect(screen.getByRole("link", { name: /Sample Labs/ }).closest("li")).toHaveTextContent("Older posting");
    expect(screen.getByRole("link", { name: /Demo Inc/ }).closest("li")).toHaveTextContent("Below cutoff");
  });

  it("Score now on one card posts just that job and does not tick it", async () => {
    const user = userEvent.setup();
    const { api } = setup();
    const card = (await screen.findByRole("link", { name: /Example Corp/ })).closest("li")!;
    await user.click(within(card).getByRole("button", { name: "Score now" }));
    await waitFor(() => expect(api.callsTo("POST /api/jobs/score")).toHaveLength(1));
    expect(api.callsTo("POST /api/jobs/score")[0]!.body).toEqual({ job_ids: ["q1"] });
    expect(api.callsTo("POST /api/jobs/select")).toHaveLength(0);
    expect(await within(card).findByRole("button", { name: "Scoring…" })).toBeDisabled();
  });

  it("Score selected posts every ticked job", async () => {
    const user = userEvent.setup();
    const { api } = setup();
    await screen.findByRole("link", { name: /Example Corp/ });
    await user.click(screen.getByRole("checkbox", { name: "Select Example Corp" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Demo Inc" }));
    await user.click(screen.getByRole("button", { name: "Score selected" }));
    await waitFor(() => expect(api.callsTo("POST /api/jobs/score")).toHaveLength(1));
    expect(api.callsTo("POST /api/jobs/score")[0]!.body).toEqual({ job_ids: ["q1", "l3"] });
  });

  it("shows a failure with Retry and keeps Score now available", async () => {
    const user = userEvent.setup();
    let n = 0;
    const { api } = setup(ROWS, {
      "POST /api/jobs/score": (_c: Call) => (n++ === 0 ? { status: 409, body: { detail: "A run is already active" } } : { run_id: "r2", kind: "score" }),
    });
    const card = (await screen.findByRole("link", { name: /Example Corp/ })).closest("li")!;
    await user.click(within(card).getByRole("button", { name: "Score now" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Scoring failed");
    expect(alert).toHaveTextContent("A run is already active");
    expect(within(card).getByRole("button", { name: "Score now" })).toBeEnabled();
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.callsTo("POST /api/jobs/score")).toHaveLength(2));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("a score run that fails after it starts puts the card back to Score now with the error and Retry", async () => {
    const run = (state: string) => ({ id: "r-score-1", kind: "score", state, status: state, stop_reason: state === "failed" ? "error" : null,
      detail: state === "failed" ? "RuntimeError: claude crashed" : "", log: "", attempts: [], started_at: daysAgo(0), ended_at: null, trigger: "ui" });
    let state = "running";
    const { api } = setup(ROWS, { "GET /api/runs/r-score-1": () => run(state) });
    const user = userEvent.setup();
    const card = (await screen.findByRole("link", { name: /Example Corp/ })).closest("li")!;
    await user.click(within(card).getByRole("button", { name: "Score now" }));
    expect(await within(card).findByRole("button", { name: "Scoring…" })).toBeDisabled();
    await waitFor(() => expect(api.callsTo("GET /api/runs/r-score-1").length).toBeGreaterThan(0));
    const listCalls = api.callsTo("GET /api/jobs").length;
    state = "failed";
    expect(await within(card).findByRole("button", { name: "Score now" }, { timeout: 3000 })).toBeEnabled();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("RuntimeError: claude crashed");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeEnabled();
    await waitFor(() => expect(api.callsTo("GET /api/jobs").length).toBeGreaterThan(listCalls));
  });

  it("reasons follow scoring.min_prescore / stale_days from Settings (TASK-039 config)", async () => {
    setup(ROWS, { "GET /api/settings/runs": { values: { "scoring.min_prescore": 10, "scoring.stale_days": 60 } } });
    await screen.findByRole("link", { name: /Example Corp/ });
    await waitFor(() => expect(screen.getAllByText("Queued")).toHaveLength(3));
    expect(screen.queryByText(/Below cutoff|Older posting/)).not.toBeInTheDocument();
  });

  it("shows the configured cutoff in the reason", async () => {
    setup(ROWS, { "GET /api/settings/runs": { values: { "scoring.min_prescore": 50, "scoring.stale_days": 21 } } });
    const card = (await screen.findByRole("link", { name: /Demo Inc/ })).closest("li")!;
    await waitFor(() => expect(card).toHaveTextContent("Below cutoff (50)"));
  });

  it("hides the List / Table view switch and Columns (one card layout here)", async () => {
    setup();
    await screen.findByRole("link", { name: /Example Corp/ });
    expect(screen.queryByRole("radiogroup", { name: "View" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Columns/ })).not.toBeInTheDocument();
  });

  it("empty state says every job is scored", async () => {
    setup([]);
    expect(await screen.findByText("Every job is scored")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    setup();
    await screen.findByRole("link", { name: /Example Corp/ });
    expect(await axeViolations(document.body)).toEqual([]);
  });
});
