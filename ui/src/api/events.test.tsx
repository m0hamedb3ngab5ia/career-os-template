import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { keysForEvent, useLiveEvents } from "./events";

class FakeEventSource {
  static last: FakeEventSource | null = null;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  close() {
    this.closed = true;
  }
  emit(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }
}

afterEach(() => vi.unstubAllGlobals());

describe("keysForEvent", () => {
  it("maps event types to the query keys they make stale", () => {
    expect(keysForEvent({ type: "job", id: "abc" })).toEqual([["jobs"], ["job", "abc"], ["status"]]);
    expect(keysForEvent({ type: "run" })).toEqual([["runs"], ["status"]]);
    expect(keysForEvent({ type: "reindex" })).toEqual([[]]);
    expect(keysForEvent({ type: "something_new" })).toEqual([["status"]]);
  });
});

describe("useLiveEvents", () => {
  it("connects to /api/events, tracks the connection, and invalidates on messages", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result, unmount } = renderHook(() => useLiveEvents(), { wrapper });
    const es = FakeEventSource.last!;
    expect(es.url).toBe("/api/events");
    expect(result.current).toBe("connecting");
    act(() => es.onopen?.());
    expect(result.current).toBe("open");
    act(() => es.emit({ type: "action", id: "7" }));
    expect(spy).toHaveBeenCalledWith({ queryKey: ["actions"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["status"] });
    act(() => es.onerror?.());
    expect(result.current).toBe("reconnecting");
    unmount();
    expect(es.closed).toBe(true);
  });

  it("ignores malformed messages", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "invalidateQueries");
    renderHook(() => useLiveEvents(), {
      wrapper: ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>,
    });
    act(() => FakeEventSource.last!.onmessage?.(new MessageEvent("message", { data: "not json" })));
    expect(spy).not.toHaveBeenCalled();
  });
});
