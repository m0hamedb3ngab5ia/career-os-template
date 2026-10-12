import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { type Call, mockApi, renderRoutes } from "../../test/mockApi";
import { WorkspacePage } from "./WorkspacePage";

const routes = [
  { path: "/resumes/:rid", element: <WorkspacePage /> },
  { path: "/profile", element: <p>Profile page</p> },
  { path: "/profile/answers", element: <p>Answers page</p> },
];
const DOC = {
  schema_version: 1,
  identity: { name: "Alex Example", email: "alex@example.com" },
  summary: "Backend engineer",
  sections: [{ id: "sec-experience", type: "experience", order: 1 }],
  experience: [{ id: "experience-1", company: "Initech", title: "Intern", bullets: [
    { id: "experience-1.b1", text: "Worked on billing" },
    { id: "experience-1.b2", text: "Wrote docs" },
  ] }],
};
const SUGG = { id: "a1", kind: "suggestion", author: "ai", status: "open", target_id: "experience-1.b1",
  base: "Worked on billing", proposed: "Fixed billing export bugs", text: "Shows impact", replies: [], at: null };
const COMM = { id: "a2", kind: "comment", author: "ai", status: "open", target_id: "summary", base: "Backend engineer",
  proposed: null, text: "Name the stack", replies: [{ text: "Which one?", author: "user", at: null }], at: null };
const META = { rid: "cv", name: "cv.pdf", type: "master", category: null, versions: [] };

function api(extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/profile/resumes/cv": META,
    "GET /api/profile/resumes/cv/draft": { rev: 3, resume: DOC, draft: true },
    "GET /api/profile/resumes/cv/annotations": [COMM, SUGG, { ...SUGG, id: "a3", status: "rejected" }],
    "PUT /api/profile/resumes/cv/draft": (c: Call) => ({ rev: (c.body as { rev: number }).rev + 1, resume: (c.body as { resume: unknown }).resume, draft: true }),
    ...extra,
  });
}
const puts = (calls: Call[]) => calls.filter((c) => c.method === "PUT");
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => vi.useRealTimers());

describe("WorkspacePage", () => {
  it("renders the draft with inline suggestions and one margin card per open annotation, in document order", async () => {
    api();
    const { container } = renderRoutes(routes, "/resumes/cv");
    expect(await screen.findByRole("textbox", { name: "Summary" })).toHaveValue("Backend engineer");
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Alex Example");
    expect(screen.getByRole("textbox", { name: "Experience 1 company" })).toHaveValue("Initech");
    expect(screen.getByRole("textbox", { name: "Experience 1 bullet 2" })).toHaveValue("Wrote docs");
    const inline = container.querySelector("#t-experience-1\\.b1")!;
    expect(inline.querySelector("del")).toHaveTextContent("Worked on billing");
    expect(inline.querySelector("ins")).toHaveTextContent("Fixed billing export bugs");
    const cards = within(screen.getByRole("complementary", { name: "Suggestions" })).getAllByRole("article");
    expect(cards.map((c) => c.getAttribute("data-for"))).toEqual(["summary", "experience-1.b1"]);  // rejected a3 hidden
    expect(cards[0]).toHaveTextContent("Name the stack");
    expect(cards[0]).toHaveTextContent("You: Which one?");
    expect(screen.getByText("All changes saved")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("debounces edits into one PUT with the current rev, then shows saved", async () => {
    const calls = api();
    renderRoutes(routes, "/resumes/cv");
    const b2 = await screen.findByRole("textbox", { name: "Experience 1 bullet 2" });
    fireEvent.change(b2, { target: { value: "Wrote onboarding docs" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Summary" }), { target: { value: "Backend engineer (Python)" } });
    expect(screen.getByText("Saving…")).toBeInTheDocument();
    await tick(300);
    expect(puts(calls)).toHaveLength(0);
    await tick(500);
    expect(puts(calls)).toHaveLength(1);
    const body = puts(calls)[0]!.body as { rev: number; author: string; resume: typeof DOC };
    expect(body.rev).toBe(3);
    expect(body.author).toBe("user");
    expect(body.resume.summary).toBe("Backend engineer (Python)");
    expect(body.resume.experience[0]!.bullets[1]!.text).toBe("Wrote onboarding docs");
    expect(await screen.findByText("All changes saved")).toBeInTheDocument();
    fireEvent.change(b2, { target: { value: "Wrote docs again" } });
    await tick(800);
    expect((puts(calls)[1]!.body as { rev: number }).rev).toBe(4);  // next save uses the rev the server returned
  });

  it("flushes a pending edit on in-app navigation and on pagehide (keepalive)", async () => {
    const calls = api();
    const { router } = renderRoutes(routes, "/resumes/cv");
    fireEvent.change(await screen.findByRole("textbox", { name: "Summary" }), { target: { value: "A" } });
    window.dispatchEvent(new Event("pagehide"));
    expect(puts(calls)).toHaveLength(1);
    expect(vi.mocked(fetch).mock.calls.at(-1)![1]).toMatchObject({ keepalive: true, headers: { "X-CareerOS": "1" } });
    await tick(0);
    fireEvent.change(screen.getByRole("textbox", { name: "Summary" }), { target: { value: "B" } });
    await act(() => router.navigate("/profile"));
    expect(puts(calls)).toHaveLength(2);
    expect((puts(calls)[1]!.body as { resume: typeof DOC }).resume.summary).toBe("B");
  });

  it("shows a save error with Retry instead of losing the edit", async () => {
    let fail = true;
    const calls = api({ "PUT /api/profile/resumes/cv/draft": (c: Call) => fail
      ? new Response(JSON.stringify({ detail: "disk full" }), { status: 500 })
      : { rev: 4, resume: (c.body as { resume: unknown }).resume, draft: true } });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.change(await screen.findByRole("textbox", { name: "Summary" }), { target: { value: "X" } });
    await tick(800);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn’t save: disk full");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(await screen.findByText("All changes saved")).toBeInTheDocument();
    expect(puts(calls).map((c) => (c.body as { resume: typeof DOC }).resume.summary)).toEqual(["X", "X"]);
  });

  it("accepts, rejects and replies (Apply comment) on cards", async () => {
    const accepted = { ...DOC, experience: [{ ...DOC.experience[0], bullets: [{ id: "experience-1.b1", text: "Fixed billing export bugs" }, DOC.experience[0]!.bullets[1]!] }] };
    const calls = api({
      "POST /api/profile/resumes/cv/annotations/a1/accept": { rev: 4, resume: accepted, draft: true },
      "POST /api/profile/resumes/cv/annotations/a2/reject": { ...COMM, status: "rejected" },
      "POST /api/profile/resumes/cv/annotations/a2/replies": { ...COMM, run_id: "r1" },
    });
    renderRoutes(routes, "/resumes/cv");
    const card = await screen.findByRole("article", { name: /Shows impact/ });
    fireEvent.click(within(card).getByRole("button", { name: "Accept" }));
    expect(await screen.findByRole("textbox", { name: "Experience 1 bullet 1" })).toHaveValue("Fixed billing export bugs");
    const comment = screen.getByRole("article", { name: /Name the stack/ });
    fireEvent.change(within(comment).getByRole("textbox", { name: "Reply" }), { target: { value: "Use Python" } });
    fireEvent.click(within(comment).getByRole("checkbox", { name: /Apply comment/ }));
    fireEvent.click(within(comment).getByRole("button", { name: "Send" }));
    await tick(0);
    fireEvent.click(within(comment).getByRole("button", { name: "Resolve" }));
    await tick(0);
    const posts = calls.filter((c) => c.method === "POST");
    expect(posts.map((c) => c.url.replace("/api/profile/resumes/cv/annotations/", ""))).toEqual(["a1/accept", "a2/replies", "a2/reject"]);
    expect(posts[1]!.body).toEqual({ text: "Use Python", apply: true });
    // the accepted draft's rev is the base for the next autosave
    fireEvent.change(screen.getByRole("textbox", { name: "Summary" }), { target: { value: "Y" } });
    await tick(800);
    expect((puts(calls)[0]!.body as { rev: number }).rev).toBe(4);
  });

  it("keeps skills groups as string[] when edited", async () => {
    const calls = api({ "GET /api/profile/resumes/cv/draft": { rev: 3, resume: { ...DOC, sections: [{ id: "s", type: "skills", order: 1 }], skills: { languages: ["Python", "Go"] } }, draft: true } });
    renderRoutes(routes, "/resumes/cv");
    const box = await screen.findByRole("textbox", { name: "Skills languages" });
    expect(box).toHaveValue("Python, Go");
    fireEvent.change(box, { target: { value: "Python, Go, Rust, " } });
    expect(box).toHaveValue("Python, Go, Rust, ");
    await tick(800);
    expect((puts(calls)[0]!.body as { resume: { skills: unknown } }).resume.skills).toEqual({ languages: ["Python", "Go", "Rust"] });
  });

  it("sends a reply once even when Enter is pressed twice while pending", async () => {
    const calls = api({ "POST /api/profile/resumes/cv/annotations/a2/replies": () => new Promise(() => {}) });  // never answers: stays pending
    renderRoutes(routes, "/resumes/cv");
    const comment = await screen.findByRole("article", { name: /Name the stack/ });
    fireEvent.change(within(comment).getByRole("textbox", { name: "Reply" }), { target: { value: "Use Python" } });
    const form = within(comment).getByRole("textbox", { name: "Reply" }).closest("form")!;
    fireEvent.submit(form);
    await tick(0);
    fireEvent.submit(form);
    await tick(0);
    expect(calls.filter((c) => c.url.endsWith("/replies"))).toHaveLength(1);
  });

  it("Done flushes edits, then publishes; a retry reuses the idempotency key", async () => {
    let fail = true;
    const calls = api({ "POST /api/profile/resumes/cv/publish": () => fail
      ? new Response(JSON.stringify({ detail: "busy" }), { status: 503 })
      : { ...META, published: true, n: 4 } });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.change(await screen.findByRole("textbox", { name: "Summary" }), { target: { value: "Z" } });
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("busy");
    const order = calls.filter((c) => c.method !== "GET").map((c) => c.method);
    expect(order).toEqual(["PUT", "POST"]);
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByText("Profile page")).toBeInTheDocument();
    const keys = calls.filter((c) => c.url.endsWith("/publish")).map((c) => (c.body as { key: string }).key);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
  });

  it("editing a sourced bullet drops its source and marks it user-written (DEC-018)", async () => {
    const doc = { ...DOC, experience: [{ ...DOC.experience[0], bullets: [{ id: "experience-1.b1", source: "m.1", text: "Worked on billing" }] }] };
    const calls = api({ "GET /api/profile/resumes/cv/draft": { rev: 3, resume: doc, draft: true } });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.change(await screen.findByRole("textbox", { name: "Experience 1 bullet 1" }), { target: { value: "Ran billing" } });
    await tick(700);
    const sent = (puts(calls)[0]!.body as { resume: typeof DOC }).resume.experience[0]!.bullets[0]!;
    expect(sent).toEqual({ id: "experience-1.b1", origin: "user", text: "Ran billing" });
  });

  it("Done locks editing so no edit lands after the flush", async () => {
    api({ "POST /api/profile/resumes/cv/publish": () => new Promise(() => {}) });
    renderRoutes(routes, "/resumes/cv");
    const box = await screen.findByRole("textbox", { name: "Summary" });
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(box).toHaveAttribute("readonly"));
  });

  it("409 on autosave offers Reload / Overwrite; Overwrite re-PUTs with the server's rev and Done works", async () => {
    let conflict = true;
    const calls = api({
      "PUT /api/profile/resumes/cv/draft": (c: Call) => conflict
        ? new Response(JSON.stringify({ detail: "stale rev" }), { status: 409 })
        : { rev: (c.body as { rev: number }).rev + 1, resume: (c.body as { resume: unknown }).resume, draft: true },
      "GET /api/profile/resumes/cv/draft": () => ({ rev: calls.filter((x) => x.method === "PUT").length ? 9 : 3, resume: DOC, draft: true }),
      "POST /api/profile/resumes/cv/publish": { ...META, published: true, n: 4 },
    });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.change(await screen.findByRole("textbox", { name: "Summary" }), { target: { value: "Mine" } });
    await tick(800);
    expect(await screen.findByRole("button", { name: "Reload" })).toBeInTheDocument();
    conflict = false;
    fireEvent.click(screen.getByRole("button", { name: "Overwrite" }));
    expect(await screen.findByText("All changes saved")).toBeInTheDocument();
    const last = puts(calls).at(-1)!.body as { rev: number; resume: typeof DOC };
    expect(last.rev).toBe(9);
    expect(last.resume.summary).toBe("Mine");
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByText("Profile page")).toBeInTheDocument();
  });

  it("409 then Reload takes the server draft and drops local edits", async () => {
    const server = { ...DOC, summary: "Server copy" };
    const calls = api({
      "PUT /api/profile/resumes/cv/draft": () => new Response(JSON.stringify({ detail: "stale rev" }), { status: 409 }),
      "GET /api/profile/resumes/cv/draft": () => (puts(calls).length ? { rev: 7, resume: server, draft: true } : { rev: 3, resume: DOC, draft: true }),
    });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.change(await screen.findByRole("textbox", { name: "Summary" }), { target: { value: "Mine" } });
    await tick(800);
    fireEvent.click(await screen.findByRole("button", { name: "Reload" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Summary" })).toHaveValue("Server copy"));
    expect(await screen.findByText("All changes saved")).toBeInTheDocument();
  });

  it("asks before closing the tab while unsaved", async () => {
    api();
    renderRoutes(routes, "/resumes/cv");
    const ev = () => { const e = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; };
    fireEvent.change(await screen.findByRole("textbox", { name: "Summary" }), { target: { value: "A" } });
    expect(ev()).toBe(true);
    await tick(800);
    await screen.findByText("All changes saved");
    expect(ev()).toBe(false);
  });

  it("blocks in-app navigation while a save is failing; Stay keeps the page, Leave anyway goes", async () => {
    api({ "PUT /api/profile/resumes/cv/draft": () => new Response(JSON.stringify({ detail: "disk full" }), { status: 500 }) });
    const { router } = renderRoutes(routes, "/resumes/cv");
    fireEvent.change(await screen.findByRole("textbox", { name: "Summary" }), { target: { value: "X" } });
    await tick(800);
    await screen.findByText(/Couldn’t save/);
    await act(() => router.navigate("/profile"));
    expect(await screen.findByText(/aren’t saved/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.queryByText(/aren’t saved/)).toBeNull();
    await act(() => router.navigate("/profile"));
    fireEvent.click(await screen.findByRole("button", { name: "Leave anyway" }));
    expect(await screen.findByText("Profile page")).toBeInTheDocument();
  });

  it("locks fields while publishing and disables Done while an accept is in flight", async () => {
    api({
      "POST /api/profile/resumes/cv/publish": () => new Promise(() => {}),
      "POST /api/profile/resumes/cv/annotations/a1/accept": () => new Promise(() => {}),
    });
    renderRoutes(routes, "/resumes/cv");
    const box = await screen.findByRole("textbox", { name: "Summary" });
    const card = screen.getByRole("article", { name: /Shows impact/ });
    fireEvent.click(within(card).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Done" })).toBeDisabled());
    expect(box).toHaveAttribute("readonly");
  });

  it("after a failed Apply-comment send, keeps the text but blocks resend until edited", async () => {
    const calls = api({ "POST /api/profile/resumes/cv/annotations/a2/replies": () => new Response(JSON.stringify({ detail: "no run" }), { status: 500 }) });
    renderRoutes(routes, "/resumes/cv");
    const comment = await screen.findByRole("article", { name: /Name the stack/ });
    const input = within(comment).getByRole("textbox", { name: "Reply" });
    fireEvent.change(input, { target: { value: "Use Python" } });
    fireEvent.click(within(comment).getByRole("button", { name: "Send" }));
    await within(comment).findByText("no run");
    expect(input).toHaveValue("Use Python");
    expect(within(comment).getByRole("button", { name: "Send" })).toBeDisabled();
    fireEvent.submit(input.closest("form")!);
    await tick(0);
    expect(calls.filter((c) => c.url.endsWith("/replies"))).toHaveLength(1);
    fireEvent.change(input, { target: { value: "Use Python 3" } });
    expect(within(comment).getByRole("button", { name: "Send" })).toBeEnabled();
  });

  const applyAndSend = async (extra: Record<string, unknown>) => {
    api({ "POST /api/profile/resumes/cv/annotations/a2/replies": { ...COMM, run_id: "r1" }, ...extra });
    renderRoutes(routes, "/resumes/cv");
    const comment = await screen.findByRole("article", { name: /Name the stack/ });
    fireEvent.change(within(comment).getByRole("textbox", { name: "Reply" }), { target: { value: "Use Python" } });
    fireEvent.click(within(comment).getByRole("checkbox", { name: /Apply comment/ }));
    fireEvent.click(within(comment).getByRole("button", { name: "Send" }));
    await tick(0);
    return comment;
  };

  it("Apply comment follows the run, then lists what it wrote", async () => {
    let n = 0;
    const comment = await applyAndSend({
      "GET /api/runs/r1": () => (++n < 2 ? { state: "running" } : { state: "done", stop_reason: "completed" }),
      "GET /api/profile/resumes/cv/annotations": [COMM, SUGG],
    });
    expect(within(comment).getByText("Claude is revising…")).toBeInTheDocument();
    await tick(2500);
    expect(await within(comment).findByText(/Claude added/)).toBeInTheDocument();
  });

  it("Apply comment: a failed run shows an error", async () => {
    const comment = await applyAndSend({ "GET /api/runs/r1": { state: "failed", stop_reason: "error", detail: "no suggestion written" } });
    await tick(1500);
    expect(await within(comment).findByRole("alert")).toHaveTextContent("no suggestion written");
  });

  it("Apply comment: a done run that stopped as failed shows an error, not 0 responses", async () => {
    const comment = await applyAndSend({ "GET /api/runs/r1": { state: "done", stop_reason: "failed", detail: "proposed nothing" } });
    await tick(1500);
    expect(await within(comment).findByRole("alert")).toHaveTextContent("proposed nothing");
    expect(within(comment).queryByText(/Claude added/)).toBeNull();
  });

  it("onboarding: Next replaces Done and publishes as master", async () => {
    const calls = api({ "POST /api/profile/resumes/cv/publish": { n: 1 } });
    renderRoutes(routes, "/resumes/cv?onboarding=1");
    expect(await screen.findByRole("button", { name: /Next: Saved answers/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Done" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Next: Saved answers/ }));
    await tick(300);
    expect(calls.find((c) => c.url.endsWith("/publish"))!.body).toMatchObject({ master: true });
  });

  it("onboarding: a draft master shows Next without the URL flag", async () => {
    api({ "GET /api/profile/resumes": { resumes: [{ rid: "cv", type: "master", status: "draft" }] } });
    renderRoutes(routes, "/resumes/cv");
    expect(await screen.findByRole("button", { name: /Next: Saved answers/ })).toBeInTheDocument();
  });

  it("onboarding: a ready master keeps Done", async () => {
    api({ "GET /api/profile/resumes": { resumes: [{ rid: "cv", type: "master", status: "ready" }] } });
    renderRoutes(routes, "/resumes/cv");
    expect(await screen.findByRole("button", { name: "Done" })).toBeInTheDocument();
    await tick(300);
    expect(screen.queryByRole("button", { name: /Next: Saved answers/ })).toBeNull();
  });

  it("shows Not carried over lines from the import", async () => {
    api({ "GET /api/profile/resumes/cv/import": { state: "done", dropped: [{ id: "d1", text: "Hobby: chess", restored: false }] } });
    renderRoutes(routes, "/resumes/cv");
    expect(await screen.findByText("Hobby: chess")).toBeInTheDocument();
  });
});
