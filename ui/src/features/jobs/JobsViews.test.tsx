import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, type Call } from "../../test/apiMock";
import { renderApp } from "../../test/renderApp";
import { JOBS, META, TABS_REPLY, job } from "./fixtures";

const ROWS = [
  job({ job_id: "a1", company: "Acme", title: "Backend Engineer", fit: 88, status: "applied",
    reasons: { covered: 7, total: 10, missing: ["Go", "Kubernetes", "Kafka"] } }),
  job({ job_id: "b2", company: "Borealis", fit: 70, status: "interview", reasons: null }),
  job({ job_id: "c3", company: "Cobalt", fit: 60, status: "needs_review" }),
];

function setup(path: string, rows = ROWS, extra: Record<string, unknown> = {}) {
  const api = mockApi({
    "GET /api/status": {},
    "GET /api/meta": META,
    "GET /api/jobs": () => ({ items: rows, total: rows.length, next_cursor: null }),
    "GET /api/jobs/tabs": TABS_REPLY,
    "GET /api/ui-state": { tour_done: true },
    "PUT /api/ui-state": (c: Call) => c.body,
    ...extra,
  });
  return { api, ...renderApp(path) };
}

beforeEach(() => vi.stubGlobal("scrollTo", vi.fn()));
afterEach(() => vi.unstubAllGlobals());

describe("Jobs tabs and List view", () => {
  it("shows Recommended / Saved / Applied with counts and lists cards by default", async () => {
    const { api } = setup("/jobs");
    expect(await screen.findByRole("tab", { name: "Recommended (59)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Saved (3)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Applied (41)" })).toBeInTheDocument();
    expect(api.callsTo("GET /api/jobs")[0]!.search.get("tab")).toBe("recommended");
    const card = (await screen.findByRole("link", { name: /Acme/ })).closest("li")!;
    expect(card).toHaveTextContent("88");
    expect(card).toHaveTextContent("7/10 skills · missing: Go, Kubernetes, +1");
    expect(screen.getAllByText("Match pending")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /Acme/ })).toHaveAttribute("href", "/jobs/a1");
  });

  it("toggles to Table, persists the choice and restores it on reload", async () => {
    const user = userEvent.setup();
    const { api } = setup("/jobs");
    await screen.findByRole("link", { name: /Acme/ });
    await user.click(screen.getByRole("radio", { name: "Table" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
    await waitFor(() => expect(api.callsTo("PUT /api/ui-state")[0]?.body).toEqual({ jobs_view: "table" }));
  });

  it("uses the remembered view when the URL has none", async () => {
    setup("/jobs", ROWS, { "GET /api/ui-state": { tour_done: true, jobs_view: "table" } });
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("offers Board only on Applied", async () => {
    setup("/jobs");
    await screen.findByRole("link", { name: /Acme/ });
    expect(screen.queryByRole("radio", { name: "Board" })).not.toBeInTheDocument();
  });

  it("marks a Needs-you job and a Saved job with words, not colour alone", async () => {
    setup("/jobs?tab=saved");
    const needs = (await screen.findByRole("link", { name: /Cobalt/ })).closest("li")!;
    expect(within(needs).getByText("Needs you")).toBeInTheDocument();
    expect(needs).toHaveAttribute("data-needs-you", "true");
    const saved = screen.getByRole("link", { name: /Borealis/ }).closest("li")!;
    expect(saved).not.toHaveAttribute("data-needs-you");
  });

  it("Start pipeline shows on Saved only", async () => {
    setup("/jobs?tab=saved&view=table", JOBS);
    await screen.findByRole("table");
    expect(screen.getByRole("button", { name: "Start pipeline" })).toBeInTheDocument();
  });
});

describe("Applied Board", () => {
  it("groups jobs by status column and moves a card by drag through POST /status", async () => {
    const { api } = setup("/jobs?tab=applied&view=board", ROWS, {
      "POST /api/jobs/a1/status": { job_id: "a1", status: "interview" },
    });
    const interview = await screen.findByRole("region", { name: "Interview" });
    expect(within(interview).getByText("Borealis")).toBeInTheDocument();
    const card = screen.getByText("Acme").closest("[draggable]")!;
    const data: Record<string, string> = {};
    const dataTransfer = { setData: (k: string, v: string) => (data[k] = v), getData: (k: string) => data[k] ?? "", effectAllowed: "" };
    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.drop(interview, { dataTransfer });
    await waitFor(() => expect(api.callsTo("POST /api/jobs/a1/status")[0]?.body).toMatchObject({ status: "interview" }));
  });

  it("keeps the card in place and shows the reason when the server refuses", async () => {
    setup("/jobs?tab=applied&view=board", ROWS, {
      "POST /api/jobs/a1/status": { status: 422, body: { detail: "applied → offer is not allowed" } },
    });
    const offer = await screen.findByRole("region", { name: "Offer" });
    const card = screen.getByText("Acme").closest("[draggable]")!;
    const dataTransfer = { setData: vi.fn(), getData: () => "a1", effectAllowed: "" };
    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.drop(offer, { dataTransfer });
    expect(await screen.findByText(/applied → offer is not allowed/)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Applied" })).getByText("Acme")).toBeInTheDocument();
  });
});
