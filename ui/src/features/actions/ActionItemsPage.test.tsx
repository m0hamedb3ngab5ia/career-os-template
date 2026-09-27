import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../app/routes";
import { axeViolations } from "../../test/axe";
import { FakeEventSource } from "../../test/fakeEventSource";
import { META, mockApi, renderRoutes } from "../../test/mockApi";
import type { ActionItem, ActionsView } from "./types";

// Fictional companies only.
function item(over: Partial<ActionItem>): ActionItem {
  return {
    id: "a1", created: "2026-09-20 10:00:00", job_id: "j1", company: "Umbrella Labs", role: "Infrastructure Engineer",
    type: "review", what: "Review and submit", link: "https://boards.greenhouse.io/umbrella/jobs/1", priority: "H",
    needs: "laptop", done: false, done_date: null, due: null, due_date_only: false, due_reason: null,
    bucket: "nodate", level: "none", scam_actions: false, ...over,
  };
}

const OVERDUE = item({ id: "late", company: "Initech", role: "Platform Engineer", what: "Send the note", type: "send_linkedin",
  link: "https://www.linkedin.com/in/example", priority: "M", needs: "phone", due: "2026-09-23T23:59:59Z",
  due_date_only: true, due_reason: "note was due", bucket: "overdue", level: "overdue" });
const TODAY = item({ id: "cap", company: "Globex", what: "Solve the captcha", type: "captcha", due: "2026-09-24T18:00:00Z",
  due_reason: "saved form expires", bucket: "today", level: "soon", link: "https://jobs.ashbyhq.com/globex/1" });
const LATER = item({ id: "wk", company: "Hooli", due: "2026-10-03T23:59:59Z", due_date_only: true, due_reason: "posting closes",
  bucket: "week", level: "later" });
const NODATE = item({ id: "nd", company: "Stark Industries", link: "", job_id: "j9", type: "profile_gap", priority: "L", needs: "anytime" });
const SCAM = item({ id: "scam", company: "Obsidian Quant Partners", role: "Quant Developer", type: "scam_suspected",
  what: "Posting asks for a paid equipment kit.", link: "https://obsidian-careers.example/jobs/1", scam_actions: true });

function view(over: Partial<ActionsView> = {}): ActionsView {
  return {
    tab: "open", group: "due", sort: "soonest", counts: { open: 5, today: 2, done: 3 }, head: { overdue: 1, soon: 1 },
    groups: [
      { key: "overdue", count: 1, items: [OVERDUE] },
      { key: "today", count: 1, items: [TODAY] },
      { key: "week", count: 1, items: [LATER] },
      { key: "nodate", count: 2, items: [NODATE, SCAM] },
    ],
    more_done: 0, now: "2026-09-24T15:00:00Z", ...over,
  };
}

function setup(v: ActionsView | ((url: string) => ActionsView) = view(), extra: Record<string, unknown> = {}) {
  const calls = mockApi({
    "GET /api/meta": META,
    "GET /api/status": {},
    "GET /api/actions": ({ url }: { url: string }) => (typeof v === "function" ? v(url) : v),
    ...extra,
  });
  const r = renderRoutes(routes, "/actions");
  return { calls, ...r };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true, now: new Date("2026-09-24T15:00:00Z") });
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Action Items", () => {
  it("groups by due date with the mockup's headings, counts and head line", { timeout: 20_000 }, async () => {
    setup();
    expect(await screen.findByRole("heading", { level: 1, name: "Action Items" }, { timeout: 8000 })).toBeInTheDocument();
    await screen.findByRole("heading", { name: "Overdue 1" }, { timeout: 8000 });
    const heads = within(screen.getByRole("main")).getAllByRole("heading", { level: 2 });
    expect(heads.map((h) => h.textContent)).toEqual(["Overdue 1", "Today 1", "Next 7 days 1", "No date 2"]);
    expect(screen.getByText("1 overdue")).toBeInTheDocument();
    expect(screen.getByText("1 due within 48 hours")).toBeInTheDocument();
    const tabs = screen.getByRole("radiogroup", { name: "Show" });
    expect(within(tabs).getByRole("radio", { name: "Open 5" })).toHaveAttribute("aria-checked", "true");
    expect(within(tabs).getByRole("radio", { name: "Today 2" })).toBeInTheDocument();
    expect(within(tabs).getByRole("radio", { name: "Done 3" })).toBeInTheDocument();
  });

  it("words deadlines relatively when close, absolutely further out; red only overdue, orange only soon", async () => {
    setup();
    const late = await screen.findByText(/Overdue by 1 day · note was due/);
    expect(late.closest("[data-level]")).toHaveAttribute("data-level", "overdue");
    expect(screen.getByText("Today, 6:00 PM · saved form expires").closest("[data-level]")).toHaveAttribute("data-level", "soon");
    expect(screen.getByText("Sat, Oct 3 · posting closes").closest("[data-level]")).toHaveAttribute("data-level", "later");
  });

  it("links are real ↗ hyperlinks named for what they open; items without a web link open the job", async () => {
    setup();
    const a = await screen.findByRole("link", { name: /Open Ashby application/ });
    expect(a).toHaveAttribute("href", "https://jobs.ashbyhq.com/globex/1");
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveTextContent("↗");
    expect(screen.getByRole("link", { name: /Open LinkedIn profile/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open job" })).toHaveAttribute("href", "/jobs/j9");
    // type label, priority chip, needs
    expect(screen.getByText("Captcha")).toBeInTheDocument();
    expect(screen.getAllByText("High").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Phone").length).toBeGreaterThan(0);
  });

  it("keeps group, sort and tab in the URL and asks the server for them", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { calls, router } = setup();
    await screen.findByRole("heading", { name: /Overdue/ });
    await user.click(screen.getByRole("button", { name: "Group by Due date" }));
    await user.click(screen.getByRole("option", { name: "Priority" }));
    await waitFor(() => expect(router.state.location.search).toBe("?group=priority"));
    await user.click(screen.getByRole("button", { name: /^Sort/ }));
    await user.click(screen.getByRole("option", { name: "Newest first" }));
    await waitFor(() => expect(router.state.location.search).toContain("sort=newest"));
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("group=priority") && c.url.includes("sort=newest"))).toBe(true),
    );
    expect(calls.find((c) => c.url.startsWith("/api/actions"))!.url).toContain("tz=");
  });

  it("marks one item done with an undo toast that reopens it", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { calls } = setup(view(), {
      "POST /api/actions/cap/done": { ok: ["cap"], queued: [], missing: [] },
      "POST /api/actions/cap/reopen": { ok: ["cap"], queued: [], missing: [] },
    });
    await user.click(await screen.findByRole("checkbox", { name: "Mark Globex done" }));
    expect(await screen.findByText("Marked done: Globex")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe("/api/actions/cap/done");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/actions/cap/reopen")).toBe(true));
  });

  it("multi-select marks N selected done in one request, with undo", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { calls, router } = setup(view(), {
      "POST /api/actions/bulk-done": { ok: ["cap", "wk"], queued: [], missing: [] },
      "POST /api/actions/bulk-reopen": { ok: ["cap", "wk"], queued: [], missing: [] },
    });
    await screen.findByRole("checkbox", { name: "Select Globex" });
    const bulk = screen.getByRole("button", { name: "Mark selected done" });
    expect(bulk).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "Select Globex" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Hooli" }));
    await waitFor(() => expect(router.state.location.search).toContain("sel=cap%2Cwk"));
    await user.click(screen.getByRole("button", { name: "Mark 2 selected done" }));
    expect(await screen.findByText("Marked 2 done")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/actions/bulk-done")!.body).toEqual({ ids: ["cap", "wk"] });
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/actions/bulk-reopen")).toBe(true));
  });

  it("Add date opens a sheet and saves a date (never invents one)", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { calls } = setup(view(), { "POST /api/actions/nd/due": { ok: ["nd"], queued: [], missing: [] } });
    const btn = await screen.findByRole("button", { name: "Add date for Stark Industries" });
    await user.click(btn);
    const dialog = screen.getByRole("dialog", { name: "Add date" });
    expect(within(dialog).getByLabelText("Date")).toBeRequired();
    await user.type(within(dialog).getByLabelText("Date"), "2026-10-01");
    await user.type(within(dialog).getByLabelText("Why this date (optional)"), "posting closes");
    await user.click(within(dialog).getByRole("button", { name: "Save date" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(calls.find((c) => c.url === "/api/actions/nd/due")!.body).toEqual({ due: "2026-10-01", due_reason: "posting closes" });
  });

  it("scam item: Block company asks first, then blocks with undo", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { calls } = setup(view(), {
      "POST /api/actions/scam/block-company": { company: "Obsidian Quant Partners", added: true, queued: false, job_id: "j5" },
      "POST /api/actions/scam/unblock-company": { removed: true },
    });
    await user.click(await screen.findByRole("button", { name: "Block company" }));
    const confirm = screen.getByRole("alertdialog", { name: "Block Obsidian Quant Partners?" });
    expect(within(confirm).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.click(within(confirm).getByRole("button", { name: "Block company" }));
    expect(await screen.findByText("Blocked Obsidian Quant Partners")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(calls.find((c) => c.url === "/api/actions/scam/unblock-company")?.body).toEqual({ company: "Obsidian Quant Partners", remove: true }),
    );
  });

  it("scam item: Undo after Block of an already-blocked company leaves the blocklist entry; queued says so", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { calls } = setup(view(), {
      "POST /api/actions/scam/block-company": { company: "Obsidian Quant Partners", added: false, queued: true, job_id: "j5" },
      "POST /api/actions/scam/unblock-company": { removed: false },
    });
    await user.click(await screen.findByRole("button", { name: "Block company" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Block company" }));
    expect(await screen.findByText(/already blocked.*run careeros tracker flush/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(calls.find((c) => c.url === "/api/actions/scam/unblock-company")?.body).toEqual({
        company: "Obsidian Quant Partners", remove: false,
      }),
    );
  });

  it("Add date: focus lands on the row after the sheet closes; a queued write says so", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let saved = false;
    const dated = { ...NODATE, due: "2026-10-01T23:59:59Z", due_date_only: true, bucket: "week", level: "later" } as ActionItem;
    setup(() => view({ groups: [{ key: "nodate", count: 2, items: [saved ? dated : NODATE, SCAM] }] }), {
      "POST /api/actions/nd/due": () => {
        saved = true;
        return { ok: [], queued: ["nd"], missing: [] };
      },
    });
    await user.click(await screen.findByRole("button", { name: "Add date for Stark Industries" }));
    const dialog = screen.getByRole("dialog", { name: "Add date" });
    await user.type(within(dialog).getByLabelText("Date"), "2026-10-01");
    await user.click(within(dialog).getByRole("button", { name: "Save date" }));
    expect(await screen.findByText(/Date added for Stark Industries.*run careeros tracker flush/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Mark Stark Industries done" })).toHaveFocus());
  });

  it("scam item: Mark posting safe confirms, then undo sends back what the server returned", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const before = { company: "Obsidian Quant Partners", state: "active" };
    const { calls } = setup(view(), {
      "POST /api/actions/scam/mark-safe": { company: "Obsidian Quant Partners", job_id: "j5", previous_status: "needs_review",
        registry_before: before, queued: false },
      "POST /api/actions/scam/mark-safe/undo": {},
    });
    await user.click(await screen.findByRole("button", { name: "Mark posting safe" }));
    const confirm = screen.getByRole("alertdialog", { name: "Mark this posting safe?" });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Mark posting safe" })).toHaveFocus();
    expect(confirm).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mark posting safe" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Mark posting safe" }));
    expect(await screen.findByText("Marked Obsidian Quant Partners posting safe")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(calls.find((c) => c.url === "/api/actions/scam/mark-safe/undo")?.body).toEqual({
        previous_status: "needs_review", registry_before: before,
      }),
    );
  });

  it("Done tab lists done items with Reopen", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const done = item({ id: "d1", company: "Hooli", what: "Solve the captcha", done: true, done_date: "2026-09-23" });
    const { calls } = setup(
      (url) => (url.includes("tab=done") ? view({ tab: "done", groups: [{ key: "done", count: 3, items: [done] }], more_done: 2 }) : view()),
      { "POST /api/actions/d1/reopen": { ok: ["d1"], queued: [], missing: [] } },
    );
    await user.click(await screen.findByRole("radio", { name: "Done 3" }));
    await user.click(await screen.findByRole("button", { name: "Reopen: Hooli" }));
    expect(await screen.findByText("2 more done earlier")).toBeInTheDocument();
    await waitFor(() => expect(calls.some((c) => c.url === "/api/actions/d1/reopen")).toBe(true));
    expect(screen.queryByRole("button", { name: /Group by/ })).toBeNull();
  });

  it("empty: says nothing needs you, with zero counts", async () => {
    setup(view({ groups: [], counts: { open: 0, today: 0, done: 0 }, head: { overdue: 0, soon: 0 } }));
    expect(await screen.findByText("Nothing needs you right now. New items appear after the next run.")).toBeInTheDocument();
    expect(screen.getByText("none overdue")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Open 0" })).toBeInTheDocument();
  });

  it("Add item sheet posts the new item", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { calls } = setup(view(), { "POST /api/actions": { id: "new1" } });
    await user.click(await screen.findByRole("button", { name: "Add item" }));
    const dialog = screen.getByRole("dialog", { name: "Add item" });
    await user.type(within(dialog).getByLabelText("What to do"), "Call the recruiter back");
    await user.type(within(dialog).getByLabelText("Link (optional)"), "https://mail.example.com/t/1");
    await user.selectOptions(within(dialog).getByLabelText("Needs"), "phone");
    await user.click(within(dialog).getByRole("button", { name: "Add item" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(calls.find((c) => c.method === "POST" && c.url === "/api/actions")!.body).toMatchObject({
      what: "Call the recruiter back", needs: "phone", link: "https://mail.example.com/t/1", due: null,
    });
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByRole("heading", { name: /No date/ });
    await act(async () => {
      expect(await axeViolations(container)).toEqual([]);
    });
  }, 20_000);
});
