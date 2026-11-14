import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, type Call } from "../../test/apiMock";
import { renderApp } from "../../test/renderApp";
import { META, TABS_REPLY, job } from "./fixtures";

const ROWS = [
  job({ job_id: "a1", company: "Acme", status: "applied" }),
  job({ job_id: "b2", company: "Borealis", status: "interview" }),
];
const FACETS = {
  field: "status",
  values: [
    { value: "applied", count: 2 },
    { value: "interview", count: 1 },
    { value: "rejected", count: 1 },
    { value: "withdrawn", count: 1 },
    { value: "ghosted", count: 1 },
  ],
};

function setup(path: string, rows = ROWS, extra: Record<string, unknown> = {}) {
  const api = mockApi({
    "GET /api/status": {},
    "GET /api/meta": META,
    "GET /api/jobs": () => ({ items: rows, total: rows.length, next_cursor: null }),
    "GET /api/jobs/tabs": TABS_REPLY,
    "GET /api/jobs/facets": FACETS,
    "GET /api/ui-state": { tour_done: true },
    "PUT /api/ui-state": (c: Call) => c.body,
    ...extra,
  });
  return { api, ...renderApp(path) };
}

beforeEach(() => vi.stubGlobal("scrollTo", vi.fn()));
afterEach(() => vi.unstubAllGlobals());

const wide = (on: boolean) =>
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: on, media: q, addEventListener() {}, removeEventListener() {} }));

describe("Applied stage sub-tabs", () => {
  it("shows Applied · Screening · Interview · Offer · Closed with counts, Closed = rejected + withdrawn, not ghosted", async () => {
    setup("/jobs?tab=applied");
    const stages = await screen.findByRole("tablist", { name: "Stage" });
    await waitFor(() => expect(within(stages).getByRole("tab", { name: "Closed (2)" })).toBeInTheDocument());
    expect(within(stages).getByRole("tab", { name: "All (6)" })).toBeInTheDocument();
    expect(within(stages).getByRole("tab", { name: "Interview (1)" })).toBeInTheDocument();
    expect(within(stages).getByRole("tab", { name: "Screening (0)" })).toBeInTheDocument();
  });

  it("is absent on other tabs; choosing a stage writes ?stage= and filters by its statuses", async () => {
    const user = userEvent.setup();
    const { api, router } = setup("/jobs?tab=applied");
    const stages = await screen.findByRole("tablist", { name: "Stage" });
    await user.click(within(stages).getByRole("tab", { name: /^Closed/ }));
    expect(router.state.location.search).toContain("stage=closed");
    await waitFor(() => {
      const last = api.callsTo("GET /api/jobs").at(-1)!;
      expect(last.search.getAll("status").sort()).toEqual(["rejected", "withdrawn"]);
    });
  });

  it("is not shown on Saved", async () => {
    setup("/jobs?tab=saved");
    await screen.findByRole("tab", { name: /^Saved/ });
    expect(screen.queryByRole("tablist", { name: "Stage" })).not.toBeInTheDocument();
  });
});

describe("Needs you", () => {
  it("flags prepared jobs and jobs with an open Action Item, not plain saved ones", async () => {
    setup("/jobs?tab=saved", [
      job({ job_id: "p1", company: "Prep", status: "prepared" }),
      job({ job_id: "n1", company: "Action", status: "queued", next_action: "Confirm salary" }),
      job({ job_id: "q1", company: "Plain", status: "queued" }),
    ]);
    expect((await screen.findByRole("link", { name: /Prep/ })).closest("li")).toHaveAttribute("data-needs-you", "true");
    expect(screen.getByRole("link", { name: /Action/ }).closest("li")).toHaveAttribute("data-needs-you", "true");
    expect(screen.getByRole("link", { name: /Plain/ }).closest("li")).not.toHaveAttribute("data-needs-you");
  });
});

describe("review fixes", () => {
  it("keeps top-level tab counts and Export on the chosen stage", async () => {
    const user = userEvent.setup();
    const { api } = setup("/jobs?tab=applied&stage=closed", ROWS, { "POST /api/jobs/export": { name: "x.xlsx" } });
    await screen.findByRole("tablist", { name: "Stage" });
    await waitFor(() => expect(api.callsTo("GET /api/jobs/tabs").length).toBeGreaterThan(0));
    for (const c of api.callsTo("GET /api/jobs/tabs")) expect(c.search.getAll("status")).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Export xlsx" }));
    await waitFor(() => expect(api.callsTo("POST /api/jobs/export")).toHaveLength(1));
    expect((api.callsTo("POST /api/jobs/export")[0]!.body as Record<string, unknown>).status).toEqual(["rejected", "withdrawn"]);
  });

  it("drops the selection when the tab changes", async () => {
    const user = userEvent.setup();
    const { router } = setup("/jobs?tab=saved&sel=a1");
    await screen.findByText("1 selected");
    await user.click(screen.getByRole("tab", { name: /^Applied/ }));
    await waitFor(() => expect(router.state.location.search).toContain("tab=applied"));
    expect(router.state.location.search).not.toContain("sel=");
  });
});
