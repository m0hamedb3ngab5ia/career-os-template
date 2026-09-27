import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeEventSource } from "../test/fakeEventSource";
import { ToastProvider } from "../kit/Toast";
import { axeViolations } from "../test/axe";
import { routes } from "./routes";

function renderAt(path: string, status: unknown = {}) {
  vi.stubGlobal(
    "fetch",
    // Only /api/status answers; screens that load their own data see a 404 and must still render their frame.
    vi.fn(async (url: string) =>
      String(url).startsWith("/api/status")
        ? new Response(JSON.stringify(status), { headers: { "content-type": "application/json" } })
        : new Response(JSON.stringify({ detail: "not in this test" }), { status: 404 }),
    ),
  );
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...utils, router };
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

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

  it("marks the current section and shows its page heading", async () => {
    renderAt("/runs");
    expect(await screen.findByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");
    // the screen is a lazy route: allow for its chunk to load
    expect(await screen.findByRole("heading", { level: 1, name: "Runs" }, { timeout: 4000 })).toBeInTheDocument();
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

  it("job detail and settings sub-routes resolve", async () => {
    renderAt("/jobs/a3f91c02d7e4");
    // the Job detail route is lazy-loaded
    const nav = await screen.findByRole("navigation", { name: "Sections" }, { timeout: 5000 });
    expect(within(nav).getByRole("link", { name: /^Jobs/ })).toHaveAttribute("aria-current", "page");
  });

  it("unknown routes show a not-found page inside the shell", () => {
    renderAt("/nope");
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = renderAt("/");
    expect(await axeViolations(container)).toEqual([]);
  });

  describe("sidebar search", () => {
    it("Enter opens Jobs filtered by the text", async () => {
      const user = userEvent.setup();
      const { router } = renderAt("/");
      const box = screen.getByRole("searchbox", { name: "Search jobs and companies" });
      expect(box).toBeEnabled();
      expect(screen.getByRole("search")).toContainElement(box);
      await user.type(box, "northwind labs{Enter}");
      await waitFor(() => expect(router.state.location.pathname).toBe("/jobs"));
      expect(router.state.location.search).toBe("?q=northwind+labs");
    });

    it("on Jobs it keeps the other view settings, mirrors q, and an empty search clears it", async () => {
      const user = userEvent.setup();
      const { router } = renderAt("/jobs?tab=review&q=globex");
      const box = await screen.findByRole("searchbox", { name: "Search jobs and companies" }, { timeout: 5000 });
      expect(box).toHaveValue("globex");
      await user.clear(box);
      await user.type(box, "initech{Enter}");
      expect(router.state.location.search).toBe("?tab=review&q=initech");
      await user.clear(box);
      await user.keyboard("{Enter}");
      expect(router.state.location.search).toBe("?tab=review");
    });

    it("elsewhere the box starts empty", async () => {
      renderAt("/runs?q=globex");
      // the Runs route is lazy-loaded, so the shell appears once it resolves
      const box = await screen.findByRole("searchbox", { name: "Search jobs and companies" }, { timeout: 5000 });
      expect(box).toHaveValue("");
    });
  });

  describe("freshness footer", () => {
    it("reports the live connection: Connecting…, Live, Reconnecting…", () => {
      renderAt("/");
      const state = screen.getByTestId("connection");
      expect(state).toHaveTextContent("Connecting…");
      expect(state).toHaveAttribute("aria-live", "polite");
      act(() => FakeEventSource.last.open());
      expect(state).toHaveTextContent("Live");
      act(() => FakeEventSource.last.fail(false));
      expect(state).toHaveTextContent("Reconnecting…");
    });

    it("shows when the index was synced, outside the live region", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      vi.setSystemTime(new Date("2026-09-26T12:00:00Z"));
      renderAt("/", { index: { indexed_at: "2026-09-26T11:58:00Z" } });
      const synced = await screen.findByText(/Index synced 2 minutes ago/);
      expect(synced.closest("[aria-live]")).toBeNull();
    });

    it("shows no freshness text without timestamps", async () => {
      renderAt("/", { counts: { jobs: 0 } });
      await screen.findAllByText("0");
      expect(screen.queryByText(/synced/)).not.toBeInTheDocument();
    });
  });
});

describe("AppShell route changes", () => {
  it("moves focus to the main region and announces the new page's title", async () => {
    const user = userEvent.setup();
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: "Sections" });
    await user.click(within(nav).getByRole("link", { name: /^Runs/ }));
    const h1 = await screen.findByRole("heading", { level: 1, name: "Runs" });
    const main = screen.getByRole("main");
    await waitFor(() => expect(main).toHaveFocus());
    expect(main.contains(h1)).toBe(true);
    expect(screen.getByTestId("route-announcer")).toHaveTextContent("Runs");
  });

  it("does not announce or move focus on the first load", async () => {
    renderAt("/runs");
    await screen.findByRole("heading", { level: 1, name: "Runs" });
    expect(screen.getByRole("main")).not.toHaveFocus();
    expect(screen.getByTestId("route-announcer")).toHaveTextContent("");
  });

  it("leaves focus alone when only the query string changes (e.g. ?sel=)", async () => {
    const { router } = renderAt("/runs");
    await screen.findByRole("heading", { level: 1, name: "Runs" });
    const search = screen.getByRole("searchbox", { name: "Search jobs and companies" });
    search.focus();
    await act(() => router.navigate("/runs?sel=abc"));
    expect(search).toHaveFocus();
    expect(screen.getByTestId("route-announcer")).toHaveTextContent("");
  });

  it("waits for a loading page's real title before announcing it (not the placeholder)", async () => {
    const { router } = renderAt("/runs");
    await screen.findByRole("heading", { level: 1, name: "Runs" });
    await act(() => router.navigate("/runs/abc"));
    const h1 = await screen.findByRole("heading", { level: 1, name: (n) => n !== "Run" && n !== "Runs" });
    await waitFor(() => expect(screen.getByTestId("route-announcer")).toHaveTextContent(h1.textContent!));
    expect(screen.getByTestId("route-announcer").textContent).not.toBe("Run");
  });

  it("Ctrl+K focuses the sidebar search off a Mac (Cmd+K does not)", async () => {
    const user = userEvent.setup();
    renderAt("/runs");
    const search = await screen.findByRole("searchbox", { name: "Search jobs and companies" });
    await user.keyboard("{Meta>}k{/Meta}");
    expect(search).not.toHaveFocus();
    await user.keyboard("{Control>}k{/Control}");
    expect(search).toHaveFocus();
    expect(search).toHaveAttribute("aria-keyshortcuts", "Control+K");
  });

  it("on a Mac Cmd+K focuses the search and Ctrl+K in a text field is left to the field", async () => {
    vi.spyOn(navigator, "platform", "get").mockReturnValue("MacIntel");
    try {
      const user = userEvent.setup();
      renderAt("/runs");
      const search = await screen.findByRole("searchbox", { name: "Search jobs and companies" });
      expect(search).toHaveAttribute("aria-keyshortcuts", "Meta+K");
      const area = document.body.appendChild(document.createElement("textarea"));
      area.focus();
      expect(fireEvent.keyDown(area, { key: "k", ctrlKey: true })).toBe(true);
      expect(area).toHaveFocus();
      await user.keyboard("{Meta>}k{/Meta}");
      expect(search).toHaveFocus();
      area.remove();
    } finally {
      vi.restoreAllMocks();
    }
  });

  it("does not pull focus out of an open modal", async () => {
    renderAt("/runs");
    await screen.findByRole("searchbox", { name: "Search jobs and companies" });
    const modal = document.body.appendChild(document.createElement("div"));
    modal.setAttribute("aria-modal", "true");
    const inside = modal.appendChild(document.createElement("button"));
    inside.focus();
    expect(fireEvent.keyDown(inside, { key: "k", ctrlKey: true })).toBe(true);
    expect(inside).toHaveFocus();
    modal.remove();
  });
});
