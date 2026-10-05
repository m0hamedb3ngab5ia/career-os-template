import { screen, within } from "@testing-library/react";
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
};

afterEach(() => vi.unstubAllGlobals());

describe("ProfilePage", () => {
  it("shows every section, the checklist and explains disabled controls", async () => {
    mockApi(BASE);
    const { container } = renderRoutes(routes, "/profile");
    expect(await screen.findByRole("heading", { name: "Before you apply: 1 must-have left" })).toBeInTheDocument();
    for (const h of ["Résumés", "Writing samples", "Saved answers", "Learned"]) expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
    expect(await screen.findByText("- short sentences")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fix" })).toHaveAttribute("href", "/profile#resumes");
    expect(screen.queryByRole("button", { name: "Make master" })).toBeNull();
    expect(screen.getByText("Master")).toBeInTheDocument();
    await screen.findByText("Workday needs a login");
    expect(unexplainedDisabled(container)).toEqual([]);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("edits and deletes a saved answer through the API", async () => {
    const calls = mockApi({ ...BASE, "PUT /api/profile/answers/why_us": {}, "DELETE /api/profile/answers/gender": {} });
    renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Edit why_us (Acme)" }));
    const box = screen.getByRole("textbox", { name: "Answer for why_us (Acme)" });
    await userEvent.clear(box);
    expect(screen.getByRole("button", { name: "Save" })).toHaveAccessibleDescription("Type an answer first");
    await userEvent.type(box, "Space.");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ answer: "Space.", company: "Acme", eeo: false });
    await userEvent.click(screen.getByRole("button", { name: "Delete gender" }));
    await userEvent.click(within(screen.getByRole("group", { name: "Delete gender?" })).getByRole("button", { name: "Yes, delete" }));
    expect(calls.find((c) => c.method === "DELETE")?.url).toBe("/api/profile/answers/gender?eeo=true");
  });

  it("removing a sample that can't re-learn shows a banner with Retry", async () => {
    const calls = mockApi({
      ...BASE,
      "DELETE /api/profile/samples/letter.md": { samples: [], learn_run: null, learn_error: "learn-voice not started: busy" },
      "POST /api/profile/samples/learn": { samples: [], learn_run: "r1", learn_error: null },
    });
    renderRoutes(routes, "/profile");
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
    await userEvent.upload(await screen.findByLabelText("Add samples"), files);
    expect(await screen.findByRole("alert")).toHaveTextContent("Voice update failed: timed out");
    const puts = calls.filter((c) => c.method === "PUT").map((c) => c.url);
    expect(puts).toEqual(["/api/profile/samples?learn=false&filename=a.md", "/api/profile/samples?learn=false&filename=b.txt"]);
    expect(calls.filter((c) => c.url === "/api/profile/samples/learn")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("an already running voice update is info, and a failed answer delete says so", async () => {
    mockApi({
      ...BASE,
      "POST /api/profile/samples/learn": { samples: [], learn_run: null, learn_error: null, learn_info: "voice update already running; new samples are used next run" },
      "PUT /api/profile/samples": {},
      "DELETE /api/profile/answers/relocate": new Response(JSON.stringify({ detail: "disk full" }), { status: 500 }),
    });
    renderRoutes(routes, "/profile");
    await userEvent.upload(await screen.findByLabelText("Add samples"), new File(["hi"], "c.md"));
    expect(await screen.findByText(/already running; new samples are used next run/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Delete relocate" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByText(/Couldn’t delete relocate: disk full/)).toBeInTheDocument();
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
    expect(await screen.findByRole("link", { name: "Fix" })).toHaveAttribute("href", "/profile#master");
    expect(await screen.findByLabelText("Proposed master.yaml changes")).toHaveTextContent("+name: new");
    expect(await axeViolations(container)).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Approve changes" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/profile/master/proposal/approve")).toBe(true);
    expect(await screen.findByText("In sync with your master résumé.")).toBeInTheDocument();
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
    await userEvent.click(await screen.findByRole("button", { name: "Reject" }));
    expect(await screen.findByText(/You rejected the last proposal/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve changes" })).toBeNull();
  });

  it("TASK-022: résumé feedback apply, comment and dismiss call the endpoints", async () => {
    const item = (id: string, state = "open") => ({ id, section: "Experience", issue: `Issue ${id}`, suggestion: "Add a number", state, comments: [] });
    const calls = mockApi({
      ...BASE,
      "GET /api/profile/resumes/cv/feedback": { review: { state: "done", run: "r1", v: 2, at: "2026-10-01" }, items: [item("f1"), item("f2", "applied")] },
      "POST /api/profile/resumes/cv/feedback/f1/apply": { kind: "resume_edit", run_id: "r2" },
      "GET /api/runs/r2": { id: "r2", state: "running" },
      "POST /api/profile/resumes/cv/feedback/f1/comment": { kind: "resume_edit", run_id: "r3" },
      "POST /api/profile/resumes/cv/feedback/f1/dismiss": item("f1", "dismissed"),
    });
    const { container } = renderRoutes(routes, "/profile");
    await userEvent.click(await screen.findByText("Feedback: 1 open of 2"));
    expect(container).toHaveTextContent("Experience · Issue f2");
    expect(unexplainedDisabled(container)).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Comment on Experience" }), "Use 12 services");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    const posts = calls.filter((c) => c.method === "POST").map((c) => c.url);
    expect(posts).toEqual(["/api/profile/resumes/cv/feedback/f1/apply", "/api/profile/resumes/cv/feedback/f1/comment", "/api/profile/resumes/cv/feedback/f1/dismiss"]);
    expect(calls.find((c) => c.url.endsWith("/comment"))?.body).toEqual({ text: "Use 12 services" });
    expect(await axeViolations(container)).toEqual([]);
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
    await userEvent.click(await screen.findByText("Feedback: 1 open of 1"));
    expect(screen.getByText(/keep it short/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("button", { name: "Applying…" })).toBeDisabled();
    done = true;
    expect(await screen.findByText(/Not applied: résumé changed since v2/, {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled();
  });

  it("TASK-022 review: stale master with no running extract-master offers Re-read", async () => {
    const calls = mockApi({
      ...BASE,
      "GET /api/profile/master/proposal": { state: "stale", diff: "" },
      "GET /api/runs": { runs: [{ id: "x1", kind: "extract_master", state: "failed" }], next_cursor: null },
      "POST /api/profile/master/proposal/refresh": { kind: "extract_master", run_id: "x2" },
    });
    renderRoutes(routes, "/profile");
    expect(await screen.findByText(/Couldn’t read your master résumé/)).toBeInTheDocument();
    expect(screen.queryByText(/Reading your master résumé/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Re-read" }));
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/profile/master/proposal/refresh")).toBe(true);
  });
});
