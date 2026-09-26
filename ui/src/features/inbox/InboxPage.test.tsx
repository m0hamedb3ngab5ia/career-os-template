import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { mockApi, renderRoutes } from "../../test/mockApi";
import { draft } from "../drafts/fixtures";
import { InboxPage } from "./InboxPage";
import type { InboxDetailResponse, InboxResponse, InboxRow } from "./types";

const OFF = { available: false, reason: "Inbox sync isn't set up yet" };
const SEND_OFF = { available: false, reason: "Follow-up sending isn't built yet" };

function row(over: Partial<InboxRow>): InboxRow {
  return {
    job_id: "hooli0000001",
    company: "Hooli",
    title: "New Grad Engineer",
    status: "applied",
    tier: "B",
    applied_at: "2026-09-22T15:00:00+00:00",
    updated_at: "2026-09-22T15:00:00+00:00",
    days_since_applied: 2,
    last_email: null,
    next: { kind: "post_apply_outreach", due: "2026-09-25T15:00:00+00:00", mode: "verified_email" },
    drafts: 1,
    placeholders: 2,
    ...over,
  };
}

const LIST: InboxResponse = {
  items: [
    row({}),
    row({
      job_id: "stark0000001",
      company: "Stark Industries",
      title: "Software Engineer",
      status: "interview",
      tier: "A",
      last_email: {
        at: "2026-09-22T15:00:00+00:00",
        class: "interview_invite",
        from: "recruiting@example.com",
        status: "interview",
        link: "https://mail.google.com/mail/u/0/#all/thread-stark-1",
      },
      next: { kind: "post_interview_thanks", due: null, mode: "always_manual" },
    }),
  ],
  last_sync: null,
  sync: OFF,
  sending: SEND_OFF,
};

const HOOLI: InboxDetailResponse = {
  ...row({}),
  drafts: [draft()],
  primary: 0,
  thread: [
    { at: "2026-09-22T15:00:00+00:00", type: "pending_update", status: "screening", note: "assessment invite" },
    { at: "2026-09-22T14:00:00+00:00", type: "status", status: "applied", note: null },
  ],
  sync: OFF,
  sending: SEND_OFF,
};

const STARK: InboxDetailResponse = {
  ...LIST.items[1]!,
  drafts: [draft({ contact: "Pat Rivers", kind: "post_interview_thanks", mode: "always_manual", verified: false })],
  primary: 0,
  thread: [
    {
      at: "2026-09-22T15:00:00+00:00",
      type: "email",
      class: "interview_invite",
      from: "recruiting@example.com",
      link: "https://mail.google.com/mail/u/0/#all/thread-stark-1",
      status: "interview",
    },
  ],
  sync: OFF,
  sending: SEND_OFF,
};

const routes = [
  { path: "/inbox", element: <InboxPage /> },
  { path: "/inbox/:jobId", element: <InboxPage /> },
];

afterEach(() => vi.unstubAllGlobals());

describe("InboxPage", () => {
  it("lists post-apply jobs; the first is shown until one is picked; no axe violations", async () => {
    mockApi({ "GET /api/inbox": LIST, "GET /api/inbox/hooli0000001": HOOLI });
    const { container } = renderRoutes(routes, "/inbox");
    const list = await screen.findByRole("region", { name: "Post-apply" });
    const links = within(list).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/inbox/hooli0000001", "/inbox/stark0000001"]);
    expect(links[0]).toHaveAttribute("aria-current", "true");
    expect(within(list).getByText("Inbox sync hasn't run yet")).toBeInTheDocument();
    expect(within(links[1]!).getByText("Always manual")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Hooli · after-apply note" })).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("the draft preview marks placeholders; unbuilt actions are off with their reasons; nothing sends", async () => {
    const calls = mockApi({ "GET /api/inbox": LIST, "GET /api/inbox/hooli0000001": HOOLI });
    renderRoutes(routes, "/inbox/hooli0000001");
    const note = await screen.findByRole("region", { name: "Hooli · after-apply note" });
    expect(within(note).getByText("2 placeholders to fill before this can go out.")).toBeInTheDocument();
    expect([...note.querySelectorAll("mark")].map((m) => m.textContent)).toEqual([
      "[SPECIFIC CONNECTION]",
      "[MOST RELEVANT EXPERIENCE]",
    ]);
    const send = within(note).getByRole("button", { name: "Send now" });
    expect(send).toHaveAttribute("aria-disabled", "true");
    expect(send).toHaveAccessibleDescription("Follow-up sending isn't built yet");
    expect(within(note).getByRole("button", { name: "Pause auto-send" })).toHaveAccessibleDescription(
      "Follow-up sending isn't built yet",
    );
    expect(within(note).getByRole("button", { name: "Skip this note" })).toHaveAttribute("aria-disabled", "true");
    expect(within(note).getByRole("button", { name: "Fill in placeholders" })).toHaveAttribute("aria-disabled", "true");
    const sync = screen.getByRole("button", { name: "Sync inbox" });
    expect(sync).toHaveAccessibleDescription("Inbox sync isn't set up yet");
    await userEvent.setup().click(send);
    expect(calls.every((c) => c.method === "GET")).toBe(true);
  });

  it("Edit note opens the draft read-only in the sheet and Escape returns focus", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /api/inbox": LIST, "GET /api/inbox/hooli0000001": HOOLI });
    renderRoutes(routes, "/inbox/hooli0000001");
    const edit = await screen.findByRole("button", { name: "Edit note" });
    await user.click(edit);
    const dialog = screen.getByRole("dialog", { name: "After-apply note" });
    expect(within(dialog).getByRole("button", { name: "Approve after-apply note" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(edit).toHaveFocus();
  });

  it("the thread shows classified emails and pending updates, newest first", async () => {
    mockApi({ "GET /api/inbox": LIST, "GET /api/inbox/hooli0000001": HOOLI, "GET /api/inbox/stark0000001": STARK });
    renderRoutes(routes, "/inbox/hooli0000001");
    const thread = await screen.findByRole("region", { name: "Thread" });
    const items = within(thread).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Inbox sync found a change it couldn't apply: assessment invite");
    expect(items[1]).toHaveTextContent("You applied");
  });

  it("a thank-you note is always manual: no Send now, no auto-send", async () => {
    mockApi({ "GET /api/inbox": LIST, "GET /api/inbox/stark0000001": STARK });
    renderRoutes(routes, "/inbox/stark0000001");
    const note = await screen.findByRole("region", { name: "Stark Industries · thank-you after interview" });
    expect(within(note).getAllByText("Always manual").length).toBeGreaterThan(0);
    expect(within(note).queryByRole("button", { name: "Send now" })).toBeNull();
    expect(within(note).queryByRole("button", { name: "Pause auto-send" })).toBeNull();
    const thread = screen.getByRole("region", { name: "Thread" });
    expect(within(thread).getByText(/Interview invite from recruiting@example.com/)).toBeInTheDocument();
    expect(within(thread).getByRole("link", { name: /Open in Gmail/ })).toHaveAttribute(
      "href",
      "https://mail.google.com/mail/u/0/#all/thread-stark-1",
    );
    expect(screen.getByRole("link", { name: "All follow-ups" })).toHaveAttribute("href", "/inbox");
  });

  it("empty state when nothing is past applying", async () => {
    mockApi({ "GET /api/inbox": { items: [], last_sync: null, sync: OFF, sending: SEND_OFF } });
    renderRoutes(routes, "/inbox");
    expect(await screen.findByRole("heading", { name: "Nothing after applying yet" })).toBeInTheDocument();
  });

  it("a job without drafts says where drafts come from", async () => {
    mockApi({
      "GET /api/inbox": LIST,
      "GET /api/inbox/hooli0000001": { ...HOOLI, drafts: [], primary: null, thread: [] },
    });
    renderRoutes(routes, "/inbox/hooli0000001");
    expect(await screen.findByRole("heading", { name: "No draft for this job" })).toBeInTheDocument();
    expect(screen.getByText(/\/draft-outreach/)).toBeInTheDocument();
    expect(screen.getByText("No emails synced for this job yet.")).toBeInTheDocument();
  });
});
