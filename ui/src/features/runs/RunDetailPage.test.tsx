import { act, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { FakeEventSource } from "../../test/fakeEventSource";
import { RunDetailPage } from "./RunDetailPage";
import { fakeLayout, mockApi, renderRoute } from "./testUtils";
import type { RunDetail } from "./types";

// axe over a whole screen is slow on a busy machine; the default 5 s is too tight for it.
vi.setConfig({ testTimeout: 20_000 });

const routes = [
  { path: "/runs", element: <p>All runs</p> },
  { path: "/runs/:runId", element: <RunDetailPage /> },
];

function detail(over: Partial<RunDetail> = {}): RunDetail {
  return {
    id: "r1",
    kind: "score",
    trigger: "manual",
    status: "running",
    state: "running",
    stop_reason: null,
    started_at: "2026-09-25T01:00:00Z",
    ended_at: null,
    duration_s: null,
    counters: { attempted: 1, ok: 1 },
    attempts: [
      { n: 1, job_id: "j1", company: "Initech", title: "Platform Engineer", outcome: "ok", duration_s: 60 },
    ].map((a) => ({ ...a, session_id: null, detail: "" })),
    log: "",
    ...over,
  };
}

let restoreLayout: () => void;
beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  restoreLayout = fakeLayout();
});
afterEach(() => {
  restoreLayout();
  vi.unstubAllGlobals();
});

describe("RunDetailPage (live run)", () => {
  it("streams output into a log that is summarised for screen readers, with no axe violations", async () => {
    mockApi({ detail: { r1: detail() } });
    const { container } = renderRoute(routes, "/runs/r1");
    expect(await screen.findByRole("heading", { level: 1, name: "Score run" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Live output" })).toBeInTheDocument();
    const es = FakeEventSource.last;
    expect(es.url).toBe("/api/runs/r1/stream");
    act(() => {
      es.dispatch("event", { type: "log", text: "scoring j2", attempt: 2 });
      es.dispatch("event", { type: "log", text: "failed j2", attempt: 2, error: true });
    });
    const log = screen.getByRole("log", { name: "Live run output" });
    expect(await within(log).findByText("failed j2")).toBeInTheDocument();
    expect(log).toHaveAttribute("aria-live", "off");
    expect(screen.getByTestId("log-announcer")).toHaveTextContent(/new log line/);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("a finished run shows run.log without live announcements", async () => {
    mockApi({
      detail: {
        r2: detail({ id: "r2", status: "done", state: "done", stop_reason: "completed", log: "- start\n- stop\n" }),
      },
    });
    renderRoute(routes, "/runs/r2");
    const log = await screen.findByRole("log", { name: "Run log" });
    expect(within(log).getByText("- stop")).toBeInTheDocument();
    expect(screen.getByTestId("log-announcer")).toHaveTextContent("");
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});
