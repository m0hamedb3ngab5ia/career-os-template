import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { unexplainedDisabled } from "../../test/disabled";
import { mockApi, renderRoutes } from "../../test/mockApi";
import { AnswersPage } from "./AnswersPage";

const routes = [{ path: "/profile/answers", element: <AnswersPage /> }];
const BASE = {
  "GET /api/profile/answers": {
    answers: [
      { scope: "general", key: "relocate", company: null, answer: "Yes", match: [], note: null },
      { scope: "company", key: "why_us", company: "Acme", answer: "Rockets.", match: [], note: null },
      { scope: "eeo", key: "gender", company: null, answer: null, match: [], note: null },
    ],
  },
};

afterEach(() => vi.unstubAllGlobals());

describe("AnswersPage", () => {
  it("shows grouped labels, Not set, and is accessible", async () => {
    mockApi(BASE);
    const { container } = renderRoutes(routes, "/profile/answers");
    expect(await screen.findByRole("heading", { name: "Job preferences · 1" })).toBeInTheDocument();
    expect(screen.getByText("Willing to relocate")).toBeInTheDocument();
    expect(screen.getByText("Not set")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete/ })).toBeNull();
    expect(unexplainedDisabled(container)).toEqual([]);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("edits an answer, and deletes only from edit mode", async () => {
    const calls = mockApi({ ...BASE, "PUT /api/profile/answers/why_us": {}, "DELETE /api/profile/answers/gender": {} });
    renderRoutes(routes, "/profile/answers");
    await userEvent.click(await screen.findByRole("button", { name: "Edit Why us (Acme)" }));
    const box = screen.getByRole("textbox", { name: "Answer for Why us (Acme)" });
    await userEvent.clear(box);
    expect(screen.getByRole("button", { name: "Save" })).toHaveAccessibleDescription("Type an answer first");
    await userEvent.type(box, "Space.");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ answer: "Space.", company: "Acme", eeo: false });
    await userEvent.click(await screen.findByRole("button", { name: "Edit Gender" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete Gender" }));
    await userEvent.click(within(screen.getByRole("group", { name: "Delete Gender?" })).getByRole("button", { name: "Yes, delete" }));
    expect(calls.find((c) => c.method === "DELETE")?.url).toBe("/api/profile/answers/gender?eeo=true");
  });

  it("a failed delete says so", async () => {
    mockApi({ ...BASE, "DELETE /api/profile/answers/relocate": new Response(JSON.stringify({ detail: "disk full" }), { status: 500 }) });
    renderRoutes(routes, "/profile/answers");
    await userEvent.click(await screen.findByRole("button", { name: "Edit Willing to relocate" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete Willing to relocate" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByText(/Couldn’t delete Willing to relocate: disk full/)).toBeInTheDocument();
  });
});
