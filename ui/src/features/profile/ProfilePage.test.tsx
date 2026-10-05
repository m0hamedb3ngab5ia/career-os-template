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
    expect(screen.getByRole("button", { name: "Make master" })).toHaveAttribute("title", "Already the master résumé");
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
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("title", "Type an answer first");
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

  it("failed loads offer Try again", async () => {
    mockApi({ ...BASE, "GET /api/readiness": new Response("{}", { status: 500 }) });
    renderRoutes(routes, "/profile");
    expect(await screen.findByText(/Couldn’t check your setup/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
