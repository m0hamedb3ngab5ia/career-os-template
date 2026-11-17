import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { routes } from "../../app/routes";
import { FakeEventSource } from "../../test/fakeEventSource";

const profile = {
  resumes: [{ rid: "acme-1", name: "Master résumé", type: "master", version: 2, at: "2026-11-01T10:00:00+00:00" }],
  documents: [{ name: "transcript.pdf", size: 2048 }],
  answers: [{ key: "work_authorization", answer: "Yes" }],
};
const settings = {
  sections: [{ id: "targets", title: "Targets", groups: [{ title: "Salary", rows: [{ label: "Minimum base", value: "90000", help: "" }] }] }],
};

function renderAt(path: string, bodies: Record<string, unknown>) {
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const hit = Object.entries(bodies).find(([k]) => String(url).startsWith(k));
      if (hit?.[1] instanceof Response) return hit[1].clone();
      return hit
        ? new Response(JSON.stringify(hit[1]), { headers: { "content-type": "application/json" } })
        : new Response(JSON.stringify({ detail: "nope" }), { status: 404 });
    }),
  );
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("Profile page", () => {
  it("lists résumés, documents and standard answers in groups", async () => {
    const { container } = renderAt("/profile", { "/api/profile": profile });
    expect(await screen.findByRole("heading", { level: 1, name: "Profile" }, { timeout: 4000 })).toBeInTheDocument();
    const resumes = await screen.findByRole("region", { name: "Résumés" });
    expect(within(resumes).getByText("Master résumé")).toBeInTheDocument();
    expect(within(resumes).getByText(/Master · v2/)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Documents" })).getByText("2 KB")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Standard answers" })).getByText("work authorization")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows the master résumé itself (REQ-151)", async () => {
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:master", revokeObjectURL: () => {} }));
    renderAt("/profile", { "/api/profile/master.pdf": "pdf", "/api/profile": profile });
    const frame = await screen.findByTitle("Master résumé", {}, { timeout: 4000 });
    expect(frame).toHaveAttribute("src", "blob:master");
  });

  it("explains when the master résumé can't be shown", async () => {
    renderAt("/profile", { "/api/profile/master.pdf": new Response("{}", { status: 409 }), "/api/profile": profile });
    expect(await screen.findByText(/can’t be shown here/, {}, { timeout: 4000 })).toBeInTheDocument();
  });

  it("says so when a group is empty", async () => {
    renderAt("/profile", { "/api/profile": { resumes: [], documents: [], answers: [] } });
    expect(await screen.findByText(/No résumés yet/, {}, { timeout: 4000 })).toBeInTheDocument();
  });
});

describe("Settings page", () => {
  it("shows the config grouped, read only", async () => {
    const { container } = renderAt("/settings", { "/api/settings": settings });
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" }, { timeout: 4000 })).toBeInTheDocument();
    const salary = await screen.findByRole("region", { name: "Salary" });
    expect(within(salary).getByText("Minimum base")).toBeInTheDocument();
    expect(within(salary).getByText("90000")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows an error when settings cannot load", async () => {
    renderAt("/settings", {});
    expect(await screen.findByText("Couldn’t load settings", {}, { timeout: 4000 })).toBeInTheDocument();
  });
});
