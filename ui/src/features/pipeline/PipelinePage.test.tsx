import { act, screen, waitFor, within } from "@testing-library/react";
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

const HOOLI = card({ job_id: "h1", company: "Hooli", title: "New Grad Engineer", status: "applied", fit: 84, tier: "B",
  qa_passed: true, override: "manual", hint: { kind: "action", type: "salary", due: "2026-09-29T23:59:59Z", due_reason: null } });
const STARK = card({ job_id: "s1", company: "Stark Industries", title: "Software Engineer", status: "interview", fit: 86,
  tier: "A", safety: "review", hint: { kind: "safety", text: "asks for payment" } });

function board(over: Partial<Board> = {}): Board {
  return {
    funnel: [
      { status: "found", count: 12 }, { status: "scored", count: 3 }, { status: "queued", count: 1 },
      { status: "prepared", count: 0 }, { status: "needs_review", count: 2 },
    ],
    submitted: { count: 4, since: "2026-09-21" },
    applications: [STARK, HOOLI],
    closed: { count: 3, by_status: { skipped: 2, rejected: 1 } },
    options: { categories: ["swe_backend"], locations: [{ value: "New York, NY", count: 3 }, { value: "Remote", count: 1 }] },
    ...over,
  };
}

function setup(b: Board | ((url: string) => Board) = board(), extra: Record<string, unknown> = {}, path = "/pipeline") {
  const calls = mockApi({
    "GET /api/meta": META,
    "GET /api/status": {},
    "GET /api/pipeline": ({ url }: { url: string }) => (typeof b === "function" ? b(url) : b),
    ...extra,
  });
  return { calls, ...renderRoutes(routes, path) };
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

async function group(name: RegExp) {
  return (await screen.findByRole("region", { name }, { timeout: 8000 })) as HTMLElement;
}

describe("Pipeline", () => {
  it("funnel counts link to Jobs filtered to that stage", { timeout: 20_000 }, async () => {
    setup();
    const funnel = await screen.findByRole("navigation", { name: "Automation funnel" }, { timeout: 8000 });
    const link = (name: RegExp) => within(funnel).getByRole("link", { name }).getAttribute("href");
    expect(link(/^12 New$/)).toBe("/jobs?tab=all&f.status=found");
    expect(link(/^1 Ready to prepare$/)).toBe("/jobs?tab=all&f.status=queued");
    expect(link(/^0 Ready to apply$/)).toBe("/jobs?tab=all&f.status=prepared");
    expect(link(/^2 Needs your review$/)).toBe("/jobs?tab=all&f.status=needs_review");
    expect(link(/^4 Submitted this week$/)).toBe("/jobs?tab=all&f.applied_at=2026-09-21..");
    expect(screen.getByRole("link", { name: "Closed: 3 (skipped 2 · rejected 1)" })).toHaveAttribute(
      "href", "/jobs?tab=all&f.status=skipped%2Crejected%2Cwithdrawn%2Cghosted");
  });

  it("applications are grouped Applied · Screening · Interview · Offer, with no drag", { timeout: 20_000 }, async () => {
    setup();
    const applied = await group(/^Applied 1/);
    expect(within(applied).getByRole("link", { name: /Hooli/ })).toHaveAttribute("href", "/jobs/h1");
    expect(within(applied).getByText("Override: manual")).toBeInTheDocument();
    expect(within(applied).getByText("Salary")).toBeInTheDocument();
    expect(within(await group(/^Interview 1/)).getByText("Asks for payment")).toBeInTheDocument();
    expect(within(await group(/^Offer 0/)).getByText("None yet")).toBeInTheDocument();
    expect(await group(/^Screening 0/)).toBeInTheDocument();
    expect(document.querySelector("[draggable='true']")).toBeNull();
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

  it("Move to… (keyboard) changes status, with undo, and keeps focus on the card", async () => {
    const user = userEvent.setup();
    let moved = false;
    const b = () => (moved ? board({ applications: [{ ...STARK, status: "offer" }, HOOLI] }) : board());
    const { calls } = setup(b, {
      "POST /api/jobs/s1/status": ({ body }: { body: { status: string } }) => {
        moved = body.status === "offer";
        return { job_id: "s1", status: body.status, previous: body.status === "offer" ? "interview" : "offer" };
      },
    });
    const btn = within(await group(/^Interview/)).getByRole("button", { name: "Move to… (Stark Industries)" });
    btn.focus();
    await user.keyboard("{ArrowDown}");
    const menu = screen.getByRole("menu", { name: "Move Stark Industries to" });
    expect(within(menu).getByRole("menuitem", { name: "Interview" })).toHaveAttribute("aria-disabled", "true");
    within(menu).getByRole("menuitem", { name: "Offer" }).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Moved Stark Industries to Offer")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ status: "offer" });
    const offer = await group(/^Offer 1/);
    await waitFor(() => expect(within(offer).getByRole("button", { name: "Move to… (Stark Industries)" })).toHaveFocus());
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST").at(-1)!.body).toMatchObject({ status: "interview" }));
  });

  it("moving into Applied asks first and has no Undo (it records the date applied and counts to the cap)", async () => {
    const user = userEvent.setup();
    const { calls } = setup(board(), {
      "POST /api/jobs/s1/submitted": { job_id: "s1", status: "applied", previous: "interview" },
    });
    const interview = await group(/^Interview/);
    await user.click(within(interview).getByRole("button", { name: "Move to… (Stark Industries)" }));
    await user.click(screen.getByRole("menuitem", { name: "Applied" }));
    const dialog = screen.getByRole("dialog", { name: "Mark Stark Industries applied?" });
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.click(within(interview).getByRole("button", { name: "Move to… (Stark Industries)" }));
    await user.click(screen.getByRole("menuitem", { name: "Applied" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark applied" }));
    expect(await screen.findByText("Moved Stark Industries to Applied")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.url).toBe("/api/jobs/s1/submitted"); // Mark submitted, not Set status
    expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
  });

  it("Closed… asks which closed status", async () => {
    const user = userEvent.setup();
    const { calls } = setup(board(), {
      "POST /api/jobs/h1/status": { job_id: "h1", status: "rejected", previous: "applied" },
    });
    await user.click(within(await group(/^Applied/)).getByRole("button", { name: "Move to… (Hooli)" }));
    await user.click(screen.getByRole("menuitem", { name: "Closed…" }));
    const dialog = screen.getByRole("dialog", { name: "Move Hooli to Closed" });
    await user.click(within(dialog).getByRole("radio", { name: "Rejected" }));
    await user.click(within(dialog).getByRole("button", { name: "Move" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ status: "rejected" }));
  });

  it("Closed link carries the active filters to Jobs", async () => {
    setup(board(), {}, "/pipeline?tier=A");
    expect(await screen.findByRole("link", { name: /^Closed: 3/ })).toHaveAttribute(
      "href", "/jobs?tab=all&f.status=skipped%2Crejected%2Cwithdrawn%2Cghosted&f.tier=A");
  });

  it("empty data shows zeros and empty groups, never sample cards", async () => {
    setup(board({
      funnel: board().funnel.map((f) => ({ ...f, count: 0 })),
      submitted: { count: 0, since: "2026-09-21" },
      applications: [],
      closed: { count: 0, by_status: {} },
      options: { categories: [], locations: [] },
    }));
    expect(await screen.findByRole("link", { name: "Closed: 0" })).toBeInTheDocument();
    expect(screen.getAllByText("None yet")).toHaveLength(4);
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await group(/^Applied/);
    await act(async () => {
      expect(await axeViolations(container)).toEqual([]);
    });
  }, 20_000);
});
