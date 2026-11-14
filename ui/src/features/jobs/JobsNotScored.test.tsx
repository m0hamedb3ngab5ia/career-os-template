import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
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

function setup(rows = ROWS, extra: Record<string, unknown> = {}, path = "/jobs?tab=notscored") {
  const api = mockApi({
    "GET /api/status": {}, "GET /api/meta": META,
    "GET /api/jobs": () => ({ items: rows, total: rows.length, next_cursor: null }),
    "GET /api/jobs/tabs": TABS,
    "GET /api/ui-state": { tour_done: true },
    "POST /api/jobs/score": { run_id: "r-score-1", kind: "score" },
    "GET /api/settings/runs": { values: { "scoring.min_prescore": 20, "scoring.stale_days": 21 } },
    ...extra,
  });
  return { api, ...renderApp(path) };
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
    expect(a).not.toHaveTextContent(/Fit \d/);
    expect(screen.getByRole("link", { name: /Sample Labs/ }).closest("li")).toHaveTextContent("Older posting");
    expect(screen.getByRole("link", { name: /Demo Inc/ }).closest("li")).toHaveTextContent("Below cutoff");
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

  it("empty state with column filters says filters hide jobs, not that every job is scored", async () => {
    setup([], {}, "/jobs?tab=notscored&f.company=Acme");
    expect(await screen.findByText("No jobs match these filters")).toBeInTheDocument();
    expect(screen.queryByText("Every job is scored")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("Every job is scored")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    setup();
    await screen.findByRole("link", { name: /Example Corp/ });
    expect(await axeViolations(document.body)).toEqual([]);
  });
});
