import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../kit/Toast";
import { FakeEventSource } from "../test/fakeEventSource";
import { routes } from "./routes";
import { TOUR_STEPS } from "./Tour";

// A fake server holding data/ui_state.json; survives "reloads" (fresh renders) like the real file.
let state: { tour_done: boolean } | null;
let puts: unknown[];
let failPut = false;

function renderApp(path = "/") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (b: unknown) => new Response(JSON.stringify(b), { headers: { "content-type": "application/json" } });
      if (String(url) === "/api/ui-state") {
        if (init?.method === "PUT" && failPut) return new Response(JSON.stringify({ detail: "disk full" }), { status: 500 });
        if (init?.method === "PUT") {
          state = JSON.parse(String(init.body));
          puts.push(state);
        }
        return json(state ?? { tour_done: false });
      }
      if (String(url).startsWith("/api/status")) return json({});
      return new Response(JSON.stringify({ detail: "not in this test" }), { status: 404 });
    }),
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

beforeEach(() => {
  state = null;
  puts = [];
  failPut = false;
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

describe("first-run tour (REQ-121)", () => {
  it("only points at main nav items, at most 8 steps", () => {
    expect(TOUR_STEPS.map((s) => s.to)).toEqual(["/", "/jobs", "/pipeline", "/inbox", "/profile", "/settings"]);
    expect(TOUR_STEPS.length).toBeLessThanOrEqual(8);
  });

  it("E2E-014-01: fresh install shows the tour; finishing saves tour_done and a reload shows none", async () => {
    const user = userEvent.setup();
    const { unmount } = renderApp();
    const dialog = await screen.findByRole("dialog", { name: "Today" });
    expect(screen.getByTestId("tour-ring")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toHaveFocus();
    for (const s of TOUR_STEPS.slice(1)) {
      await user.keyboard("{Enter}");
      expect(await screen.findByRole("dialog", { name: s.title })).toBeInTheDocument();
    }
    expect(dialog).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(puts).toEqual([{ tour_done: true }]));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    unmount();
    renderApp();
    await screen.findByRole("navigation", { name: "Sections" });
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/ui-state", expect.anything()));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Escape at step 2 ends it; Settings How to use restarts at step 1", async () => {
    const user = userEvent.setup();
    const { unmount } = renderApp();
    await screen.findByRole("dialog", { name: "Today" });
    await user.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("dialog", { name: "Jobs" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(puts).toEqual([{ tour_done: true }]));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    unmount();
    renderApp("/settings/general");
    const how = await screen.findByRole("button", { name: "How to use" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(how);
    expect(await screen.findByRole("dialog", { name: "Today" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(how).toHaveFocus();
    expect(puts).toHaveLength(1); // already done: no second write
  });

  it("Back keeps focus in the dialog (on Next), so Escape still closes it", async () => {
    const user = userEvent.setup();
    renderApp();
    await screen.findByRole("dialog", { name: "Today" });
    await user.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("dialog", { name: "Jobs" });
    await user.click(screen.getByRole("button", { name: "Back" }));
    await screen.findByRole("dialog", { name: "Today" });
    expect(screen.getByRole("button", { name: "Next" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("a failed save shows a toast", async () => {
    failPut = true;
    const user = userEvent.setup();
    renderApp();
    await screen.findByRole("dialog", { name: "Today" });
    await user.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(await screen.findByText(/Couldn’t save tour progress/)).toBeInTheDocument();
  });
});

describe("tour announcements", () => {
  it("has one live region, so each step is announced once", async () => {
    const { Tour } = await import("./Tour");
    const { mockApi, renderRoutes } = await import("../test/mockApi");
    mockApi({ "GET /api/ui-state": { tour_done: false } });
    renderRoutes([{ path: "/", element: <Tour /> }], "/");
    const live = await waitFor(() => {
      const l = screen.getByRole("dialog").querySelectorAll("[aria-live]");
      expect(l).toHaveLength(1);
      return l[0]!;
    });
    expect(live).toHaveTextContent("Step 1 of 6");
  });
});
