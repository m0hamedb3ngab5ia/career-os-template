import { vi } from "vitest";

// A tiny fetch router for screen tests: match "METHOD /path" (the path without the query string, or a RegExp on
// the full URL) and answer with JSON, a status + JSON body, or a raw Response. Every call is recorded.

export interface Call {
  method: string;
  url: string;
  path: string;
  search: URLSearchParams;
  body: unknown;
  headers: Record<string, string>;
}

export type Reply = unknown | { status: number; body?: unknown } | Response;
export type Handler = (call: Call) => Reply | Promise<Reply>;
export type Routes = Record<string, Reply | Handler>;

function isStatusReply(r: unknown): r is { status: number; body?: unknown } {
  return !!r && typeof r === "object" && "status" in r && typeof (r as { status: unknown }).status === "number" &&
    Object.keys(r).every((k) => k === "status" || k === "body");
}

function toResponse(r: Reply): Response {
  if (r instanceof Response) return r;
  const { status, body } = isStatusReply(r) ? r : { status: 200, body: r };
  return new Response(body === undefined ? "" : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export function mockApi(routes: Routes) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const u = new URL(url, "http://localhost");
    const method = (init.method ?? "GET").toUpperCase();
    const headers = Object.fromEntries(new Headers(init.headers).entries());
    let body: unknown = undefined;
    if (typeof init.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    }
    const call: Call = { method, url, path: u.pathname, search: u.searchParams, body, headers };
    calls.push(call);
    const key = `${method} ${u.pathname}`;
    const hit = routes[key];
    if (hit === undefined) return toResponse({ status: 404, body: { detail: `no mock for ${key}` } });
    const reply = typeof hit === "function" ? await (hit as Handler)(call) : hit;
    return toResponse(reply);
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    calls,
    fetchMock,
    /** Calls to one "METHOD /path". */
    callsTo: (key: string) => calls.filter((c) => `${c.method} ${c.path}` === key),
  };
}
