import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, type Call } from "../../test/apiMock";
import { axeViolations } from "../../test/axe";
import { renderApp } from "../../test/renderApp";
import { formatDate } from "../../lib/format";
import { JOBS, META, TABS_REPLY } from "./fixtures";

function page(call: Call) {
  const cursor = call.search.get("cursor");
  // page_size 2 in META: first page = 2 rows, then the rest
  if (!cursor) return { items: JOBS.slice(0, 2), total: 3, next_cursor: "2" };
  return { items: JOBS.slice(2), total: 3, next_cursor: null };
}

function setup(path = "/jobs", extra: Record<string, unknown> = {}) {
  const api = mockApi({
    "GET /api/status": {},
    "GET /api/meta": META,
    "GET /api/jobs": page,
    "GET /api/jobs/tabs": TABS_REPLY,
    ...extra,
  });
  const app = renderApp(path);
  return { api, ...app };
}

beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Jobs screen", () => {
  it("shows the header, tabs with counts and the first page of the live table", async () => {
    const { api } = setup();
    expect(await screen.findByRole("heading", { level: 1, name: "Jobs" }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/same columns as the Jobs tab in JobTracker.xlsx/)).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Tracked jobs, sorted by fit, highest first" });
    expect(within(table).getByRole("rowheader", { name: "Northwind Labs" })).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "Northwind Labs" })).toHaveAttribute("href", "/jobs/nw01");
    expect(await screen.findByRole("tab", { name: "Active (59)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "All (736)" })).toBeInTheDocument();
    const req = api.callsTo("GET /api/jobs")[0]!;
    expect(Object.fromEntries(req.search)).toEqual({ tab: "active", sort: "-fit", limit: "2" });
    expect(screen.getByText(/Showing 2 of 3 active jobs/)).toBeInTheDocument();
  });

  it("renders every mockup column with chips, dates and spoken dashes for empty cells", async () => {
    setup();
    const table = await screen.findByRole("table");
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent?.replace(/,.*$/, ""));
    expect(headers).toEqual(["Select all shown jobs", "Company", "Role", "Location", "Tier", "Fit", "Status", "Safety",
      "QA", "ATS", "Found", "Applied", "Next action"]);
    const nw = within(table).getByRole("rowheader", { name: "Northwind Labs" }).closest("tr")!;
    expect(within(nw).getByRole("cell", { name: "Software Engineer" })).toBeInTheDocument();
    expect(within(nw).getByRole("cell", { name: "Springfield" })).toBeInTheDocument();
    const globex = within(table).getByRole("rowheader", { name: "Globex Analytics" }).closest("tr")!;
    expect(within(globex).getByRole("cell", { name: "Remote" })).toBeInTheDocument();
    expect(within(nw).getByText("Needs review")).toHaveAttribute("data-tone", "orange");
    expect(within(nw).getByText("Pass")).toHaveAttribute("data-tone", "green");
    expect(within(nw).getByText("Not applied")).toHaveClass("sr-only");
    expect(within(nw).getByText("You submit (Tier A)")).toBeInTheDocument();
    expect(within(nw).getByText(formatDate("2026-09-20T09:00:00")!)).toBeInTheDocument();
    const gx = within(table).getByRole("rowheader", { name: "Globex Analytics" }).closest("tr")!;
    expect(within(gx).getByText("No QA score")).toHaveClass("sr-only");
    expect(within(gx).getByText(formatDate("2026-09-22T10:00:00")!)).toBeInTheDocument();
    expect(within(gx).getByText("Lever")).toBeInTheDocument();
  });

  it("unknown status and safety codes fall back to gray chips", async () => {
    setup();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Show more" }));
    const row = (await screen.findByRole("rowheader", { name: "Initech" })).closest("tr")!;
    expect(within(row).getByText("On hold")).toHaveAttribute("data-tone", "gray");
    expect(within(row).getByText("Mystery")).toHaveAttribute("data-tone", "gray");
    expect(within(row).getByText("No tier")).toBeInTheDocument();
  });

  it("Show more loads the next page by cursor and hides once everything is loaded", async () => {
    const { api } = setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Show more" }));
    expect(await screen.findByText(/Showing 3 of 3 active jobs/)).toBeInTheDocument();
    expect(api.callsTo("GET /api/jobs")[1]!.search.get("cursor")).toBe("2");
    expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  });

  it("tabs are a roving tablist: arrow keys switch the filter and the URL", async () => {
    const { api, router } = setup();
    const user = userEvent.setup();
    const active = await screen.findByRole("tab", { name: "Active (59)" });
    expect(screen.getByRole("tab", { name: "Needs review (6)" })).toHaveAttribute("tabindex", "-1");
    active.focus();
    await user.keyboard("{ArrowRight}");
    const review = screen.getByRole("tab", { name: "Needs review (6)" });
    expect(review).toHaveFocus();
    expect(review).toHaveAttribute("aria-selected", "true");
    expect(router.state.location.search).toBe("?tab=review");
    await waitFor(() => expect(api.callsTo("GET /api/jobs").some((c) => c.search.get("tab") === "review")).toBe(true));
  });

  it("clicking a sortable header sorts, sets aria-sort and updates the caption and URL", async () => {
    const { api, router } = setup();
    const user = userEvent.setup();
    const table = await screen.findByRole("table");
    const fit = within(table).getByRole("columnheader", { name: /Fit/ });
    expect(fit).toHaveAttribute("aria-sort", "descending");
    expect(within(table).getByRole("columnheader", { name: "Safety" })).not.toHaveAttribute("aria-sort");
    await user.click(within(table).getByRole("button", { name: "Company" }));
    expect(router.state.location.search).toBe("?sort=company");
    expect(within(table).getByRole("columnheader", { name: /Company/ })).toHaveAttribute("aria-sort", "ascending");
    expect(await screen.findByRole("table", { name: "Tracked jobs, sorted by company, A to Z" })).toBeInTheDocument();
    await waitFor(() => expect(api.callsTo("GET /api/jobs").at(-1)!.search.get("sort")).toBe("company"));
    await user.click(within(table).getByRole("button", { name: /Company/ }));
    expect(router.state.location.search).toBe("?sort=-company");
  });

  it("reads tab, search, sort and hidden columns from the URL", async () => {
    const { api } = setup("/jobs?tab=tier_a&q=globex&sort=-found_at&cols=ats,qa");
    const table = await screen.findByRole("table", { name: "Tracked jobs, sorted by found date, newest first" });
    expect(within(table).queryByRole("columnheader", { name: "ATS" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "QA" })).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search jobs" })).toHaveValue("globex");
    const req = api.callsTo("GET /api/jobs")[0]!;
    expect(req.search.get("tab")).toBe("tier_a");
    expect(req.search.get("q")).toBe("globex");
    expect(api.callsTo("GET /api/jobs/tabs")[0]!.search.get("q")).toBe("globex");
  });

  it("the search field commits to the URL after a pause", async () => {
    const { router, api } = setup();
    const user = userEvent.setup();
    await user.type(await screen.findByRole("searchbox", { name: "Search jobs" }), "north");
    await waitFor(() => expect(router.state.location.search).toBe("?q=north"));
    await waitFor(() => expect(api.callsTo("GET /api/jobs").at(-1)!.search.get("q")).toBe("north"));
  });

  it("the location filter has its own column sort and commits to the URL and the request", async () => {
    const { router, api } = setup();
    const user = userEvent.setup();
    const table = await screen.findByRole("table");
    await user.click(within(table).getByRole("button", { name: "Location" }));
    expect(router.state.location.search).toBe("?sort=location");
    expect(await screen.findByRole("table", { name: "Tracked jobs, sorted by location, A to Z" })).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Filter by location" }), "remote");
    await waitFor(() => expect(router.state.location.search).toBe("?sort=location&loc=remote"));
    await waitFor(() => expect(api.callsTo("GET /api/jobs").at(-1)!.search.get("location")).toBe("remote"));
    await waitFor(() => expect(api.callsTo("GET /api/jobs/tabs").at(-1)!.search.get("location")).toBe("remote"));
    expect(api.callsTo("GET /api/jobs").at(-1)!.search.has("q")).toBe(false);
  });

  it("reads the location filter from the URL", async () => {
    const { api } = setup("/jobs?loc=springfield");
    await screen.findByRole("table");
    expect(screen.getByRole("searchbox", { name: "Filter by location" })).toHaveValue("springfield");
    expect(api.callsTo("GET /api/jobs")[0]!.search.get("location")).toBe("springfield");
  });

  it("the column chooser hides a column and keeps it in the URL", async () => {
    const { router } = setup();
    const user = userEvent.setup();
    const table = await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Columns" }));
    const ats = screen.getByRole("menuitemcheckbox", { name: "ATS" });
    expect(ats).toHaveAttribute("aria-checked", "true");
    await user.click(ats);
    expect(within(table).queryByRole("columnheader", { name: "ATS" })).not.toBeInTheDocument();
    expect(router.state.location.search).toBe("?cols=ats");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Columns" })).toHaveFocus();
  });

  it("selects rows, announces the count, selects all shown and clears", async () => {
    const { router } = setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Select Northwind Labs" }));
    const live = screen.getByText("1 selected").closest("[role=status]")!;
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(router.state.location.search).toBe("?sel=nw01");
    expect(screen.getByRole("button", { name: "Export 1 to xlsx" })).toBeInTheDocument();
    const all = screen.getByRole("checkbox", { name: "Select all shown jobs" });
    expect((all as HTMLInputElement).indeterminate).toBe(true);
    await user.click(all);
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(all).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.queryByText(/selected$/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export xlsx" })).toBeInTheDocument();
  });

  it("exports the selection by id with the visible columns and downloads the file", async () => {
    const createObjectURL = vi.fn(() => "blob:x");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { api } = setup("/jobs?sel=nw01&cols=ats", {
      "POST /api/jobs/export": () =>
        new Response("xlsx", {
          headers: { "content-disposition": 'attachment; filename="careeros-jobs-20260926.xlsx"' },
        }),
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Export 1 to xlsx" }));
    expect(await screen.findByText("Downloaded careeros-jobs-20260926.xlsx")).toBeInTheDocument();
    const req = api.callsTo("POST /api/jobs/export")[0]!;
    expect(req.headers["x-careeros"]).toBe("1");
    expect(req.body).toEqual({
      job_ids: ["nw01"],
      columns: ["job_id", "company", "title", "location", "tier", "fit", "status", "safety", "qa_score", "found_at", "applied_at",
        "next_action"],
    });
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:x");
    click.mockRestore();
  });

  it("with no selection, exports the current filter", async () => {
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:y", revokeObjectURL: () => undefined }));
    const { api } = setup("/jobs?tab=applied&q=data&sort=company", {
      "POST /api/jobs/export": () => new Response("x"),
    });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Export xlsx" }));
    await screen.findByText("Downloaded careeros-jobs.xlsx");
    expect(api.callsTo("POST /api/jobs/export")[0]!.body).toMatchObject({ tab: "applied", q: "data", sort: "company" });
  });

  it("export errors show the server's detail", async () => {
    setup("/jobs", { "POST /api/jobs/export": { status: 409, body: { detail: "Index is rebuilding" } } });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Export xlsx" }));
    expect(await screen.findByText("Index is rebuilding")).toBeInTheDocument();
  });

  it("Sync tracker posts and reports the count; a pending sync says why", async () => {
    let pending = 0;
    const { api } = setup("/jobs", {
      "POST /api/tracker/sync": () => ({ synced: 736, path: "data/JobTracker.xlsx", pending }),
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Sync tracker" }));
    expect(await screen.findByText("Synced 736 jobs")).toBeInTheDocument();
    expect(api.callsTo("POST /api/tracker/sync")[0]!.headers["x-careeros"]).toBe("1");
    pending = 3;
    await user.click(screen.getByRole("button", { name: "Sync tracker" }));
    expect(await screen.findByText(/saved to a queue; they're written on the next change, or run `careeros tracker flush` after closing Excel/)).toBeInTheDocument();
  });

  it("Open JobTracker.xlsx shows the server's reason on 409", async () => {
    setup("/jobs", {
      "POST /api/tracker/open": { status: 409, body: { detail: "No tracker yet: run Sync tracker first" } },
    });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Open JobTracker.xlsx" }));
    expect(await screen.findByText("No tracker yet: run Sync tracker first")).toBeInTheDocument();
  });

  it("empty states: nothing tracked, and no search match with a way out", async () => {
    const empty = { items: [], total: 0, next_cursor: null };
    setup("/jobs?tab=all", { "GET /api/jobs": empty });
    expect(await screen.findByRole("heading", { name: "No jobs here yet" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("no search match offers Clear search", async () => {
    const { router } = setup("/jobs?q=zzz", { "GET /api/jobs": { items: [], total: 0, next_cursor: null } });
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "No jobs match “zzz”" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(router.state.location.search).toBe("");
  });

  it("a load error says so and can retry", async () => {
    setup("/jobs", { "GET /api/jobs": { status: 503, body: { detail: "config/pipeline.yaml: broken" } } });
    expect(await screen.findByRole("heading", { name: "Couldn’t load jobs" })).toBeInTheDocument();
    expect(screen.getByText("config/pipeline.yaml: broken")).toBeInTheDocument();
  });

  it("the sidebar search is live on the Jobs screen and mirrors q", async () => {
    setup("/jobs?q=globex");
    const side = await screen.findByRole("searchbox", { name: "Search jobs and companies" });
    expect(side).toHaveValue("globex");
  });

  it("has no axe violations", { timeout: 20_000 }, async () => {
    const { container } = setup("/jobs?sel=nw01");
    await screen.findByRole("table");
    await screen.findByRole("tab", { name: "Active (59)" });
    await act(async () => undefined);
    expect(await axeViolations(container)).toEqual([]);
  });
});
