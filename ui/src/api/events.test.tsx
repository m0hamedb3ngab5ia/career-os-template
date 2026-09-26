import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeEventSource } from "../test/fakeEventSource";
import { keysForChange, useLiveEvents } from "./events";

function setup() {
  vi.stubGlobal("EventSource", FakeEventSource);
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const hook = renderHook(() => useLiveEvents(), { wrapper });
  return { spy, hook };
}

beforeEach(() => {
  FakeEventSource.instances = [];
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("keysForChange", () => {
  it("maps a changed payload to the query keys it makes stale", () => {
    expect(keysForChange({ jobs: ["a1", "b2"], runs: [], actions: false, config: false, status: false })).toEqual([
      ["jobs"],
      ["job", "a1"],
      ["job", "b2"],
      ["contacts"],
      ["status"],
    ]);
    expect(keysForChange({ jobs: [], runs: ["r1"], actions: true, config: false, status: false })).toEqual([
      ["runs"],
      ["run", "r1"],
      ["status"],
      ["actions"],
    ]);
    expect(keysForChange({ jobs: [], runs: [], actions: false, config: true, status: false })).toEqual([
      ["meta"],
      ["settings"],
      ["status"],
    ]);
    expect(keysForChange({ status: true })).toEqual([["status"]]);
    expect(keysForChange({})).toEqual([]);
  });
});

describe("useLiveEvents", () => {
  it("connects, reports the state, and invalidates on `changed`", () => {
    const { spy, hook } = setup();
    const es = FakeEventSource.last;
    expect(es.url).toBe("/api/events");
    expect(hook.result.current).toBe("connecting");
    act(() => es.open());
    act(() => es.dispatch("hello", { indexed_at: "2026-09-26T12:00:00Z" }));
    expect(hook.result.current).toBe("open");
    expect(spy).not.toHaveBeenCalled();
    act(() => es.dispatch("changed", { jobs: [], runs: [], actions: true, config: false, status: false }));
    expect(spy).toHaveBeenCalledWith({ queryKey: ["actions"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["status"] });
    hook.unmount();
    expect(es.closed).toBe(true);
  });

  it("ignores malformed `changed` data", () => {
    const { spy } = setup();
    act(() => FakeEventSource.last.dispatch("changed", "not json"));
    expect(spy).not.toHaveBeenCalled();
  });

  it("refetches everything after a reconnect (a `hello` after the first)", () => {
    const { spy, hook } = setup();
    const es = FakeEventSource.last;
    act(() => es.dispatch("hello", {}));
    act(() => es.fail(false));
    expect(hook.result.current).toBe("reconnecting");
    act(() => es.dispatch("hello", {}));
    expect(hook.result.current).toBe("open");
    expect(spy).toHaveBeenCalledWith();
  });

  it("recreates a closed connection with backoff", () => {
    vi.useFakeTimers();
    const { hook } = setup();
    const first = FakeEventSource.last;
    act(() => first.fail(true));
    expect(first.closed).toBe(true);
    expect(hook.result.current).toBe("reconnecting");
    expect(FakeEventSource.instances).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeEventSource.instances).toHaveLength(2);
    act(() => FakeEventSource.last.fail(true));
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeEventSource.instances).toHaveLength(2);
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeEventSource.instances).toHaveLength(3);
    hook.unmount();
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeEventSource.instances).toHaveLength(3);
  });
});
