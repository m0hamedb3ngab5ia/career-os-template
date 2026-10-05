import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../kit/Toast";
import { FakeEventSource } from "../test/fakeEventSource";
import { unexplainedDisabled } from "../test/disabled";
import { routes } from "./routes";

// REQ-119: every screen's header has an h1 and a one-line guidance under it. Enumerates the route table, so a new
// screen without guidance fails here. Redirect-only routes (loader, no screen) are skipped.
const paths = (routes[0]!.children ?? [])
  .filter((r) => !r.loader)
  .map((r) => (r.index ? "/" : `/${r.path!.replace("*", "nope").replace(/\/:\w+\?/g, "").replace(/:(\w+)/g, "$1-x")}`));

beforeEach(() => vi.stubGlobal("EventSource", FakeEventSource));
afterEach(() => vi.unstubAllGlobals());

describe("page guidance (REQ-119)", () => {
  it("covers every screen route", () => {
    expect(paths.length).toBeGreaterThanOrEqual(14);
  });

  it.each(paths)("%s has an h1 and a guidance line", async (path) => {
    // No API answers: each screen must still show its header (loading, empty or error state).
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "not in this test" }), { status: 404 })));
    const router = createMemoryRouter(routes, { initialEntries: [path] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </QueryClientProvider>,
    );
    // Wait for the settled header (not the aria-busy loading one), then read its guidance line.
    await screen.findByRole("heading", { level: 1 }, { timeout: 5000 });
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).not.toHaveAttribute("aria-busy"), { timeout: 5000 });
    const settled = screen.getByRole("heading", { level: 1 });
    expect(settled.parentElement?.querySelector("h1 + *")?.textContent?.trim()).toBeTruthy();
    // REQ-119 / P-rule: a control that can't be used says why (title or aria-describedby).
    if (path !== "/kit") expect(unexplainedDisabled()).toEqual([]); // Kit demos disabled states on purpose
  });

  it.each(["/contacts", "/inbox", "/pipeline", "/actions", "/automation/runs/r1"])("%s error state offers Try again", async (path) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500 })));
    const router = createMemoryRouter(routes, { initialEntries: [path] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("button", { name: "Try again" }, { timeout: 5000 })).toBeInTheDocument();
  });
});
