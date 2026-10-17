import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type Call, mockApi, renderRoutes } from "../../test/mockApi";
import { WorkspacePage } from "./WorkspacePage";

const routes = [{ path: "/resumes/:rid", element: <WorkspacePage /> }, { path: "/profile", element: <p>Profile page</p> }];
const DOC = {
  schema_version: 1,
  identity: { name: "Alex Example", email: "alex@example.com" },
  summary: "Backend engineer",
  sections: [{ id: "s1", type: "experience", order: 1 }, { id: "s2", type: "projects", order: 2 }, { id: "s3", type: "education", order: 3 }, { id: "s4", type: "skills", order: 4 }],
  experience: [{ id: "experience-1", company: "Initech", title: "Intern", bullets: [{ id: "experience-1.b1", text: "Worked on billing" }] }],
  projects: [{ id: "projects-1", name: "Widgetizer", stack: ["Swift", "SwiftUI"], links: [{ label: "App Store", url: "https://example.com/a" }], bullets: [{ id: "projects-1.b1", text: "Built it" }] }],
  education: [{ id: "education-1", school: "State U", coursework: ["Databases"], activities: ["ACM"] }],
  skill_groups: [{ label: "Languages", items: ["Python", "SQL"] }],
};
const SUGG = { id: "a1", kind: "suggestion", author: "ai", status: "open", target_id: "experience-1.b1", base: "Worked on billing", proposed: "Fixed billing", text: "Impact", replies: [], at: null };
// oldest first, as the API returns; c2 was reverted by c3
const CH = [
  { id: "c1", author: "user", target_id: "experience-1.b1", kind: "bullet", op: "edit", before: { id: "experience-1.b1", text: "Old" }, after: { id: "experience-1.b1", text: "Worked on billing" } },
  { id: "c2", author: "user", target_id: "summary", kind: "field", op: "edit", before: "x", after: "Backend engineer" },
  { id: "c3", author: "user", target_id: "summary", kind: "field", op: "edit", before: "Backend engineer", after: "x", reverts: "c2" },
];
function api(extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/profile/resumes/cv": { rid: "cv", name: "cv.pdf", type: "master", category: null, versions: [] },
    "GET /api/profile/resumes/cv/draft": { rev: 3, resume: DOC, draft: true },
    "GET /api/profile/resumes/cv/annotations": [SUGG],
    "GET /api/profile/resumes/cv/draft/changes": CH,
    "PUT /api/profile/resumes/cv/draft": (c: Call) => ({ rev: (c.body as { rev: number }).rev + 1, resume: (c.body as { resume: unknown }).resume, draft: true }),
    ...extra,
  });
}
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => vi.useRealTimers());

describe("Workspace extras", () => {
  it("shows the open-suggestions count", async () => {
    api();
    renderRoutes(routes, "/resumes/cv");
    expect(await screen.findByText("1 open suggestion")).toBeInTheDocument();
  });

  it("ATS view tab shows the server-rendered plain text and hides the editor", async () => {
    api({ "GET /api/profile/resumes/cv/draft/text": "Alex Example\n- Worked on billing\n" });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.click(await screen.findByRole("tab", { name: "ATS view" }));
    const ats = await screen.findByLabelText("ATS view");
    await waitFor(() => expect(ats).toHaveTextContent("- Worked on billing"));  // the panel mounts before its text loads
    expect(screen.queryByRole("textbox", { name: "Summary" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Résumé" }));
    expect(screen.getByRole("textbox", { name: "Summary" })).toBeInTheDocument();
  });

  it("renders stack, links, coursework, activities and skill_groups as editable fields", async () => {
    const calls = api();
    renderRoutes(routes, "/resumes/cv");
    expect(await screen.findByRole("textbox", { name: "Projects 1 stack" })).toHaveValue("Swift, SwiftUI");
    expect(screen.getByRole("textbox", { name: "Projects 1 link 1 label" })).toHaveValue("App Store");
    expect(screen.getByRole("textbox", { name: "Projects 1 link 1 url" })).toHaveValue("https://example.com/a");
    expect(screen.getByRole("textbox", { name: "Education 1 coursework" })).toHaveValue("Databases");
    expect(screen.getByRole("textbox", { name: "Education 1 activities" })).toHaveValue("ACM");
    fireEvent.change(screen.getByRole("textbox", { name: "Skills Languages" }), { target: { value: "Python, Go" } });
    await tick(1000);
    expect(calls.filter((c) => c.method === "PUT").at(-1)!.body).toMatchObject({ resume: { skill_groups: [{ label: "Languages", items: ["Python", "Go"] }] } });
  });

  it("History lists changes newest first; Revert swaps in the returned draft; reverted entries are disabled", async () => {
    const back = structuredClone(DOC);
    back.experience[0]!.bullets[0]!.text = "Old";
    const calls = api({ "POST /api/profile/resumes/cv/draft/changes/c1/revert": { rev: 9, resume: back, draft: true } });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.click(await screen.findByRole("button", { name: /History/ }));
    const panel = await screen.findByRole("complementary", { name: "History" });
    const rows = await within(panel).findAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("reverted a change");
    expect(within(rows[1]!).getByRole("button", { name: "Revert" })).toBeDisabled();  // c2 reverted by c3
    fireEvent.click(within(rows[2]!).getByRole("button", { name: "Revert" }));
    await tick(100);
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/changes/c1/revert"))).toBe(true);
    fireEvent.click(screen.getByRole("tab", { name: "Résumé" }));
    expect(await screen.findByRole("textbox", { name: "Experience 1 bullet 1" })).toHaveValue("Old");
  });

  it("Revert 409 shows both texts and keeps the draft", async () => {
    api({ "POST /api/profile/resumes/cv/draft/changes/c1/revert": new Response(JSON.stringify({ detail: { message: "changed", expected: "Worked on billing", current: "Edited since" } }), { status: 409 }) });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.click(await screen.findByRole("button", { name: /History/ }));
    const panel = await screen.findByRole("complementary", { name: "History" });
    const rows = await within(panel).findAllByRole("listitem");
    fireEvent.click(within(rows[2]!).getByRole("button", { name: "Revert" }));
    const alert = await within(panel).findByRole("alert");
    expect(alert).toHaveTextContent("Worked on billing");
    expect(alert).toHaveTextContent("Edited since");
  });

  it("Ctrl/Cmd+Z undoes the user's own edits (also inside a field); Ctrl+Shift+Z redoes", async () => {
    const calls = api();
    renderRoutes(routes, "/resumes/cv");
    const sum = await screen.findByRole("textbox", { name: "Summary" });
    fireEvent.change(sum, { target: { value: "Changed" } });
    expect(sum).toHaveValue("Changed");
    fireEvent.keyDown(sum, { key: "z", ctrlKey: true });
    expect(sum).toHaveValue("Backend engineer");
    fireEvent.keyDown(sum, { key: "z", ctrlKey: true, shiftKey: true });
    expect(sum).toHaveValue("Changed");
    fireEvent.keyDown(sum, { key: "z", metaKey: true });
    expect(sum).toHaveValue("Backend engineer");
    await tick(1000);
    expect(calls.filter((c) => c.method === "PUT").at(-1)!.body).toMatchObject({ resume: { summary: "Backend engineer" } });
  });

  it("Cmd+Z inside a margin comment field is left to the browser", async () => {
    api();
    renderRoutes(routes, "/resumes/cv");
    const sum = await screen.findByRole("textbox", { name: "Summary" });
    fireEvent.change(sum, { target: { value: "Changed" } });
    const reply = await screen.findByRole("textbox", { name: "Reply" });
    const ev = new KeyboardEvent("keydown", { key: "z", metaKey: true, bubbles: true, cancelable: true });
    reply.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(false);
    expect(sum).toHaveValue("Changed");
  });

  it("Cmd+Z with focus on a button still undoes", async () => {
    api();
    renderRoutes(routes, "/resumes/cv");
    const sum = await screen.findByRole("textbox", { name: "Summary" });
    fireEvent.change(sum, { target: { value: "Changed" } });
    fireEvent.keyDown(screen.getByRole("tab", { name: "Résumé" }), { key: "z", metaKey: true });
    expect(sum).toHaveValue("Backend engineer");
  });

  it("does not refetch annotations on re-render after an Apply run ended", async () => {
    const calls = api({
      "GET /api/profile/resumes/cv/annotations": [{ ...SUGG, id: "a2", kind: "comment", author: "user", proposed: null, text: "Name the stack" }],
      "POST /api/profile/resumes/cv/annotations/a2/replies": { id: "a2", run_id: "r1", replies: [] },
      "GET /api/runs/r1": { state: "done", stop_reason: "completed" },
    });
    renderRoutes(routes, "/resumes/cv");
    const reply = await screen.findByRole("textbox", { name: "Reply" });
    fireEvent.change(reply, { target: { value: "Use Python" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Apply comment/ }));
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await tick(2500);
    const n = () => calls.filter((c) => c.method === "GET" && c.url.endsWith("/annotations")).length;
    const before = n();
    fireEvent.change(await screen.findByRole("textbox", { name: "Summary" }), { target: { value: "Changed" } });
    await tick(300);
    expect(n()).toBe(before);
  });

  it("tabs are wired to panels and switch with the arrow keys", async () => {
    api({ "GET /api/profile/resumes/cv/draft/text": "Alex Example\n" });
    renderRoutes(routes, "/resumes/cv");
    const doc = await screen.findByRole("tab", { name: "Résumé" });
    expect(doc).toHaveAttribute("aria-controls", "tabpanel-doc");
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", doc.id);
    fireEvent.keyDown(doc, { key: "ArrowRight" });
    expect(await screen.findByLabelText("ATS view")).toHaveAttribute("role", "tabpanel");
    fireEvent.keyDown(screen.getByRole("tab", { name: "ATS view" }), { key: "ArrowLeft" });
    expect(await screen.findByLabelText("Résumé draft")).toBeInTheDocument();
  });
});

describe("Comment card highlight", () => {
  const marked = () => Array.from(document.querySelectorAll("[id^='t-'][data-on]")).map((e) => e.id);
  const marks = () => Array.from(document.querySelectorAll("[id^='t-'] mark")).map((m) => [m.closest("[id^='t-']")!.id, m.textContent]).sort();

  it("selecting a card highlights its target and scrolls to it; selecting it again clears it", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    api();
    renderRoutes(routes, "/resumes/cv");
    const card = await screen.findByRole("button", { name: "Impact" });
    expect(card).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(card);
    expect(card).toHaveAttribute("aria-pressed", "true");
    expect(marked()).toEqual(["t-experience-1.b1"]);
    expect(scroll).toHaveBeenCalled();
    fireEvent.click(card);
    expect(card).toHaveAttribute("aria-pressed", "false");
    expect(marked()).toEqual([]);
  });

  it("a bridged comment (no target) highlights every field matching its quote, case/whitespace-insensitive", async () => {
    const old = { id: "f1", kind: "comment", author: "ai", status: "open", target_id: null, base: " BUILT\n  it ", proposed: null, text: "Projects: vague", replies: [], at: null };
    api({
      "GET /api/profile/resumes/cv/draft": { rev: 3, resume: { ...DOC, summary: "I built it twice" }, draft: true },
      "GET /api/profile/resumes/cv/annotations": [old],
    });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.click(await screen.findByRole("button", { name: "Projects: vague" }));
    expect(marks()).toEqual([["t-projects-1.b1", "Built it"], ["t-summary", "built it"]]);
    expect(marked()).toEqual([]);  // inline spans, not whole fields
  });

  it("a quoted comment highlights exactly the quoted words inline, scrolls to them, shows the quote on the card", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    const q = { ...SUGG, id: "q1", kind: "comment", proposed: null, quote: "ON  billing", text: "Which system?" };
    api({ "GET /api/profile/resumes/cv/annotations": [q] });
    renderRoutes(routes, "/resumes/cv");
    const card = await screen.findByRole("button", { name: "Which system?" });
    expect(card.closest("article")).toHaveTextContent("“ON billing”");
    expect(marks()).toEqual([]);
    fireEvent.click(card);
    expect(marks()).toEqual([["t-experience-1.b1", "on billing"]]);
    expect(marked()).toEqual([]);
    expect((scroll.mock.contexts[0] as Element).tagName).toBe("MARK");
    fireEvent.click(card);
    expect(marks()).toEqual([]);
  });

  it("a comment on several passages marks every one inline, scrolls to the first, lists 3 quotes + more", async () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    const anchors = [{ target_id: "experience-1.b1", quote: "billing" }, { target_id: "summary", quote: "BACKEND" },
      { target_id: "projects-1.b1", quote: "built" }, { target_id: "experience-1.b1", quote: "worked" }];
    const q = { ...SUGG, id: "m1", kind: "comment", proposed: null, quote: "billing", anchors, text: "Everywhere" };
    api({ "GET /api/profile/resumes/cv/annotations": [q] });
    renderRoutes(routes, "/resumes/cv");
    const card = await screen.findByRole("button", { name: "Everywhere" });
    const art = card.closest("article")!;
    expect(art).toHaveTextContent("“billing”");
    expect(art).toHaveTextContent("“BACKEND”");
    expect(art).toHaveTextContent("“built”");
    expect(art).not.toHaveTextContent("“worked”");
    expect(art).toHaveTextContent("+1 more");
    fireEvent.click(card);
    expect(marks()).toEqual([["t-experience-1.b1", "Worked"], ["t-experience-1.b1", "billing"],
      ["t-projects-1.b1", "Built"], ["t-summary", "Backend"]]);
    expect(marked()).toEqual([]);
    expect((scroll.mock.contexts[0] as Element).closest("[id^='t-']")!.id).toBe("t-experience-1.b1");
  });

  it("a quote the target no longer holds falls back to highlighting the whole target", async () => {
    const q = { ...SUGG, id: "q2", kind: "comment", proposed: null, quote: "payments", text: "Stale" };
    api({ "GET /api/profile/resumes/cv/annotations": [q] });
    renderRoutes(routes, "/resumes/cv");
    fireEvent.click(await screen.findByRole("button", { name: "Stale" }));
    expect(marked()).toEqual(["t-experience-1.b1"]);
    expect(marks()).toEqual([]);
  });

  it("a card with neither target nor matchable quote still selects, with no highlight", async () => {
    const lone = { id: "f2", kind: "comment", author: "ai", status: "open", target_id: null, base: null, proposed: null, text: "General: tighten", replies: [], at: null };
    api({ "GET /api/profile/resumes/cv/annotations": [lone, { ...lone, id: "f3", base: "not in the résumé", text: "Other" }] });
    renderRoutes(routes, "/resumes/cv");
    const card = await screen.findByRole("button", { name: "General: tighten" });
    fireEvent.click(card);
    expect(card).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Other" }));
    expect(screen.getByRole("button", { name: "Other" })).toHaveAttribute("aria-pressed", "true");
    expect(card).toHaveAttribute("aria-pressed", "false");
    expect(marked()).toEqual([]);
  });
});
