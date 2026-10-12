import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { unexplainedDisabled } from "../../test/disabled";
import { mockApi, renderRoutes } from "../../test/mockApi";
import { ProfilePage } from "./ProfilePage";

const routes = [{ path: "/profile", element: <ProfilePage /> }];
const READY = {
  ready: false,
  items: [
    { id: "master_resume", label: "Master résumé set", must: true, done: false, fix_link: "/profile#resumes" },
    { id: "writing_sample", label: "At least one writing sample", must: false, done: true, fix_link: "/profile#samples" },
  ],
};
const BASE = {
  "GET /api/readiness": READY,
  "GET /api/profile/resumes": { resumes: [{ rid: "cv", name: "cv.pdf", type: "master", category: null, latest: 2, at: "2026-10-01" }] },
  "GET /api/profile/samples": { samples: [{ name: "letter.md", size: 9 }], learned: "- short sentences" },
  "GET /api/profile/answers": {
    answers: [
      { scope: "general", key: "relocate", company: null, answer: "Yes", match: [], note: null },
      { scope: "company", key: "why_us", company: "Acme", answer: "Rockets.", match: [], note: null },
      { scope: "eeo", key: "gender", company: null, answer: "Decline", match: [], note: null },
    ],
  },
  "GET /api/learning/lessons": { lessons: [{ id: "abc12345", text: "Workday needs a login", ats: "workday", company: null, job_id: null, added: null, tags: [] }] },
  "GET /api/profile/master/proposal": { state: "synced", diff: "" },
  "GET /api/profile/resumes/cv/feedback": { review: null, items: [] },
  "GET /api/profile/resumes/cv/versions/2": { rid: "cv", n: 2, text: "Experience\n- Supported migration of 12 services\n", ats: {} },
};

afterEach(() => vi.unstubAllGlobals());

describe("ProfilePage", () => {
  it("shows every section, the checklist and explains disabled controls", async () => {
    mockApi(BASE);
    const { container } = renderRoutes(routes, "/profile");
    expect(await screen.findByText("1 setup item remaining")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(await screen.findByRole("heading", { name: "Before you apply: 1 must-have left" })).toBeInTheDocument();
    for (const h of ["Résumés", "Writing style", "Application answers"]) expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Lessons" })).toBeNull();
    expect(screen.getByText("1 sample")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fix it" })).toHaveAttribute("href", "/profile#resumes");
    expect(screen.queryByRole("menuitem", { name: "Make master" })).toBeNull();
    expect(screen.getByText("Master résumé")).toBeInTheDocument();
    expect(unexplainedDisabled(container)).toEqual([]);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("summarises answers by group with a Manage answers link", async () => {
    mockApi(BASE);
    renderRoutes(routes, "/profile");
    expect(await screen.findByText("Job preferences · 1")).toBeInTheDocument();
    expect(screen.getByText("Company-specific · 1")).toBeInTheDocument();
    expect(screen.getByText("EEO (voluntary) · 1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage answers" })).toHaveAttribute("href", "/profile/answers");
  });

  it("removing a sample that can't re-learn shows a banner with Retry", async () => {
    const calls = mockApi({
      ...BASE,
      "DELETE /api/profile/samples/letter.md": { samples: [], learn_run: null, learn_error: "learn-voice not started: busy" },
      "POST /api/profile/samples/learn": { samples: [], learn_run: "r1", learn_error: null },
    });
    renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Manage samples" }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete letter.md" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("learn-voice not started: busy");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/profile/samples/learn")).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("uploads several samples in one action, learns once and shows a failed run with Retry", async () => {
    const calls = mockApi({
      ...BASE,
      "PUT /api/profile/samples": { samples: [], learn_run: null, learn_error: null, learn_info: null },
      "POST /api/profile/samples/learn": { samples: [], learn_run: "r9", learn_error: null, learn_info: null },
      "GET /api/runs/r9": { id: "r9", kind: "learn_voice", state: "done", status: "done", stop_reason: "timeout", detail: "timed out", log: "", attempts: [], started_at: null, ended_at: null },
    });
    renderRoutes(routes, "/profile");
    const files = ["a.md", "b.txt"].map((n) => new File(["hi"], n, { type: "text/plain" }));
    await userEvent.click(await screen.findByRole("button", { name: "Manage samples" }));
    await userEvent.upload(await screen.findByLabelText("Add samples"), files);
    expect(await screen.findByRole("alert")).toHaveTextContent("Voice update failed: timed out");
    const puts = calls.filter((c) => c.method === "PUT").map((c) => c.url);
    expect(puts).toEqual(["/api/profile/samples?learn=false&filename=a.md", "/api/profile/samples?learn=false&filename=b.txt"]);
    expect(calls.filter((c) => c.url === "/api/profile/samples/learn")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("an already running voice update is info", async () => {
    mockApi({
      ...BASE,
      "POST /api/profile/samples/learn": { samples: [], learn_run: null, learn_error: null, learn_info: "voice update already running; new samples are used next run" },
      "PUT /api/profile/samples": {},
    });
    renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Manage samples" }));
    await userEvent.upload(await screen.findByLabelText("Add samples"), new File(["hi"], "c.md"));
    expect(await screen.findByText(/already running; new samples are used next run/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("failed loads offer Try again", async () => {
    mockApi({ ...BASE, "GET /api/readiness": new Response("{}", { status: 500 }) });
    renderRoutes(routes, "/profile");
    expect(await screen.findByText(/Couldn’t check your setup/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("TASK-022: approves the master.yaml diff; readiness links to the panel and refreshes", async () => {
    let synced = false;
    const unsynced = { ...READY, items: [{ id: "master_synced", label: "master.yaml synced with the master résumé", must: true, done: false, fix_link: "/profile#master" }] };
    const calls = mockApi({
      ...BASE,
      "GET /api/readiness": () => (synced ? { ready: true, items: [{ ...unsynced.items[0], done: true }] } : unsynced),
      "GET /api/profile/master/proposal": () => (synced ? { state: "synced", diff: "" } : { state: "pending", diff: "--- a\n+++ b\n-name: old\n+name: new\n" }),
      "POST /api/profile/master/proposal/approve": () => { synced = true; return { state: "synced", diff: "" }; },
    });
    const { container } = renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect(await screen.findByRole("link", { name: "Fix it" })).toHaveAttribute("href", "/profile#master");
    expect(await screen.findByText("CareerOS read new details from this version")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Review new details" }));
    expect(await screen.findByLabelText("Proposed profile fact changes")).toHaveTextContent("+name: new");
    expect(await axeViolations(container)).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Approve changes" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/profile/master/proposal/approve")).toBe(true);
    await vi.waitFor(() => expect(screen.queryByText("CareerOS read new details from this version")).toBeNull());
    expect(await screen.findByRole("heading", { name: "Ready to apply" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve changes" })).toBeNull();
  });

  it("TASK-022: reject keeps master.yaml and says so", async () => {
    let rejected = false;
    mockApi({
      ...BASE,
      "GET /api/profile/master/proposal": () => ({ state: rejected ? "rejected" : "pending", diff: "+x: 1\n" }),
      "POST /api/profile/master/proposal/reject": () => { rejected = true; return { state: "rejected", diff: "+x: 1\n" }; },
    });
    renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Review new details" }));
    await userEvent.click(await screen.findByRole("button", { name: "Reject" }));
    expect(await screen.findByText(/You rejected the last proposal/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve changes" })).toBeNull();
  });

  it("TASK-022: résumé feedback apply, comment and dismiss call the endpoints", async () => {
    const item = (id: string, state = "open") => ({ id, section: "Experience", issue: `Issue ${id}`, suggestion: "Add a number", state, comments: [],
      quote: "Supported migration of 12 services" });
    const calls = mockApi({
      ...BASE,
      "GET /api/profile/resumes/cv/feedback": { review: { state: "done", run: "r1", v: 2, at: "2026-10-01" }, items: [item("f1"), item("f2", "applied")] },
      "POST /api/profile/resumes/cv/feedback/f1/apply": { kind: "resume_edit", run_id: "r2" },
      "GET /api/runs/r2": { id: "r2", state: "running" },
      "POST /api/profile/resumes/cv/feedback/f1/comment": { kind: "resume_edit", run_id: "r3" },
      "POST /api/profile/resumes/cv/feedback/f1/dismiss": item("f1", "dismissed"),
    });
    const { container } = renderRoutes(routes, "/profile");
    expect(await screen.findByText(/1 suggestion to review/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Review suggestions" }));
    const dialog = screen.getByRole("dialog", { name: "Résumé review" });
    expect(dialog).toHaveTextContent("CareerOS found 2 possible improvements");
    expect(dialog).toHaveTextContent("Suggestion 1 of 2");
    expect(dialog).toHaveTextContent("Experience: Issue f1");
    expect(within(dialog).queryByLabelText("Résumé text")).toBeNull(); // only the passage, not the full text
    const mark = await within(dialog).findByText((_, el) => el?.tagName === "MARK");
    expect(mark).toHaveTextContent("Supported migration of 12 services");
    expect(mark.parentElement?.textContent).toBe("Experience\n- Supported migration of 12 services"); // neighbouring line kept
    expect(unexplainedDisabled(dialog)).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Suggest different wording" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Comment on Experience" }), "Use 12 services");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await userEvent.click(screen.getByRole("button", { name: "Ignore" }));
    expect(await screen.findByText("Suggestion 2 of 2")).toBeInTheDocument(); // Ignore -> next item
    expect(screen.getByRole("dialog", { name: "Résumé review" })).toHaveTextContent(/Applied/);
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    await userEvent.click(await screen.findByRole("button", { name: "Accept" }));
    expect(await screen.findByText("Suggestion 2 of 2")).toBeInTheDocument(); // Accept -> next item
    const posts = calls.filter((c) => c.method === "POST").map((c) => c.url);
    expect(posts).toEqual(["/api/profile/resumes/cv/feedback/f1/comment", "/api/profile/resumes/cv/feedback/f1/dismiss", "/api/profile/resumes/cv/feedback/f1/apply"]);
    expect(calls.find((c) => c.url.endsWith("/comment"))?.body).toEqual({ text: "Use 12 services" });
    expect(await axeViolations(container)).toEqual([]);
  });

  it("review: a format item has How to fix + Mark as fixed (dismiss), no Accept; no quote = whole résumé", async () => {
    const calls = mockApi({
      ...BASE,
      "GET /api/profile/resumes/cv/feedback": { review: { state: "done", run: "r1", v: 2, at: "2026-10-01" },
        items: [{ id: "f1", section: "Layout", issue: "Broken words", suggestion: "Export with embedded fonts", kind: "format", whole: true, state: "open", comments: [], v: 2 }] },
      "POST /api/profile/resumes/cv/feedback/f1/dismiss": { id: "f1", state: "dismissed" },
    });
    renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Review suggestions" }));
    const dialog = screen.getByRole("dialog", { name: "Résumé review" });
    expect(dialog).toHaveTextContent("How to fix");
    expect(dialog).toHaveTextContent("This affects the whole résumé, not one line.");
    expect(within(dialog).queryByRole("button", { name: "Accept" })).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Mark as fixed" }));
    expect(calls.filter((c) => c.method === "POST").map((c) => c.url)).toEqual(["/api/profile/resumes/cv/feedback/f1/dismiss"]);
  });

  it("TASK-022 review: Apply follows its run, then shows the item's outcome (reason)", async () => {
    let done = false;
    const item = { id: "f1", section: "Experience", issue: "Vague", suggestion: "Add a number", state: "open", comments: [{ text: "keep it short" }], v: 2 };
    mockApi({
      ...BASE,
      "GET /api/profile/resumes/cv/feedback": () => ({ review: { state: "done", run: "r1", v: 2, at: "2026-10-01" },
        items: [done ? { ...item, reason: "résumé changed since v2" } : item] }),
      "POST /api/profile/resumes/cv/feedback/f1/apply": { kind: "resume_edit", run_id: "r2" },
      "GET /api/runs/r2": () => ({ id: "r2", state: done ? "done" : "running" }),
    });
    renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Review suggestions" }));
    expect(screen.getByText(/keep it short/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(await screen.findByRole("button", { name: "Applying…" })).toBeDisabled();
    done = true;
    expect(await screen.findByText(/Not applied: résumé changed since v2/, {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeEnabled();
  });

  it("review: Accept while another apply runs waits, then starts when it ends; Before vs Suggested change", async () => {
    let done = false;
    const item = (id: string) => ({ id, section: "Experience", issue: `Issue ${id}`, suggestion: `Say ${id}`, quote: "Supported migration", state: "open", comments: [], v: 2 });
    const calls = mockApi({
      ...BASE,
      "GET /api/profile/resumes/cv/feedback": { review: { state: "done", run: "r1", v: 2, at: "2026-10-01" }, items: [item("f1"), item("f2")] },
      "POST /api/profile/resumes/cv/feedback/f1/apply": { kind: "resume_edit", run_id: "r2" },
      "POST /api/profile/resumes/cv/feedback/f2/apply": { kind: "resume_edit", run_id: "r3" },
      "GET /api/runs/r2": () => ({ id: "r2", state: done ? "done" : "running" }),
      "GET /api/runs/r3": { id: "r3", state: "running" },
    });
    renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Review suggestions" }));
    const dialog = screen.getByRole("dialog", { name: "Résumé review" });
    expect(within(dialog).getByRole("heading", { name: "Before" })).toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: "Suggested change" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(await screen.findByText("Suggestion 2 of 2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(await screen.findByRole("button", { name: "Waiting…" })).toBeDisabled();
    expect(dialog).not.toHaveTextContent(/another run|pid/);
    const applies = () => calls.filter((c) => c.method === "POST").map((c) => c.url);
    expect(applies()).toEqual(["/api/profile/resumes/cv/feedback/f1/apply"]);
    done = true;
    expect(await screen.findByRole("button", { name: "Applying…" }, { timeout: 3000 })).toBeDisabled();
    expect(applies()).toEqual(["/api/profile/resumes/cv/feedback/f1/apply", "/api/profile/resumes/cv/feedback/f2/apply"]);
  });

  it("review: Before shows the first 2 quoted lines, See more / Collapse; no quote + not whole = retry hint", async () => {
    const base = { section: "Experience", issue: "Opens with Member of", suggestion: "Lead with the outcome", state: "open", comments: [], v: 2 };
    const calls = mockApi({
      ...BASE,
      "GET /api/profile/resumes/cv/feedback": { review: { state: "done", run: "r1", v: 2, at: "2026-10-01" },
        items: [{ ...base, id: "f1", quotes: ["Line A", "Line B", "Line C"] }, { ...base, id: "f2" }] },
      "POST /api/profile/resumes/cv/feedback/f1/dismiss": { ...base, id: "f1", state: "dismissed" },
      "POST /api/profile/resumes/cv/review": { run_id: "r2" },
    });
    renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Review suggestions" }));
    const dialog = screen.getByRole("dialog", { name: "Résumé review" });
    expect(dialog).toHaveTextContent("Line A");
    expect(dialog).toHaveTextContent("Line B");
    expect(dialog).not.toHaveTextContent("Line C");
    await userEvent.click(within(dialog).getByRole("button", { name: "See more (1)" }));
    expect(dialog).toHaveTextContent("Line C");
    await userEvent.click(within(dialog).getByRole("button", { name: "Collapse" }));
    expect(dialog).not.toHaveTextContent("Line C");
    await userEvent.click(within(dialog).getByRole("button", { name: "Ignore" }));
    expect(await screen.findByText("Suggestion 2 of 2")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("Review again to see the exact lines.");
    expect(dialog).not.toHaveTextContent("whole résumé");
    await userEvent.click(within(dialog).getByRole("button", { name: "Review again" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/profile/resumes/cv/review")).toBe(true);
  });

  it("one failure state: failed review + failed read show one message and one Retry that runs both", async () => {
    const calls = mockApi({
      ...BASE,
      "GET /api/profile/resumes/cv/feedback": { review: { state: "failed", run: null, v: 1, at: "2026-10-01" }, items: [] },
      "GET /api/profile/master/proposal": { state: "stale", diff: "" },
      "GET /api/runs": { runs: [{ id: "x1", kind: "extract_master", state: "failed" }], next_cursor: null },
      "POST /api/profile/master/proposal/refresh": { kind: "extract_master", run_id: "x2" },
      "POST /api/profile/resumes/cv/review": { kind: "review", run_id: "r9" },
    });
    renderRoutes(routes, "/profile");
    await screen.findAllByText(/We couldn’t process this résumé/);
    await waitFor(() => expect(calls.filter((c) => c.url.startsWith("/api/runs"))).toHaveLength(1));
    await new Promise((r) => setTimeout(r, 50)); // let the master read state settle
    expect(screen.getAllByText(/We couldn’t process this résumé/)).toHaveLength(1);
    expect(screen.queryByText(/Retry review|Re-read|review failed/i)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST").map((c) => c.url).sort()).toEqual(
      ["/api/profile/master/proposal/refresh", "/api/profile/resumes/cv/review"]));
  });
  it("TASK-022 review: stale master with no running extract-master offers one Retry", async () => {
    const calls = mockApi({
      ...BASE,
      "GET /api/profile/master/proposal": { state: "stale", diff: "" },
      "GET /api/runs": { runs: [{ id: "x1", kind: "extract_master", state: "failed" }], next_cursor: null },
      "POST /api/profile/master/proposal/refresh": { kind: "extract_master", run_id: "x2" },
    });
    renderRoutes(routes, "/profile");
    expect(await screen.findByText(/We couldn’t process this résumé/)).toBeInTheDocument();
    expect(screen.queryByText(/Reading your master résumé/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/profile/master/proposal/refresh")).toBe(true);
  });
});
