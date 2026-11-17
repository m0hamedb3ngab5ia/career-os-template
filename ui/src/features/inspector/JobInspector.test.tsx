import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { defaultRoutes, json, mockApi, renderWithApp } from "../today/testing";
import { JobInspector } from "./JobInspector";

afterEach(() => vi.unstubAllGlobals());

const detail = (over: Record<string, unknown> = {}) => ({
  job: { job_id: "j1", company: "Acme Robotics", title: "Platform Engineer", url: "https://jobs.example.com/acme/1", fit: 82,
    status: "needs_review", found_at: "2026-11-10T09:00:00Z" },
  posting: { posted_at: "2026-11-01T00:00:00Z" }, status: "needs_review",
  qa: { pass: false, fail_reasons: ["relevance: weak summary"] },
  documents: [{ name: "resume.txt", size: 1, modified: 0 }, { name: "resume.pdf", size: 1, modified: 0 }, { name: "cover_letter.md", size: 1, modified: 0 }],
  ...over,
});

function setup(d = detail()) {
  const calls = mockApi({
    ...defaultRoutes(),
    "GET /api/jobs/j1": d,
    "GET /api/jobs/j1/files/resume.txt": () => new Response("RESUME BODY"),
    "GET /api/jobs/j1/files/cover_letter.md": () => new Response("DEAR TEAM"),
    "POST /api/jobs/j1/status": json({ job_id: "j1" }),
    "POST /api/jobs/select": json({ ids: ["j1"], selected: true }),
  });
  renderWithApp(<JobInspector />, { path: "/?job=j1" });
  return calls;
}

describe("JobInspector", () => {
  it("renders nothing without ?job=", () => {
    mockApi(defaultRoutes());
    renderWithApp(<JobInspector />, { path: "/" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows dates, fit, progress, QA reasons, résumé and letter text", async () => {
    setup();
    const panel = await screen.findByRole("dialog", { name: "Loading…" });
    expect(await within(panel).findByText("Platform Engineer")).toBeInTheDocument();
    expect(within(panel).getByText("Nov 1")).toBeInTheDocument();
    expect(within(panel).getByText("Nov 10")).toBeInTheDocument();
    expect(within(panel).getByText("82%")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "Open the posting" })).toHaveAttribute("target", "_blank");
    expect(within(panel).getAllByRole("listitem").map((li) => li.textContent).slice(0, 5)).toEqual([
      "Scored", "Drafted", "Quality check (didn’t pass)", "Ready", "Applied"]);
    expect(within(panel).getByText("relevance: weak summary")).toBeInTheDocument();
    expect(await within(panel).findByText("RESUME BODY")).toBeInTheDocument();
    expect(await within(panel).findByText("DEAR TEAM")).toBeInTheDocument();
  });

  it("offers no Approve when the quality check failed", async () => {
    setup();
    await screen.findByText("Platform Engineer");
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skip" })).toBeInTheDocument();
  });

  it("says who submits, from the pipeline state", async () => {
    const pipe = (over: object) => ({ auto_submit: false, note: null, ...over });
    for (const [state, text] of [
      [pipe({ auto_submit: false }), "You’ll submit it yourself."],
      [pipe({ auto_submit: true }), "The next apply run may submit it automatically (auto-submit is on for this tier)."],
      [pipe({ auto_submit: true, note: "Tier A: the run fills and stages the form; you review and submit." }), "You’ll submit it yourself."],
    ] as const) {
      const calls = mockApi({ ...defaultRoutes(), "GET /api/jobs/j1": detail({ qa: { pass: true } }), "GET /api/jobs/j1/pipeline": state });
      void calls;
      const { unmount } = renderWithApp(<JobInspector />, { path: "/?job=j1" });
      expect(await screen.findByText(text)).toBeInTheDocument();
      unmount();
    }
  });

  it("never promises auto-submit for a Tier A job", async () => {
    const base = detail({ qa: { pass: true } });
    mockApi({ ...defaultRoutes(), "GET /api/jobs/j1": { ...base, job: { ...base.job, tier: "A" } }, "GET /api/jobs/j1/pipeline": { auto_submit: true, note: null } });
    renderWithApp(<JobInspector />, { path: "/?job=j1" });
    expect(await screen.findByText("You’ll submit it yourself.")).toBeInTheDocument();
  });

  it("uses a neutral note until the pipeline state loads", async () => {
    setup(detail({ qa: { pass: true } }));
    expect(await screen.findByText("Approve marks it ready for the next apply run.")).toBeInTheDocument();
  });

  it("Approve marks it queued and ticked, never submits", async () => {
    const calls = setup(detail({ qa: { pass: true } }));
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/jobs/select")).toBe(true));
    const status = calls.find((c) => c.path === "/api/jobs/j1/status")!;
    expect(status.body).toMatchObject({ status: "queued" });
    expect(calls.some((c) => /apply/.test(c.path))).toBe(false);
  });

  it("Skip sets status skipped", async () => {
    const calls = setup();
    await userEvent.click(await screen.findByRole("button", { name: "Skip" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/jobs/j1/status")).toBe(true));
    expect(calls.find((c) => c.path === "/api/jobs/j1/status")!.body).toMatchObject({ status: "skipped" });
  });

  it("offers no actions once applied", async () => {
    setup(detail({ status: "applied", job: { ...detail().job, status: "applied" } }));
    await screen.findByText("Platform Engineer");
    expect(screen.queryByRole("button", { name: "Skip" })).not.toBeInTheDocument();
  });
});

describe("JobInspector outreach", () => {
  const outreach = {
    drafts: [{ contact: "Jane Doe", role: "recruiter", linkedin_note: "Hi Jane, I applied to the Platform role.",
      linkedin_message: "Longer LinkedIn message.", email: { subject: "Platform Engineer applicant", body: "Hello Jane,\nI applied." } }],
  };
  const contacts = { contacts: [], search_urls: { recruiter: "https://www.linkedin.com/search/results/people/?keywords=Acme%20recruiter" } };
  const withOutreach = () => detail({ other_files: [{ name: "outreach.json", size: 1, modified: 0 }, { name: "contacts.json", size: 1, modified: 0 }] });
  const routes = {
    "GET /api/jobs/j1/files/outreach.json": () => new Response(JSON.stringify(outreach)),
    "GET /api/jobs/j1/files/contacts.json": () => new Response(JSON.stringify(contacts)),
  };

  it("shows the drafted messages with Copy buttons, and never sends", async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: write }, configurable: true });
    const calls = mockApi({ ...defaultRoutes(), "GET /api/jobs/j1": withOutreach(), ...routes });
    renderWithApp(<JobInspector />, { path: "/?job=j1" });
    const sec = await screen.findByRole("region", { name: "Reach out" });
    expect(await within(sec).findByText(/Hello Jane,/)).toBeInTheDocument();
    expect(within(sec).getByText("Platform Engineer applicant")).toBeInTheDocument();
    expect(within(sec).getByText("Hi Jane, I applied to the Platform role.")).toBeInTheDocument();
    expect(within(sec).getByText(/You send these yourself/)).toBeInTheDocument();
    await userEvent.click(within(sec).getByRole("button", { name: "Copy email" }));
    expect(write).toHaveBeenCalledWith("Subject: Platform Engineer applicant\n\nHello Jane,\nI applied.");
    expect(await within(sec).findByText("Copied")).toBeInTheDocument();
    const li = within(sec).getByRole("link", { name: "Search LinkedIn" });
    expect(li).toHaveAttribute("target", "_blank");
    expect(calls.some((c) => c.method !== "GET" && /outreach|send/.test(c.path))).toBe(false);
  });

  it("has no Reach out block without outreach or contacts files", async () => {
    setup();
    await screen.findByText("RESUME BODY");
    expect(screen.queryByRole("region", { name: "Reach out" })).not.toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    mockApi({ ...defaultRoutes(), "GET /api/jobs/j1": withOutreach(), ...routes });
    renderWithApp(<JobInspector />, { path: "/?job=j1" });
    await screen.findByText(/Hello Jane,/);
    expect(await axeViolations(screen.getByRole("dialog"))).toEqual([]);
  });
});
