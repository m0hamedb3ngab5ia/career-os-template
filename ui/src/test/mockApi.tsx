import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { vi } from "vitest";
import { ToastProvider } from "../kit/Toast";

export interface Call {
  method: string;
  url: string;
  body: unknown;
  headers: Record<string, string>;
}

type Handler = (call: Call) => unknown;

/**
 * Stub fetch with handlers keyed "METHOD /path" (the query string is ignored for matching; the handler gets the
 * full url). Unknown routes answer 404. Returns the list of calls made.
 */
export function mockApi(handlers: Record<string, Handler | unknown>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      const method = (init.method ?? "GET").toUpperCase();
      const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      const call: Call = { method, url, body, headers: (init.headers ?? {}) as Record<string, string> };
      calls.push(call);
      const key = `${method} ${url.split("?")[0]}`;
      if (!(key in handlers)) return new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 404 });
      const h = handlers[key];
      const out = typeof h === "function" ? await (h as Handler)(call) : h;
      if (out instanceof Response) return out;
      return new Response(JSON.stringify(out ?? {}), { headers: { "content-type": "application/json" } });
    }),
  );
  return calls;
}

export function renderRoutes(routes: RouteObject[], path: string, wrap?: (n: ReactNode) => ReactNode) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  );
  return { router, qc, ...render(wrap ? wrap(tree) : tree) };
}

export const META = {
  statuses: ["found", "scored", "skipped", "queued", "prepared", "needs_review", "applied", "screening", "interview",
    "offer", "rejected", "withdrawn", "ghosted"],
  tiers: ["A", "B", "C"],
  priorities: ["H", "M", "L"],
  action_types: ["review", "captcha", "scam_suspected", "other"],
  action_needs: ["laptop", "phone", "anytime"],
  safety_verdicts: ["pass", "review", "block", "skip"],
  pipeline: {
    columns: [
      { name: "Found", statuses: ["found", "scored"] },
      { name: "Queued", statuses: ["queued", "prepared"] },
      { name: "Needs review", statuses: ["needs_review"] },
      { name: "Applied", statuses: ["applied"] },
      { name: "Screening · Interview", statuses: ["screening", "interview"] },
      { name: "Offer", statuses: ["offer"] },
    ],
    closed: ["skipped", "rejected", "withdrawn", "ghosted"],
  },
  ui: { theme: "system", undo_seconds: 8, page_size: 100, due_soon_hours: 48 },
};
