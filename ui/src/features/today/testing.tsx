import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";
import { ToastProvider } from "../../kit/Toast";
import { META } from "../../test/mockApi";
import type { ActionItem, Meta, TodayData, TodayStatus } from "./types";

// Test-only helpers: fictional fixtures shaped like the server's JSON and a fetch mock routed by method + path.

export const NOW = new Date("2026-09-25T10:00:00Z"); // Friday

/** An Action Item with every field the server sends; tests override what they care about. */
export function actionItem(over: Partial<ActionItem> & Pick<ActionItem, "id" | "company" | "what">): ActionItem {
  return {
    created: null, job_id: null, role: "", type: "other", link: "", priority: "", needs: "", done: false,
    done_date: null, due: null, due_date_only: false, due_reason: null, bucket: "nodate", level: "none",
    scam_actions: false, ...over,
  };
}

export const actions: ActionItem[] = [
  actionItem({ id: "11", job_id: "j-acme", company: "Acme Robotics", role: "Software Engineer, Platform",
    what: "Tier A: review résumé, cover letter and answers, then submit yourself", type: "review", priority: "H",
    needs: "laptop", link: "https://jobs.example.com/acme/123", created: "2026-09-20T09:00:00Z",
    due: "2026-10-03T12:00:00Z", due_reason: "posting closes", level: "later", bucket: "later" }),
  actionItem({ id: "12", job_id: "j-globex", company: "Globex", role: "Backend Engineer",
    what: "Interview invite: pick a slot", type: "send_email", priority: "H", needs: "phone",
    link: "https://mail.example.org/thread/1", created: "2026-09-24T09:00:00Z",
    due: "2026-09-26T15:00:00Z", due_reason: "reply within 48 hours", level: "soon", bucket: "tomorrow" }),
  actionItem({ id: "13", job_id: "j-initech", company: "Initech", role: "Data Engineer",
    what: "Add a number to the dashboard bullet", type: "profile_gap", priority: "L", needs: "anytime",
    link: "profile/master.yaml", created: "2026-09-22T09:00:00Z", due: null, due_reason: null, level: "none", bucket: "nodate" }),
  actionItem({ id: "14", job_id: "j-hooli", company: "Hooli", role: "Software Engineer",
    what: "Tailor the message yourself", type: "send_linkedin", priority: "M", needs: "phone",
    link: "", created: "2026-09-21T09:00:00Z", due: "2026-09-24T09:00:00Z", due_reason: "note was due", level: "overdue", bucket: "overdue" }),
];

export const today: TodayData = { actions, prepare_queue: { total: 3, error: null } };

export const meta: Meta = {
  ...META,
  clean_stops: [],
  stop_reasons: [],
  statuses: ["found", "queued", "needs_review", "applied", "screening", "interview", "offer", "rejected"],
  presets: { names: ["small", "medium", "large"], recommended: "medium", current: "small", values: {} },
  pipeline: { columns: [], closed: [], card_limit: 5 },
  ui: { theme: "system", undo_seconds: 8, page_size: 50, due_soon_hours: 48, pause_until_tomorrow_at: "08:00" },
};

export const status: TodayStatus = {
  now: NOW.toISOString(),
  tiles: {
    applied_week: {
      value: 2, since: "2026-09-21T00:00:00+00:00", daily_cap: 15,
      rows: [
        { job_id: "j1", company: "Umbrella Labs", role: "Platform Engineer", detail: "applied", when: "2026-09-21T10:00:00Z" },
        { job_id: "j2", company: "Vandelay Industries", role: "Engineer", detail: "screening", when: "2026-09-22T10:00:00Z" },
      ],
    },
    needs_you: { value: 4, high: 2, rows: actions.slice(0, 2) },
    interviews: {
      value: 1,
      rows: [{ job_id: "j3", company: "Globex", role: "Backend Engineer", detail: "interview", when: "2026-09-24T10:00:00Z" }],
    },
    response_rate: {
      rate: 7 / 41, responded: 7, applied: 41, days: 30,
      definition: "applications in the last 30 days that reached screening, interview, offer or rejected",
      breakdown: [
        { status: "interview", count: 2, companies: ["Globex", "Hooli"] },
        { status: "rejected", count: 5, companies: ["Initech"] },
        { status: "no_reply", count: 34, companies: [] },
      ],
      rows: [],
    },
  },
  pipeline: {
    columns: [
      { name: "Found", statuses: ["found"], count: 412 },
      { name: "Queued", statuses: ["queued"], count: 23 },
      { name: "Applied", statuses: ["applied"], count: 41 },
      { name: "Offer", statuses: ["offer"], count: 0 },
    ],
    closed: { count: 0, by_status: {} },
  },
  counts: { jobs: 476, action_items_open: 4, inbox: 0, contacts: 0 },
  recent_runs: [
    { trigger: null, ended_at: null, duration_s: null, attempted: null, ok: null, failed: null, id: "r1", kind: "scout", status: "ok", stop_reason: "completed", detail: "38 new of 412 scanned",
      started_at: "2026-09-25T08:02:00Z", interrupted: false },
    { trigger: null, ended_at: null, duration_s: null, failed: null, id: "r2", kind: "prepare", status: "running", stop_reason: null, detail: "", started_at: "2026-09-25T09:14:00Z",
      attempted: 2, ok: 1, interrupted: true },
    { trigger: null, ended_at: null, duration_s: null, attempted: null, ok: null, failed: null, id: "r3", kind: "score", status: "done", stop_reason: "mystery_reason", detail: "",
      started_at: "2026-09-21T16:40:00Z", interrupted: false },
  ],
  paused: null,
  catch_up: null,
  schedule: {
    last_tick: "2026-09-25T09:55:00Z",
    next: { scout: "2026-09-25T12:00:00Z", score: "2026-09-26T01:00:00Z", prepare: "2026-09-26T02:00:00Z",
            inbox_sync: null, prune: "2026-09-27T03:00:00Z" },
    error: null,
  },
  index: { indexed_at: "2026-09-25T09:59:00Z" },
};

type Reply = unknown | { $status: number; body: unknown } | (() => Promise<Response> | Response);
export type Routes = Record<string, Reply>;

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Headers;
}

/** Stubs fetch: `routes["GET /api/today"]` is the JSON reply (or `{ $status, body }`, or a function returning a
 * Response). Unknown routes answer 404. Returns the list of calls made. */
export function mockApi(routes: Routes): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = (init.method ?? "GET").toUpperCase();
      const path = url.split("?")[0]!;
      calls.push({
        method,
        path,
        body: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
        headers: new Headers(init.headers),
      });
      const r = routes[`${method} ${path}`];
      if (r === undefined) return json({ detail: "Not found" }, 404);
      if (typeof r === "function") return (r as () => Response)();
      if (r && typeof r === "object" && "$status" in r) {
        const x = r as { $status: number; body: unknown };
        return json(x.body, x.$status);
      }
      return json(r);
    }),
  );
  return calls;
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

export const defaultRoutes = (): Routes => ({
  "GET /api/status": status,
  "GET /api/today": today,
  "GET /api/meta": meta,
});

export function renderWithApp(ui: ReactNode, { path = "/" }: { path?: string } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter([{ path: "/", element: ui }, { path: "*", element: <p>elsewhere</p> }], {
    initialEntries: [path],
  });
  const utils = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...utils, router, qc };
}
