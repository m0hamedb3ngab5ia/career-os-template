import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, type Call } from "../../test/apiMock";
import { renderApp } from "../../test/renderApp";
import { detail } from "../job-detail/fixtures";
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
    "GET /api/jobs/a1": detail({ posting: { ...detail().posting, company: "Acme" } }),
    "GET /api/jobs/b2": detail({ posting: { ...detail().posting, company: "Borealis" } }),
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

describe("List master-detail", () => {
  it("opens a job at /jobs/:id keeping tab/view, with the detail beside the list", async () => {
    wide(true);
    const user = userEvent.setup();
    const { router } = setup("/jobs?tab=applied&view=list");
    await user.click(await screen.findByRole("link", { name: /Borealis/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs/b2"));
    expect(router.state.location.search).toContain("tab=applied");
    expect(await screen.findByRole("heading", { name: "Borealis", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Acme/ })).toBeInTheDocument();
    await router.navigate(-1);
    // Wide List with no job open falls back to the first job (a1) rather than an empty pane.
    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs/a1"));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Borealis", level: 2 })).not.toBeInTheDocument());
  });

  it("is a full page under 900px", async () => {
    wide(false);
    setup("/jobs/a1?tab=applied");
    expect(await screen.findByRole("heading", { name: "Acme", level: 1 }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Borealis/ })).not.toBeInTheDocument();
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

describe("Board drag to Applied", () => {
  it("is refused without calling /status: applying goes through /submitted", async () => {
    const { api } = setup("/jobs?tab=applied&view=board", ROWS, {
      "POST /api/jobs/b2/status": { job_id: "b2", status: "applied" },
    });
    const applied = await screen.findByRole("region", { name: "Applied" });
    const card = screen.getByText("Borealis").closest("[draggable]")!;
    const dataTransfer = { setData: vi.fn(), getData: () => "b2", effectAllowed: "" };
    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.drop(applied, { dataTransfer });
    expect(await screen.findByText(/becomes Applied when its application is submitted/)).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/b2/status")).toHaveLength(0);
    expect(within(screen.getByRole("region", { name: "Interview" })).getByText("Borealis")).toBeInTheDocument();
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

  it("selects the first job on a wide List view with none open, without adding history", async () => {
    wide(true);
    const { router } = setup("/jobs?tab=applied&view=list");
    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs/a1"));
    expect(router.state.location.search).toContain("tab=applied");
    await router.navigate(-1);
    expect(router.state.location.pathname).not.toBe("/jobs");
  });
});
