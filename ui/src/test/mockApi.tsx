import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { vi } from "vitest";
import { ToastProvider } from "../kit/Toast";

export interface Call {
  method: string;
  url: string;
  body: unknown;
  headers: Record<string, string>;
}

type Handler = (call: Call) => unknown | Response;

/**
 * Stub fetch with a route table: "GET /api/contacts" -> body (or a function of the call). Unknown routes answer
 * 404. Returns the list of calls so tests can assert what was written.
 */
export function mockApi(routes: Record<string, unknown | Handler>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      const method = (init.method ?? "GET").toUpperCase();
      const call: Call = {
        method,
        url,
        body: init.body ? JSON.parse(String(init.body)) : undefined,
        headers: (init.headers ?? {}) as Record<string, string>,
      };
      calls.push(call);
      const path = url.split("?")[0];
      const key = `${method} ${path}`;
      if (!(key in routes)) return new Response(JSON.stringify({ detail: "not mocked" }), { status: 404 });
      const r = routes[key];
      const out = typeof r === "function" ? (r as Handler)(call) : r;
      if (out instanceof Response) return out;
      return new Response(JSON.stringify(out), { headers: { "content-type": "application/json" } });
    }),
  );
  return calls;
}

export function renderRoutes(routes: RouteObject[], path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...utils, router, qc };
}
