import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../app/routes";
import { axeViolations } from "../../test/axe";
import { FakeEventSource } from "../../test/fakeEventSource";
import { META, mockApi, renderRoutes } from "../../test/mockApi";
import type { Board, Card } from "./types";

// Fictional companies only.
function card(over: Partial<Card>): Card {
  return {
    job_id: "j1", company: "Acme Robotics", title: "Backend Engineer", location: "New York, NY", category: "swe_backend",
    fit: null, tier: null, status: "found", safety: "pass", qa_passed: null, qa_score: null, found_at: null, updated_at: null, override: null,
    hint: { kind: "not_scored" }, ...over,
  };
}

const QUEUED = card({ job_id: "q1", company: "Initech", title: "Platform Engineer", status: "queued", fit: 88, tier: "B",
  qa_passed: true, override: "manual", hint: { kind: "action", type: "salary", due: "2026-09-29T23:59:59Z", due_reason: null } });
const REVIEW = card({ job_id: "r1", company: "Umbrella Labs", title: "Infrastructure Engineer", status: "needs_review",
  fit: 91, tier: "A", safety: "review", hint: { kind: "tier_a" } });
const SCAM = card({ job_id: "s1", company: "Obsidian Quant Partners", title: "Quant Developer", status: "needs_review", fit: 74,
  safety: "block", hint: { kind: "safety", text: "asks for payment" } });

function board(over: Partial<Board> = {}): Board {
  return {
    columns: [
      { name: "Found", statuses: ["found", "scored"], count: 12, cards: [card({})] },
      { name: "Queued", statuses: ["queued", "prepared"], count: 1, cards: [QUEUED] },
      { name: "Needs review", statuses: ["needs_review"], count: 2, cards: [REVIEW, SCAM] },
      { name: "Applied", statuses: ["applied"], count: 0, cards: [] },
      { name: "Screening · Interview", statuses: ["screening", "interview"], count: 0, cards: [] },
      { name: "Offer", statuses: ["offer"], count: 0, cards: [] },
    ],
    closed: { count: 3, by_status: { skipped: 2, rejected: 1 } },
    card_limit: 10,
    options: { categories: ["swe_backend"], locations: [{ value: "New York, NY", count: 3 }, { value: "Remote", count: 1 }] },
    ...over,
  };
}

function setup(b: Board | ((url: string) => Board) = board(), extra: Record<string, unknown> = {}) {
  const calls = mockApi({
    "GET /api/meta": META,
    "GET /api/status": {},
    "GET /api/pipeline": ({ url }: { url: string }) => (typeof b === "function" ? b(url) : b),
    ...extra,
  });
  return { calls, ...renderRoutes(routes, "/pipeline") };
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

async function columnNamed(name: RegExp) {
  return (await screen.findByRole("region", { name }, { timeout: 8000 })) as HTMLElement;
}

describe("Pipeline", () => {
  it("draws the configured columns with counts, cards and the Closed line", { timeout: 20_000 }, async () => {
    setup();
    const found = await columnNamed(/^Found 12 jobs/);
    expect(within(found).getByText("Acme Robotics")).toBeInTheDocument();
    expect(within(found).getByText("Not scored yet", { selector: ":not(.sr-only)" })).toBeInTheDocument();
    const queued = await columnNamed(/^Queued 1/);
    expect(within(queued).getByText("Override: manual")).toBeInTheDocument();
    expect(within(queued).getByText("QA")).toBeInTheDocument();
    expect(within(queued).getByText("Salary")).toBeInTheDocument();
    expect(within(queued).getByRole("link", { name: /Initech/ })).toHaveAttribute("href", "/jobs/q1");
    const review = await columnNamed(/^Needs review 2/);
    expect(within(review).getByText("Tier A · you submit")).toBeInTheDocument();
    expect(within(review).getByText("Asks for payment")).toBeInTheDocument();
    expect(within(await columnNamed(/^Offer 0/)).getByText("No jobs here yet")).toBeInTheDocument();
    expect(screen.getByText("Closed: 3 (skipped 2 · rejected 1)")).toBeInTheDocument();
  });

  it("Show all asks the server for the whole column and keeps it in the URL", async () => {
    const user = userEvent.setup();
    const { calls, router } = setup();
    await user.click(await screen.findByRole("button", { name: "Show all 12 Found jobs" }));
    await waitFor(() => expect(router.state.location.search).toBe("?expand=Found"));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/pipeline?expand=Found")).toBe(true));
  });

  it("filters are listboxes kept in the URL", async () => {
    const user = userEvent.setup();
    const { calls, router } = setup();
    await user.click(await screen.findByRole("button", { name: "Tier: All" }));
    await user.click(screen.getByRole("option", { name: "A" }));
    await user.click(screen.getByRole("button", { name: "Location: All" }));
    await user.click(screen.getByRole("option", { name: "Remote" }));
    await waitFor(() => expect(router.state.location.search).toBe("?tier=A&location=Remote"));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/pipeline?tier=A&location=Remote")).toBe(true));
  });

  it("Move to… (keyboard) moves a card to a one-status column, with undo, and keeps focus on the card", async () => {
    const user = userEvent.setup();
    let moved = false;
    const b = () => {
      const base = board();
      if (!moved) return base;
      const cols = base.columns.map((c) => ({ ...c, cards: c.cards.filter((x) => x.job_id !== "r1") }));
      cols.find((c) => c.name === "Offer")!.cards.push({ ...REVIEW, status: "offer" });
      return { ...base, columns: cols };
    };
    const { calls } = setup(b, {
      "POST /api/jobs/r1/status": ({ body }: { body: { status: string } }) => {
        moved = body.status === "offer";
        return { job_id: "r1", status: body.status, previous: body.status === "offer" ? "needs_review" : "offer" };
      },
    });
    const review = await columnNamed(/^Needs review/);
    const btn = within(review).getByRole("button", { name: "Move to… (Umbrella Labs)" });
    btn.focus();
    await user.keyboard("{ArrowDown}");
    const menu = screen.getByRole("menu", { name: "Move Umbrella Labs to" });
    expect(within(menu).getByRole("menuitem", { name: "Needs review" })).toHaveAttribute("aria-disabled", "true");
    within(menu).getByRole("menuitem", { name: "Offer" }).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Moved Umbrella Labs to Offer")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ status: "offer" });
    const offer = await columnNamed(/^Offer/);
    await waitFor(() =>
      expect(within(offer).getByRole("button", { name: "Move to… (Umbrella Labs)" })).toHaveFocus(),
    );
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST").at(-1)!.body).toMatchObject({ status: "needs_review" }));
  });

  it("moving into Applied asks first and has no Undo (it records the date applied and counts to the cap)", async () => {
    const user = userEvent.setup();
    const { calls } = setup(board(), {
      "POST /api/jobs/r1/submitted": { job_id: "r1", status: "applied", previous: "needs_review" },
    });
    const review = await columnNamed(/^Needs review/);
    await user.click(within(review).getByRole("button", { name: "Move to… (Umbrella Labs)" }));
    await user.click(screen.getByRole("menuitem", { name: "Applied" }));
    const dialog = screen.getByRole("dialog", { name: "Mark Umbrella Labs applied?" });
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.click(within(review).getByRole("button", { name: "Move to… (Umbrella Labs)" }));
    await user.click(screen.getByRole("menuitem", { name: "Applied" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark applied" }));
    expect(await screen.findByText("Moved Umbrella Labs to Applied")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.url).toBe("/api/jobs/r1/submitted"); // Mark submitted, not Set status
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("moving into a column with several statuses asks which one", async () => {
    const user = userEvent.setup();
    const { calls } = setup(board(), {
      "POST /api/jobs/r1/status": { job_id: "r1", status: "prepared", previous: "needs_review" },
    });
    const review = await columnNamed(/^Needs review/);
    await user.click(within(review).getByRole("button", { name: "Move to… (Umbrella Labs)" }));
    await user.click(screen.getByRole("menuitem", { name: "Queued" }));
    const dialog = screen.getByRole("dialog", { name: "Move Umbrella Labs to Queued" });
    await user.click(within(dialog).getByRole("radio", { name: "Prepared" }));
    await user.click(within(dialog).getByRole("button", { name: "Move" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ status: "prepared" }));
  });

  it("drag and drop onto another column sets the status", async () => {
    const { calls } = setup(board(), {
      "POST /api/jobs/q1/submitted": { job_id: "q1", status: "applied", previous: "queued" },
    });
    const queued = await columnNamed(/^Queued/);
    const cardEl = within(queued).getByText("Initech").closest("[draggable='true']")!;
    const applied = await columnNamed(/^Applied/);
    const dt = { setData: vi.fn(), effectAllowed: "", dropEffect: "" };
    fireEvent.dragStart(cardEl, { dataTransfer: dt });
    fireEvent.dragOver(applied, { dataTransfer: dt });
    await waitFor(() => expect(applied).toHaveAttribute("data-drop"));
    fireEvent.drop(applied, { dataTransfer: dt });
    await userEvent.setup().click(within(screen.getByRole("dialog", { name: "Mark Initech applied?" })).getByRole("button", { name: "Mark applied" }));
    // Applied goes through Mark submitted (it records the date applied), not Set status
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.url).toBe("/api/jobs/q1/submitted"));
  });

  it("Add job is disabled with a plain-language reason; Table links to Jobs", async () => {
    const user = userEvent.setup();
    setup();
    const add = await screen.findByRole("button", { name: "Add job" });
    expect(add).toHaveAttribute("aria-disabled", "true");
    expect(add).toHaveAccessibleDescription("Adding jobs by hand isn't supported yet — run scout");
    await user.click(add);
    expect(screen.queryByRole("dialog")).toBeNull();
    const view = screen.getByRole("navigation", { name: "View" });
    expect(within(view).getByRole("link", { name: "Table" })).toHaveAttribute("href", "/jobs");
    expect(within(view).getByRole("link", { name: "Board" })).toHaveAttribute("aria-current", "page");
  });

  it("empty data shows zeros and empty columns, never sample cards", async () => {
    setup(board({
      columns: board().columns.map((c) => ({ ...c, count: 0, cards: [] })),
      closed: { count: 0, by_status: {} },
      options: { categories: [], locations: [] },
    }));
    expect(await screen.findByText("Closed: 0")).toBeInTheDocument();
    expect(screen.getAllByText("No jobs here yet")).toHaveLength(6);
    expect(screen.queryByRole("button", { name: /Show all/ })).toBeNull();
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await columnNamed(/^Found/);
    await act(async () => {
      expect(await axeViolations(container)).toEqual([]);
    });
  }, 20_000);
});
