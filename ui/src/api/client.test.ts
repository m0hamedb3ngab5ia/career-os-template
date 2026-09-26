import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, apiSend } from "./client";

function mockFetch(body: unknown, status = 200) {
  const fn = vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("GETs JSON without the mutation header", async () => {
    const f = mockFetch({ ok: true });
    await expect(apiFetch("/api/health")).resolves.toEqual({ ok: true });
    const init = f.mock.calls[0]![1]!;
    expect(new Headers(init.headers).has("X-CareerOS")).toBe(false);
  });

  it("adds X-CareerOS and a JSON body on mutations", async () => {
    const f = mockFetch({ ok: true });
    await apiSend("POST", "/api/actions/7/done", { note: "x" });
    const [url, init] = f.mock.calls[0]! as [string, RequestInit];
    expect(url).toBe("/api/actions/7/done");
    expect(init.method).toBe("POST");
    const h = new Headers(init.headers);
    expect(h.get("X-CareerOS")).toBe("1");
    expect(h.get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ note: "x" }));
  });

  it("throws ApiError with the server's detail on failure", async () => {
    mockFetch({ detail: "runs.preset: must be one of small, medium" }, 422);
    const err = await apiSend("PUT", "/api/settings/runs", {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
    expect((err as ApiError).message).toContain("runs.preset");
  });
});
