import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { vi } from "vitest";
import { ToastProvider } from "../../kit/Toast";
import type { CurrentRun, HistoryPage, Meta, Queue, RunDetail, Schedule } from "./types";

// A fake of the Runs API for screen tests: GET answers come from `data`, every request is recorded.

export interface Call {
  method: string;
  url: string;
  body: unknown;
  headers: Record<string, string>;
}

export const META: Meta = {
  stop_reasons: ["completed", "usage_limit", "error"],
  clean_stops: ["completed"],
  presets: {
    names: ["small", "medium", "large", "max", "custom"],
    values: {
      small: { max_score_jobs: 10, max_prepare_jobs: 2, max_minutes: 30 },
      medium: { max_score_jobs: 25, max_prepare_jobs: 5, max_minutes: 90 },
      large: { max_score_jobs: 50, max_prepare_jobs: 10, max_minutes: 180 },
      max: { max_score_jobs: 150, max_prepare_jobs: 25, max_minutes: 480 },
      custom: { max_score_jobs: 25, max_prepare_jobs: 5, max_minutes: 90 },
    },
    recommended: "medium",
    current: "medium",
  },
  ui: { theme: "system", undo_seconds: 8, page_size: 100 },
};

export function schedule(over: Partial<Schedule> = {}): Schedule {
  return {
    label: "com.careeros.tick",
    installed: false,
    loaded: false,
    last_tick: null,
    tick_minutes: 15,
    quiet_hours: { start: "09:00", end: "18:00" },
    jobs: [
      { kind: "scout", enabled: true, every_minutes: 180, at: [], preset: null, claude: false, next: "2026-09-26T15:00:00Z", last_run: null, last_status: null },
      { kind: "inbox_sync", enabled: false, every_minutes: null, at: ["08:00", "18:00"], preset: null, claude: true, next: null, last_run: null, last_status: null },
      { kind: "score", enabled: true, every_minutes: null, at: ["01:00"], preset: null, claude: true, next: "2026-09-27T01:00:00Z", last_run: null, last_status: null },
      { kind: "prepare", enabled: true, every_minutes: null, at: ["02:00"], preset: null, claude: true, next: "2026-09-27T02:00:00Z", last_run: null, last_status: null },
      { kind: "prune", enabled: true, every_minutes: 10080, at: [], preset: null, claude: false, next: "2026-09-28T03:00:00Z", last_run: null, last_status: null },
    ],
    catch_up: null,
    paused: null,
    inbox_ready: false,
    ...over,
  };
}

export const EMPTY_QUEUE: Queue = { kind: "score", items: [], total: 0, excluded: [], excluded_total: 0 };

export interface ApiData {
  meta?: Meta;
  current?: CurrentRun | null;
  schedule?: Schedule;
  history?: HistoryPage | ((url: URL) => HistoryPage);
  queue?: Queue | ((kind: string) => Queue);
  detail?: Record<string, RunDetail>;
  /** POST answers by path ("/api/runs", "/api/runs/cancel", ...); a function sees the parsed body. */
  post?: Record<string, unknown | ((body: unknown) => unknown)>;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

export function mockApi(data: ApiData = {}) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: string, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://127.0.0.1");
    const method = (init.method ?? "GET").toUpperCase();
    const body = typeof init.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    calls.push({ method, url: url.pathname + url.search, body, headers: (init.headers ?? {}) as Record<string, string> });
    const p = url.pathname;
    if (method === "POST") {
      const answer = data.post?.[p];
      if (answer === undefined) return json({ detail: `no fake for POST ${p}` }, 500);
      const out = typeof answer === "function" ? (answer as (b: unknown) => unknown)(body) : answer;
      if (out instanceof Response) return out;
      return json(out);
    }
    if (p === "/api/meta") return json(data.meta ?? META);
    if (p === "/api/status") return json({});
    if (p === "/api/runs/current") return json(data.current ?? null);
    if (p === "/api/schedule") return json(data.schedule ?? schedule());
    if (p.startsWith("/api/runs/queue/")) {
      const kind = p.split("/").at(-1)!;
      const q = typeof data.queue === "function" ? data.queue(kind) : (data.queue ?? { ...EMPTY_QUEUE, kind });
      return json(q);
    }
    if (p === "/api/runs") {
      const h = typeof data.history === "function" ? data.history(url) : (data.history ?? { runs: [], next_cursor: null });
      return json(h);
    }
    const m = /^\/api\/runs\/([^/]+)$/.exec(p);
    if (m) {
      const d = data.detail?.[decodeURIComponent(m[1]!)];
      return d ? json(d) : json({ detail: "no run" }, 404);
    }
    return json({ detail: "not found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, posts: () => calls.filter((c) => c.method === "POST") };
}

export function renderRoute(routes: RouteObject[], path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...view, router, qc };
}

/** jsdom has no layout: give scroll containers a size so the virtualized lists render their rows. */
export function fakeLayout() {
  const h = vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(480);
  const w = vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(600);
  return () => {
    h.mockRestore();
    w.mockRestore();
  };
}
