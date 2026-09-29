import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { FakeEventSource } from "../../test/fakeEventSource";
import { ACTION_HELP } from "../job-detail/actionHelp";
import { RunDetailPage } from "./RunDetailPage";
import { RunsPage } from "./RunsPage";
import { fakeLayout, mockApi, renderRoute, schedule, type ApiData } from "./testUtils";
import type { CurrentRun, RunRecord } from "./types";

// axe over a whole screen is slow on a busy machine; the default 5 s is too tight for it.
vi.setConfig({ testTimeout: 20_000 });

const routes = [
  { path: "/automation", element: <RunsPage /> },
  { path: "/automation/runs/:runId", element: <RunDetailPage /> },
  { path: "/settings/runs", element: <p>Settings › Runs</p> },
];

function current(over: Partial<CurrentRun> = {}): CurrentRun {
  const base: CurrentRun = {
    id: "20260926-020000-prepare-ab12",
    detail: "",
    attempts: [],
    holder: null,
    kind: "prepare",
    trigger: "manual",
    budget: { preset: "medium", max_jobs: 5, max_minutes: 90 },
    status: "running",
    state: "running",
    stop_reason: null,
    started_at: "2026-09-26T02:00:00Z",
    ended_at: null,
    duration_s: null,
    counters: { attempted: 1, ok: 1 },
    scheduled: false,
    current_job: "b2",
    used: { jobs: 1, max_jobs: 5, minutes: 21, max_minutes: 90 },
    cap: { date: "2026-09-25", cap: 15, base: 15, multiplier: 1, applied: 0, remaining: 15, reached: false },
    jobs: [
      {
        job_id: "a1",
        company: "Acme Robotics",
        title: "Backend Engineer",
        state: "done",
        outcome: "ok",
        duration_s: 432,
        detail: "",
        steps: ["Score", "Tailor", "Cover", "QA"].map((name) => ({ name, state: "done" as const })),
      },
      {
        job_id: "b2",
        company: "Globex",
        title: "Platform Engineer",
        state: "active",
        outcome: null,
        duration_s: null,
        detail: "",
        steps: [
          { name: "Score", state: "done" },
          { name: "Tailor", state: "done" },
          { name: "Cover", state: "active" },
          { name: "QA", state: "pending" },
        ],
      },
      {
        job_id: "c3",
        company: "Initech",
        title: "Data Engineer",
        state: "queued",
        outcome: null,
        duration_s: null,
        detail: "",
        steps: ["Score", "Tailor", "Cover", "QA"].map((name) => ({ name, state: "pending" as const })),
      },
    ],
  };
  return Object.assign(base, over);
}

function run(over: Partial<RunRecord>): RunRecord {
  const base: RunRecord = {
    id: "20260925-010000-score-aaaa",
    kind: "score",
    trigger: "schedule",
    budget: { preset: "small", max_jobs: 3, max_minutes: 30 },
    status: "done",
    state: "done",
    stop_reason: "completed",
    detail: "",
    started_at: "2026-09-25T01:00:00Z",
    ended_at: "2026-09-25T01:07:00Z",
    duration_s: 420,
    counters: { attempted: 3, ok: 3 },
  };
  return Object.assign(base, over);
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

function open(data: ApiData = {}, path = "/automation") {
  const api = mockApi(data);
  const view = renderRoute(routes, path);
  return { api, ...view };
}

describe("Runs page", () => {
  it("keeps manual runs and run history under a collapsed Advanced section", async () => {
    open();
    const advanced = screen.getByText("Advanced").closest("details")!;
    expect(advanced).not.toHaveAttribute("open");
    expect(within(advanced).getByText(/uses your Claude Code subscription/)).toBeInTheDocument();
    expect(await within(advanced).findByRole("heading", { name: "Start a run", hidden: true })).toBeInTheDocument();
    expect(await within(advanced).findByRole("heading", { name: "No runs yet", hidden: true })).toBeInTheDocument();
    expect(within(advanced).queryByText(/Scheduler not installed/)).toBeNull(); // schedule stays up top
  });

  it("opens Advanced when the URL already picks a run kind (deep link to a manual run or history filter)", () => {
    open({}, "/automation?kind=score");
    expect(screen.getByText("Advanced").closest("details")).toHaveAttribute("open");
  });

  it("shows empty states, never invented data, when nothing has run", async () => {
    const { container } = open();
    expect(screen.getByRole("heading", { level: 1, name: "Automation" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Nothing running" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "No runs yet" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Nothing to score" })).toBeInTheDocument();
    expect(screen.getByText(/nothing is skipped/)).toBeInTheDocument();
    expect(screen.getByText("Scheduler not installed: nothing runs on its own")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows the running batch: meters, job rows with step pills, and the live log", async () => {
    const { container } = open({ current: current() });
    expect(await screen.findByRole("heading", { name: "Prepare · manual" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Jobs prepared" })).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByRole("progressbar", { name: "Time budget" })).toHaveAttribute("aria-valuemax", "90");
    expect(screen.getByRole("progressbar", { name: "Daily apply cap" })).toBeInTheDocument();
    const jobs = within(screen.getByRole("list", { name: "Jobs in this run" })).getAllByRole("listitem");
    expect(jobs).toHaveLength(3);
    expect(within(jobs[1]!).getByText("Globex")).toBeInTheDocument();
    expect(jobs[1]!).toHaveTextContent("Cover in progress");
    expect(jobs[2]!).toHaveTextContent("queued");
    const es = FakeEventSource.last;
    expect(es.url).toBe("/api/runs/20260926-020000-prepare-ab12/stream");
    act(() => es.dispatch("event", { type: "assistant", text: "Tailoring the résumé", attempt: 2 }));
    expect(await within(screen.getByRole("log", { name: "Live run output" })).findByText("Tailoring the résumé")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("names a skipped step (a cover letter the tier rule left out)", async () => {
    const base = current();
    const jobs = base.jobs.map((j) =>
      j.state === "active"
        ? { ...j, steps: [{ name: "Score", state: "done" as const }, { name: "Tailor", state: "done" as const },
            { name: "Cover", state: "skipped" as const }, { name: "QA", state: "active" as const }] }
        : j,
    );
    open({ current: { ...base, jobs } });
    const rows = within(await screen.findByRole("list", { name: "Jobs in this run" })).getAllByRole("listitem");
    expect(rows[1]!).toHaveTextContent("Cover skipped");
    expect(rows[1]!).toHaveTextContent("QA in progress");
  });

  it("cancels after a confirm, then says it stops at the next safe point", async () => {
    const user = userEvent.setup();
    const { api } = open({ current: current(), post: { "/api/runs/cancel": { status: "cancelling", run_id: "x", pid: 1 } } });
    await user.click(await screen.findByRole("button", { name: "Cancel run" }));
    const dialog = screen.getByRole("alertdialog", { name: /Cancel this run/ });
    expect(within(dialog).getByRole("button", { name: "Keep running" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Pause all runs" })).toHaveAttribute("title", ACTION_HELP.pause);
    await user.click(within(dialog).getByRole("button", { name: "Cancel run" }));
    expect(await screen.findByText("Cancelling at the next safe point…")).toBeInTheDocument();
    const post = api.posts()[0]!;
    expect(post.url).toBe("/api/runs/cancel");
    expect(post.body).toEqual({ run_id: "20260926-020000-prepare-ab12" });
    expect(post.headers["X-CareerOS"]).toBe("1");
  });

  it("returns focus to Cancel run when the confirm is dismissed with Escape", async () => {
    const user = userEvent.setup();
    open({ current: current() });
    await user.click(await screen.findByRole("button", { name: "Cancel run" }));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Cancel run" })).toHaveFocus();
  });

  it("offers Pause all instead of Cancel for a scheduled batch", async () => {
    open({ current: current({ trigger: "schedule", scheduled: true }) });
    expect(await screen.findByText("Use Pause all to stop a scheduled run")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel run" })).toBeNull();
  });

  it("dry-runs first by default: shows the selection, then starts", async () => {
    const user = userEvent.setup();
    const selection = {
      dry_run: true,
      kind: "prepare",
      budget: { preset: "medium", max_jobs: 5, max_minutes: 90 },
      candidates: 4,
      selected: [
        {
          job_id: "q1",
          company: "Initech",
          title: "Platform Engineer",
          rank: 1,
          score: 60,
          fit: 88,
          why: "",
          reasons: [{ code: "fit", text: "fit 88", points: 44 }],
        },
      ],
    };
    const { api, router } = open({
      post: {
        "/api/runs": (b: unknown) =>
          (b as { dry_run: boolean }).dry_run ? selection : { kind: "prepare", started: true, pid: 7 },
      },
    });
    expect(await screen.findByRole("radio", { name: /Medium/ })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Show the selection" }));
    const region = await screen.findByRole("region", { name: "Dry run selection" });
    expect(within(region).getByText("1 of 4 jobs would run")).toBeInTheDocument();
    expect(within(region).getByText("Fit 88 +44")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start prepare run" })).toHaveAttribute("title", ACTION_HELP.startRun);
    await user.click(screen.getByRole("button", { name: "Start prepare run" }));
    expect(await screen.findByText("Prepare run started.")).toBeInTheDocument();
    expect(api.posts().map((c) => c.body)).toEqual([
      { kind: "prepare", preset: "medium", dry_run: true },
      { kind: "prepare", preset: "medium", dry_run: false },
    ]);
    await user.click(screen.getByRole("radio", { name: /Small/ }));
    expect(router.state.location.search).toContain("budget=small");
  });

  it("keeps the run kind in the URL and sends custom limits", async () => {
    const user = userEvent.setup();
    const { api, router } = open({ post: { "/api/runs": { kind: "score", started: true, pid: 7 } } });
    const kinds = await screen.findByRole("radiogroup", { name: "Run type" });
    await user.click(within(kinds).getByRole("radio", { name: "Score" }));
    expect(router.state.location.search).toContain("kind=score");
    await user.click(screen.getByRole("radio", { name: /Custom/ }));
    await user.type(screen.getByRole("spinbutton", { name: "Jobs" }), "3");
    await user.type(screen.getByRole("spinbutton", { name: "Minutes" }), "20");
    await user.click(screen.getByRole("switch", { name: "Dry run first" }));
    await user.click(screen.getByRole("button", { name: "Start score run" }));
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    expect(api.posts()[0]!.body).toEqual({ kind: "score", preset: "custom", max_jobs: 3, max_minutes: 20, dry_run: false });
    expect(screen.getByText(/Never applies/)).toBeInTheDocument();
  });

  it("forgets a dry-run selection when the custom limits change", async () => {
    const user = userEvent.setup();
    const selection = { dry_run: true, kind: "score", budget: {}, candidates: 1, selected: [] };
    const { api } = open({ post: { "/api/runs": selection } }, "/automation?kind=score&budget=custom");
    await user.type(await screen.findByRole("spinbutton", { name: "Jobs" }), "3");
    await user.click(screen.getByRole("button", { name: "Show the selection" }));
    expect(await screen.findByRole("region", { name: "Dry run selection" })).toBeInTheDocument();
    await user.type(screen.getByRole("spinbutton", { name: "Jobs" }), "0");
    expect(screen.queryByRole("region", { name: "Dry run selection" })).toBeNull();
    expect(screen.getByRole("button", { name: "Show the selection" })).toBeEnabled();
    await user.type(screen.getByRole("spinbutton", { name: "Minutes" }), "5");
    expect(api.posts()).toHaveLength(1);
  });

  it("refuses a fractional job count before asking the server", async () => {
    const user = userEvent.setup();
    const { api } = open({ post: { "/api/runs": { started: true } } }, "/automation?kind=score&budget=custom");
    const jobs = await screen.findByRole("spinbutton", { name: "Jobs" });
    expect(jobs).toHaveAttribute("step", "1");
    await user.type(jobs, "2.5");
    await user.click(screen.getByRole("button", { name: "Show the selection" }));
    expect(await screen.findByText("Jobs must be a whole number, 1 or more.")).toBeInTheDocument();
    expect(api.posts()).toHaveLength(0);
  });

  it("disables Inbox with a reason until inbox sync is set up; steps start directly", async () => {
    const user = userEvent.setup();
    const { api } = open({ post: { "/api/runs/steps/scout": { kind: "scout", started: true, pid: 3 } } }, "/automation?kind=inbox");
    const start = await screen.findByRole("button", { name: "Start inbox run" });
    expect(start).toBeDisabled();
    expect(start).toHaveAccessibleDescription(/Inbox sync isn't set up yet/);
    await user.click(within(screen.getByRole("radiogroup", { name: "Run type" })).getByRole("radio", { name: "Scout" }));
    expect(screen.queryByRole("group", { name: "Budget" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Start scout run" }));
    await waitFor(() => expect(api.posts()[0]?.url).toBe("/api/runs/steps/scout"));
  });

  it("shows a server refusal in plain words", async () => {
    const user = userEvent.setup();
    open(
      {
        post: {
          "/api/runs": new Response(JSON.stringify({ detail: "Runs are paused. Resume them first." }), { status: 409 }),
        },
      },
      "/automation?kind=score",
    );
    await user.click(await screen.findByRole("switch", { name: "Dry run first" }));
    await user.click(screen.getByRole("button", { name: "Start score run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Runs are paused. Resume them first.");
  });

  it("pauses all runs until resumed (Recommended); Escape closes the menu and returns focus", async () => {
    const user = userEvent.setup();
    const { api } = open({ post: { "/api/runs/pause": { paused_at: "x", until: null, reason: "" } } });
    const button = await screen.findByRole("button", { name: "Pause all runs" });
    await user.click(button);
    const dialog = screen.getByRole("dialog", { name: "Pause all runs" });
    expect(within(dialog).getByRole("radio", { name: /Until I resume/ })).toBeChecked();
    // ui.pause_until_tomorrow_at from /api/meta ("08:00" here), shown in the locale's clock style
    expect(within(dialog).getByRole("radio", { name: /^Until tomorrow, 0?8:00( AM)?$/ })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(button).toHaveFocus();
    await user.click(button);
    await user.click(within(screen.getByRole("dialog")).getByRole("radio", { name: "For 1 hour" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Pause all runs" }));
    await waitFor(() => expect(api.posts()[0]?.body).toEqual({ until: "+1h" }));
  });

  it("shows the paused banner with Resume", async () => {
    const user = userEvent.setup();
    const { api } = open({
      schedule: schedule({ paused: { paused_at: "2026-09-26T10:00:00Z", until: null, reason: "" } }),
      post: { "/api/runs/resume": { resumed: true } },
    });
    expect(await screen.findByText("All runs paused until you resume")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume all runs" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(api.posts()[0]?.url).toBe("/api/runs/resume"));
  });

  it("offers catch-up for missed runs, and skipping them after a confirm", async () => {
    const user = userEvent.setup();
    const { api } = open({
      schedule: schedule({
        catch_up: { created_at: "x", kinds: { score: { first_missed: "2026-09-25T01:00:00Z", slots: 2 } } },
      }),
      post: { "/api/runs/catch-up": { pending: true } },
    });
    const banner = await screen.findByRole("region", { name: "Missed runs" });
    expect(within(banner).getByText("Missed 2 runs while your Mac was off")).toBeInTheDocument();
    await user.click(within(banner).getByRole("button", { name: "Catch up now" }));
    await waitFor(() => expect(api.posts()[0]?.body).toEqual({ dismiss: false }));
    await user.click(within(banner).getByRole("button", { name: "Skip missed runs" }));
    await user.keyboard("{Escape}");
    expect(within(banner).getByRole("button", { name: "Skip missed runs" })).toHaveFocus();
    await user.click(within(banner).getByRole("button", { name: "Skip missed runs" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Skip missed runs" }));
    await waitFor(() => expect(api.posts()[1]?.body).toEqual({ dismiss: true }));
  });

  it("lists history with stop-reason chips and fix text; the kind filter lives in the URL", async () => {
    const user = userEvent.setup();
    const { api, router } = open({
      history: (url) =>
        url.searchParams.get("kind") === "score"
          ? { runs: [run({})], next_cursor: null }
          : {
              runs: [
                run({ id: "r3", kind: "prepare", stop_reason: "usage_limit", counters: { attempted: 2, ok: 1 } }),
                run({ id: "r2", kind: "scout", trigger: "manual", state: "interrupted", stop_reason: "interrupted", detail: "" }),
                run({}),
              ],
              next_cursor: "r1",
            },
    });
    const list = await screen.findByRole("list", { name: "Runs" });
    const rows = within(list).getAllByRole("link");
    expect(rows[0]).toHaveTextContent("Prepare · scheduled");
    expect(rows[0]).toHaveTextContent("Usage limit");
    expect(rows[0]).toHaveTextContent("1 of 2 prepared");
    expect(rows[0]).toHaveTextContent("retries at the next slot");
    expect(rows[1]).toHaveTextContent("Interrupted");
    expect(rows[2]).toHaveTextContent("Done");
    expect(rows[2]).toHaveAttribute("href", "/automation/runs/20260925-010000-score-aaaa");
    expect(screen.getByRole("navigation", { name: "Runs pages" })).toHaveTextContent(/of \d+\+/);
    await user.click(within(screen.getByRole("radiogroup", { name: "Run kind" })).getByRole("radio", { name: "Score" }));
    expect(router.state.location.search).toContain("history=score");
    await waitFor(() => expect(api.calls.some((c) => c.url === "/api/runs?kind=score")).toBe(true));
  });

  it("explains the queue with why chips and keeps excluded jobs in a collapsed group", async () => {
    open({
      queue: (kind) => ({
        kind: kind as "score",
        total: 1,
        items: [
          {
            job_id: "j1",
            company: "Initech",
            title: "Platform Engineer",
            rank: 1,
            score: 85,
            fit: null,
            why: "",
            reasons: [
              { code: "fresh", text: "posted 20h ago", points: 60 },
              { code: "dream", text: "dream company", points: 25 },
            ],
          },
        ],
        excluded: [{ job_id: "j2", reason: "pruned", company: "Globex", title: "SRE" }],
        excluded_total: 1,
      }),
    });
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Posted 20h ago +60")).toBeInTheDocument();
    expect(within(table).getByText("Dream company +25")).toBeInTheDocument();
    expect(within(table).getByText("85")).toBeInTheDocument();
    expect(screen.getByText("Not in queue (1)")).toBeInTheDocument();
    expect(screen.queryByText(/nothing is skipped/)).toBeNull();
    expect(screen.getByText("pruned")).not.toBeVisible();
  });

  it("describes the schedule and installs the LaunchAgent after a confirm", async () => {
    const user = userEvent.setup();
    const { api } = open({ post: { "/api/schedule/install": { loaded: true } } });
    expect(await screen.findByText("Prune + storage check")).toBeInTheDocument();
    expect(screen.getByText(/Every 3 h/)).toBeInTheDocument();
    expect(screen.getByText(/off until inbox sync is ready/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit schedule" })).toHaveAttribute("href", "/settings/runs");
    await user.click(screen.getByRole("button", { name: "Install" }));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Install" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Install" }));
    await user.click(within(screen.getByRole("alertdialog", { name: /Install the scheduler/ })).getByRole("button", { name: "Install" }));
    await waitFor(() => expect(api.posts()[0]?.url).toBe("/api/schedule/install"));
    expect(await screen.findByText("Scheduler installed.")).toBeInTheDocument();
  });

  it("says when the scheduler installed but claude is not on PATH", async () => {
    const user = userEvent.setup();
    const warning = "`claude` is not on PATH; scheduled score and prepare runs will stop with doctor_failed";
    open({ post: { "/api/schedule/install": { loaded: true, warning } } });
    await user.click(await screen.findByRole("button", { name: "Install" }));
    await user.click(within(screen.getByRole("alertdialog", { name: /Install the scheduler/ })).getByRole("button", { name: "Install" }));
    expect(await screen.findByText("Scheduler installed with a warning.")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Scheduler warning" })).toHaveTextContent(warning);
    expect(screen.queryByText("Scheduler installed.")).not.toBeInTheDocument();
  });
});

describe("Run detail", () => {
  it("shows the attempts and run.log of a finished run", async () => {
    const { container } = open(
      {
        detail: {
          r9: {
            ...run({ id: "r9", kind: "prepare", stop_reason: "timeout", counters: { attempted: 1, ok: 0 } }),
            attempts: [
              { n: 1, job_id: "j1", company: "Initech", title: "Platform Engineer", outcome: "timeout", duration_s: 2700, session_id: "sess-1", detail: "no result" },
            ],
            log: "- 2026-09-25 01:00:00 [run] start prepare\n- 2026-09-25 01:45:00 [run] stop timeout\n",
          },
        },
      },
      "/automation/runs/r9",
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Prepare run" })).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("Initech")).toBeInTheDocument();
    expect(within(table).getByText("Timeout")).toBeInTheDocument();
    expect(within(table).getByText("sess-1")).toBeInTheDocument();
    expect(within(screen.getByRole("log", { name: "Run log" })).getByText(/stop timeout/)).toBeInTheDocument();
    expect(screen.getByText("Job timed out")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("says so when the run does not exist", async () => {
    open({}, "/automation/runs/nope");
    expect(await screen.findByRole("heading", { level: 1, name: "Run not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All runs" })).toHaveAttribute("href", "/automation");
  });
});
