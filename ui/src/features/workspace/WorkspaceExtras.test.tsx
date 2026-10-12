import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type Call, mockApi, renderRoutes } from "../../test/mockApi";
import { atsText } from "./atsText";
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

describe("atsText", () => {
  it("is plain text: header, summary, sections in order, no suggestions", () => {
    const t = atsText(DOC);
    expect(t).toContain("Alex Example\nalex@example.com");
    expect(t).toMatch(/SUMMARY\nBackend engineer/);
    expect(t.indexOf("EXPERIENCE")).toBeLessThan(t.indexOf("SKILLS"));
    expect(t).toContain("- Worked on billing");
    expect(t).toContain("Stack: Swift, SwiftUI");
    expect(t).toContain("Languages: Python, SQL");
    expect(t).not.toContain("Fixed billing");
  });
});

describe("Workspace extras", () => {
  it("shows the open-suggestions count", async () => {
    api();
    renderRoutes(routes, "/resumes/cv");
    expect(await screen.findByText("1 open suggestion")).toBeInTheDocument();
  });

  it("ATS view tab shows the plain text and hides the editor", async () => {
    api();
    renderRoutes(routes, "/resumes/cv");
    fireEvent.click(await screen.findByRole("tab", { name: "ATS view" }));
    expect(screen.getByLabelText("ATS view")).toHaveTextContent("- Worked on billing");
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
});
