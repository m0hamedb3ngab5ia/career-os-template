import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../../app/routes";
import { FakeEventSource } from "../../../test/fakeEventSource";
import { META, mockApi, renderRoutes } from "../../../test/mockApi";
import type { Batch } from "./api";
import { confirmSentence, filterSummary } from "./copy";

// Fictional companies only.
const JOBS = [
  { job_id: "a1", company: "Acme Robotics", title: "Backend Engineer" },
  { job_id: "h1", company: "Hooli", title: "New Grad Engineer" },
  { job_id: "l1", company: "Initech", title: "Platform Engineer" },
];

function row(job_id: string, company: string, title: string) {
  return { job_id, company, title, status: "scored", fit: 80, score: 1, why: "fit 80, fresh", rank: 1, stage: "prepare",
    stages: ["prepare"], auto_submit: false, submit_reason: "" };
}

function preview(ids: string[], stop_at = "prepare"): Batch {
  const rows = JOBS.filter((j) => ids.includes(j.job_id) && j.job_id !== "l1").map((j) => row(j.job_id, j.company, j.title));
  return { dry_run: true, stop_at, kind: stop_at, selected: rows,
    excluded: ids.includes("l1") ? [{ job_id: "l1", reason: "LinkedIn application: apply yourself" }] : [] };
}

function setup(path = "/pipeline/batch/new?f.fit=75..", autoSubmit = false) {
  const calls = mockApi({
    "GET /api/meta": META,
    "GET /api/status": {},
    "GET /api/settings/runs": { values: { "runs.auto_submit.enabled": autoSubmit }, defaults: {}, files: {}, warnings: {}, version: "1",
      section: { id: "runs", title: "Runs", groups: [] } },
    "GET /api/jobs": ({ url }: { url: string }) => {
      const limit = Number(new URL(url, "http://x").searchParams.get("limit"));
      return { items: JOBS.slice(0, limit).map((j) => ({ ...j })), next_cursor: null, total: 127 };
    },
    "POST /api/batches": ({ body }: { body: { job_ids: string[]; stop_at: string; dry_run?: boolean } }) =>
      body.dry_run ? preview(body.job_ids, body.stop_at) : { ...preview(body.job_ids, body.stop_at), id: "b-1", dry_run: false, status: "ready" },
    "POST /api/batches/b-1/start": { ...preview(["a1"]), id: "b-1", dry_run: false, status: "ready" },
  });
  return { calls, ...renderRoutes(routes, path) };
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const opts = { timeout: 8000 };
const dry = (c: { body?: unknown }) => (c.body as { dry_run?: boolean } | undefined)?.dry_run;

describe("Batch builder", () => {
  it("shows the live count from /api/jobs with the same filters", { timeout: 20_000 }, async () => {
    const { calls } = setup();
    expect(await screen.findByText(/127 jobs match/, {}, opts)).toBeInTheDocument();
    const url = calls.find((c) => c.url.startsWith("/api/jobs"))!.url;
    expect(url).toContain("fit_min=75");
    expect(url).toContain("limit=25");
    expect(screen.getByText(/fit ≥ 75/)).toBeInTheDocument();
  });

  it("previews the exact list, lists exclusions with reasons, and deselects", { timeout: 20_000 }, async () => {
    setup();
    const list = await screen.findByRole("group", { name: "Jobs in this batch" }, opts);
    await within(list).findByRole("checkbox", { name: /Hooli/ }, opts);
    expect(screen.getByText("2 of 2 selected")).toBeInTheDocument();
    expect(screen.getByText(/LinkedIn application: apply yourself/)).toBeInTheDocument();
    await userEvent.click(within(list).getByRole("checkbox", { name: /Hooli/ }));
    expect(screen.getByText("1 of 2 selected")).toBeInTheDocument();
  });

  it("takes preselected ids from the URL instead of filters", { timeout: 20_000 }, async () => {
    const { calls } = setup("/pipeline/batch/new?ids=a1,h1");
    await screen.findByText("2 of 2 selected", {}, opts);
    expect(calls.some((c) => c.url.startsWith("/api/jobs"))).toBe(false);
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ job_ids: ["a1", "h1"], dry_run: true });
  });

  it("disables Submit when allowed with the reason while auto-submit is off", { timeout: 20_000 }, async () => {
    setup();
    const submit = await screen.findByRole("radio", { name: "Submit when allowed" }, opts);
    await waitFor(() => expect(submit).toBeDisabled());
    expect(submit).toHaveAccessibleDescription(/Auto-submit is off in Settings/);
  });

  it("enables Submit when allowed once auto-submit is on", { timeout: 20_000 }, async () => {
    setup(undefined, true);
    const submit = await screen.findByRole("radio", { name: "Submit when allowed" }, opts);
    await waitFor(() => expect(submit).toBeEnabled());
  });

  it("starts only from the confirm step, with the checked jobs", { timeout: 20_000 }, async () => {
    const { calls } = setup();
    await screen.findByText("2 of 2 selected", {}, opts);
    await userEvent.click(screen.getByRole("radio", { name: "Fill application, then ask me" }));
    await screen.findByText("2 of 2 selected", {}, opts);
    await userEvent.click(within(screen.getByRole("group", { name: "Jobs in this batch" })).getByRole("checkbox", { name: /Hooli/ }));
    expect(screen.queryByRole("button", { name: "Start batch" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Review and start" }));
    const confirm = screen.getByRole("region", { name: "Confirm batch" });
    expect(confirm).toHaveTextContent("Fill 1 application, then ask you · auto-submit off · Top choice staged · filters: fit ≥ 75");
    expect(calls.filter((c) => c.method === "POST" && !dry(c))).toHaveLength(0);
    await userEvent.click(within(confirm).getByRole("button", { name: "Start batch" }));
    expect(await screen.findByRole("link", { name: /Follow batch/ }, opts)).toHaveAttribute("href", "/pipeline/batch/b-1");
    const create = calls.find((c) => c.method === "POST" && c.url === "/api/batches" && !dry(c))!;
    expect(create.body).toMatchObject({ job_ids: ["a1"], stop_at: "fill" });
    expect(calls.some((c) => c.url === "/api/batches/b-1/start")).toBe(true);
  });
});

describe("copy", () => {
  it("summarises filters and the confirm sentence", () => {
    expect(filterSummary({ q: "", location: "", filters: { fit: { kind: "range", min: "75", max: "" },
      found_at: { kind: "range", min: "2026-09-21", max: "" } } })).toBe("fit ≥ 75, found since 2026-09-21");
    expect(confirmSentence(1, "score", "")).toBe("Score 1 job");
    expect(confirmSentence(23, "submit", "from your Jobs selection")).toBe(
      "Fill 23 applications and submit where your Settings allow · auto-submit on, within your rules and daily cap · Top choice staged · from your Jobs selection");
  });
});
