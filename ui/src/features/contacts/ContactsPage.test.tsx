import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { mockApi, renderRoutes } from "../../test/mockApi";
import { draft, linkedinDraft } from "../drafts/fixtures";
import { ContactsPage } from "./ContactsPage";
import type { ContactRow, ContactsResponse } from "./types";

function row(over: Partial<ContactRow>): ContactRow {
  return {
    job_id: "stark0000001",
    company: "Stark Industries",
    job_title: "Software Engineer",
    job_status: "interview",
    name: "Sam Lee",
    title: "Recruiter",
    linkedin: "https://www.linkedin.com/in/example-sam",
    email: null,
    email_confidence: null,
    linkedin_degree: null,
    mutuals: null,
    sent: false,
    replied: null,
    manual: false,
    manual_reason: null,
    manual_detail: null,
    draft: null,
    mode: "no_draft",
    ...over,
  };
}

const DATA: ContactsResponse = {
  items: [
    row({
      name: "Pat Rivers",
      title: "Engineering Manager",
      linkedin_degree: 1,
      manual: true,
      manual_reason: "LINKEDIN_CONNECTED",
      manual_detail: "connected on LinkedIn",
      mode: "manual",
      draft: linkedinDraft({ contact: "Pat Rivers", mode: "manual", manual_tailor: true }),
    }),
    row({ name: "Sam Lee", linkedin_degree: 2, mutuals: 12, manual: true, mode: "manual", manual_detail: "12 mutual connections" }),
    row({ name: "Riley Park", title: "Technical Recruiter", linkedin_degree: 3, mode: "linkedin_draft", draft: linkedinDraft({ contact: "Riley Park" }) }),
    row({
      job_id: "hooli0000001",
      company: "Hooli",
      name: "Dana Cruz",
      title: "Technical Recruiter",
      email: "dana.cruz@example.com",
      email_confidence: "verified",
      mode: "email_draft",
      draft: draft(),
    }),
  ],
  linkedin_drafts: 1,
  policy: { manual_if_connected: true, manual_if_mutuals: true },
};

const routes = [{ path: "/contacts", element: <ContactsPage /> }];

afterEach(() => vi.unstubAllGlobals());

describe("ContactsPage", () => {
  it("lists contacts with avatar initials, connection, mutuals and outreach mode; no axe violations", async () => {
    mockApi({ "GET /api/contacts": DATA, "GET /api/meta": {} });
    const { container } = renderRoutes(routes, "/contacts");
    const table = await screen.findByRole("table", { name: "Contacts at companies you applied to" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    const pat = rows[0]!;
    expect(within(pat).getByText("PR")).toBeInTheDocument();
    expect(within(pat).getByText("Connected")).toBeInTheDocument();
    expect(within(pat).getByText("Manual: you tailor it")).toBeInTheDocument();
    expect(within(pat).getByRole("button", { name: "Tailor manually: Pat Rivers" })).toBeInTheDocument();
    expect(within(rows[1]!).getByText("12 mutuals")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("LinkedIn draft ready · you send")).toBeInTheDocument();
    expect(within(rows[3]!).getByText("Email draft · verified address")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows the people-you-know banner with a link to Outreach settings", async () => {
    mockApi({ "GET /api/contacts": DATA });
    renderRoutes(routes, "/contacts");
    expect(await screen.findByText("No automated messages to people you know.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Outreach settings" })).toHaveAttribute("href", "/settings/outreach");
  });

  it("Find contacts is off with the reason; LinkedIn drafts open read-only", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /api/contacts": DATA });
    renderRoutes(routes, "/contacts");
    await screen.findByRole("table");
    const find = screen.getByRole("button", { name: "Find contacts" });
    expect(find).toHaveAttribute("aria-disabled", "true");
    expect(find).toHaveAccessibleDescription("Finding contacts runs from Claude Code for now: /find-contacts");
    await user.click(screen.getByRole("button", { name: "Open LinkedIn drafts (1)" }));
    const dialog = screen.getByRole("dialog", { name: "LinkedIn draft" });
    expect(within(dialog).getByText("To Riley Park")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /Approve/ })).toBeNull();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Open LinkedIn drafts (1)" })).toHaveFocus();
  });

  it("Mark connection writes through the API with the write header and offers Undo when it can", async () => {
    const user = userEvent.setup();
    const calls = mockApi({
      "GET /api/contacts": DATA,
      "POST /api/contacts/stark0000001/Sam%20Lee/mark": { job_id: "stark0000001", name: "Sam Lee", linkedin_degree: 1, mutuals: 12 },
    });
    renderRoutes(routes, "/contacts");
    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Mark connection for Sam Lee" }));
    const dialog = screen.getByRole("dialog", { name: "Mark connection" });
    await user.click(within(dialog).getByRole("radio", { name: "1st · connected" }));
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toEqual({ degree: 1 });
    expect(post.headers["X-CareerOS"]).toBe("1");
    expect(await screen.findByText("Saved what LinkedIn shows for Sam Lee.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(calls.filter((c) => c.method === "POST").at(-1)!.body).toEqual({ degree: 2 });
  });

  it("Mark connection validates mutuals and shows server errors", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /api/contacts": DATA,
      "POST /api/contacts/stark0000001/Pat%20Rivers/mark": () =>
        new Response(JSON.stringify({ detail: "no contact named 'Pat Rivers'" }), { status: 404 }),
    });
    renderRoutes(routes, "/contacts");
    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Mark connection for Pat Rivers" }));
    const dialog = screen.getByRole("dialog", { name: "Mark connection" });
    const input = within(dialog).getByRole("spinbutton", { name: "Mutual connections" });
    await user.type(input, "-2");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("whole number");
    expect(input).toHaveFocus();
    await user.clear(input);
    await user.type(input, "3");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("no contact named");
  });

  it("an email the candidate sends by hand is labelled email, not LinkedIn, and opens its draft", async () => {
    const d = draft({ contact: "Sam Lee", mode: "email_manual", kind: "status_followup" });
    mockApi({
      "GET /api/contacts": { ...DATA, items: [row({ name: "Sam Lee", mode: "email_manual", draft: d })], linkedin_drafts: 0 },
      "GET /api/meta": {},
    });
    renderRoutes(routes, "/contacts");
    const table = await screen.findByRole("table", { name: "Contacts at companies you applied to" });
    expect(within(table).getByText("Email draft · you send")).toBeInTheDocument();
    expect(within(table).queryByText(/LinkedIn draft/)).not.toBeInTheDocument();
  });

  it("empty state when no contacts exist yet", async () => {
    mockApi({
      "GET /api/contacts": { items: [], linkedin_drafts: 0, policy: { manual_if_connected: true, manual_if_mutuals: true } },
    });
    renderRoutes(routes, "/contacts");
    expect(await screen.findByRole("heading", { name: "No contacts yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open LinkedIn drafts (0)" })).toHaveAccessibleDescription(
      "No LinkedIn drafts yet",
    );
  });

  it("paging LinkedIn drafts keeps the sheet open and focus on the pager", async () => {
    const user = userEvent.setup();
    const three: ContactsResponse = {
      ...DATA,
      items: ["Riley Park", "Casey Moss", "Jamie Fox"].map((name) =>
        row({ name, linkedin_degree: 3, mode: "linkedin_draft", draft: linkedinDraft({ contact: name }) }),
      ),
      linkedin_drafts: 3,
    };
    mockApi({ "GET /api/contacts": three });
    renderRoutes(routes, "/contacts");
    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Open LinkedIn drafts (3)" }));
    const next = within(screen.getByRole("dialog")).getByRole("button", { name: "Next" });
    next.focus();
    await user.keyboard("{Enter}");
    const dialog = screen.getByRole("dialog", { name: "LinkedIn draft" });
    expect(within(dialog).getByText("To Casey Moss")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Next" })).toHaveFocus();
    expect(within(dialog).getAllByText("2 of 3")).toHaveLength(1);
    await user.keyboard("{Enter}");
    expect(screen.getByRole("dialog", { name: "LinkedIn draft" })).toBeInTheDocument();
    expect(within(screen.getByRole("dialog")).getByText("To Jamie Fox")).toBeInTheDocument();
    // Next is now disabled at the end; focus moves to Previous, still inside the dialog.
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Previous" })).toHaveFocus();
  });
});
