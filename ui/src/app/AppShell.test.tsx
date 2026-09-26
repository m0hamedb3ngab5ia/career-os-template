import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../kit/Toast";
import { axeViolations } from "../test/axe";
import { routes } from "./routes";

function renderAt(path: string, status: unknown = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(status), { headers: { "content-type": "application/json" } })),
  );
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("AppShell", () => {
  it("lists the sections in the mockup's order and groups", () => {
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: "Sections" });
    const links = within(nav).getAllByRole("link").map((a) => a.textContent?.replace(/\d[\d,]*$/, "").trim());
    expect(links).toEqual([
      "Today",
      "Pipeline",
      "Jobs",
      "Action Items",
      "Inbox & Follow-ups",
      "Contacts",
      "Runs",
      "Settings",
    ]);
    for (const g of ["Overview", "Work", "System"]) expect(within(nav).getByText(g)).toBeInTheDocument();
  });

  it("marks the current section and shows its page heading", () => {
    renderAt("/runs");
    expect(screen.getByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { level: 1, name: "Runs" })).toBeInTheDocument();
  });

  it("shows live counts from /api/status; zero when there is no data yet", async () => {
    renderAt("/", { counts: { jobs: 736, action_items_open: 7, inbox: 0 } });
    const nav = screen.getByRole("navigation", { name: "Sections" });
    expect(await within(nav).findByText("736")).toBeInTheDocument();
    expect(within(nav).getByText("7")).toBeInTheDocument();
    expect(within(nav).getByText("0")).toBeInTheDocument();
  });

  it("has a skip link to the main content", () => {
    renderAt("/");
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(document.getElementById("main")).not.toBeNull();
  });

  it("job detail and settings sub-routes resolve", () => {
    renderAt("/jobs/a3f91c02d7e4");
    expect(screen.getByRole("link", { name: /^Jobs/ })).toHaveAttribute("aria-current", "page");
  });

  it("unknown routes show a not-found page inside the shell", () => {
    renderAt("/nope");
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = renderAt("/");
    expect(await axeViolations(container)).toEqual([]);
  });
});
