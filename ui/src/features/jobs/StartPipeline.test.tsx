import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, type Call } from "../../test/apiMock";
import { renderApp } from "../../test/renderApp";
import { META, TABS_REPLY, job } from "./fixtures";

// pl plain, ta Tier A, li LinkedIn Easy Apply, lg LinkedIn-found with a Greenhouse URL, rd plain, fl flagged posting
const ROWS = [
  job({ job_id: "pl", company: "Plainco", tier: "B" }),
  job({ job_id: "ta", company: "Topco", tier: "A" }),
  job({ job_id: "li", company: "Linkco", tier: "B" }),
  job({ job_id: "lg", company: "Greenco", tier: "B" }),
  job({ job_id: "fl", company: "Flagco", tier: "B" }),
];
const TIER_A = "tier_a: never auto-submitted, stops at fill";
const READY = "setup not finished (readiness must-haves open): stops at prepare";
let notReady = false;
const FLAG = "flagged: hidden text asking to ignore instructions";

/** The server's caps (runs/batches.py _cap), mocked: the UI only shows what the preview says. */
function preview(body: { job_ids: string[]; stop_at: string; stops?: Record<string, string>; dry_run?: boolean }) {
  const selected = body.job_ids.filter((j) => j !== "fl").map((j) => {
    let stop = body.stops?.[j] ?? body.stop_at;
    let cap: string | undefined;
    if (j === "li" && stop !== "prepare") [stop, cap] = ["prepare", "LinkedIn: apply yourself on LinkedIn"];
    if (notReady && stop !== "prepare") [stop, cap] = ["prepare", READY];
    if (j === "ta" && stop === "submit") [stop, cap] = ["fill", TIER_A];
    const ok = stop === "submit";
    return { job_id: j, company: j, title: "t", status: "scored", score: 1, why: "", rank: 1, stage: "prepare", stages: [],
      stop_at: stop, ...(cap ? { cap } : {}), auto_submit: ok, submit_reason: ok ? "verdict allows" : `stop point ${stop}: never submits` };
  });
  const excluded = body.job_ids.includes("fl") ? [{ job_id: "fl", reason: FLAG }] : [];
  return { stop_at: body.stop_at, stops: body.stops, kind: "fill", selected, excluded, dry_run: !!body.dry_run,
    ...(body.dry_run ? {} : { id: "b-1", status: "ready" }) };
}

function setup(path: string) {
  const api = mockApi({
    "GET /api/status": {},
    "GET /api/meta": { ...META, ui: { ...META.ui, page_size: 10 } },
    "GET /api/jobs": { items: ROWS, total: ROWS.length, next_cursor: null },
    "GET /api/jobs/tabs": TABS_REPLY,
    "POST /api/batches": (c: Call) => preview(c.body as Parameters<typeof preview>[0]),
    "POST /api/batches/b-1/start": preview({ job_ids: ["pl"], stop_at: "fill" }),
    "GET /api/batches/b-1": preview({ job_ids: ["pl"], stop_at: "fill" }),
  });
  return { api, ...renderApp(path) };
}

class FakeEventSource {
  close() {}
  addEventListener() {}
  removeEventListener() {}
}
beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => {
  vi.unstubAllGlobals();
  notReady = false;
});

const opts = { timeout: 8000 };

describe("Start pipeline (REQ-117)", () => {
  it("is unavailable until jobs are ticked, with the reason", async () => {
    setup("/jobs");
    const btn = await screen.findByRole("button", { name: "Start pipeline" }, opts);
    expect(btn).toHaveAttribute("aria-disabled", "true");
    expect(btn).toHaveAccessibleDescription("Tick jobs first");
  });

  it("E2E-013-01: default Fill, plain set to Submit; caps shown with reasons; Start opens batch progress", { timeout: 30_000 }, async () => {
    const { api, router } = setup("/jobs?sel=pl,ta,li,lg,fl");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start pipeline" }, opts));
    const sheet = await screen.findByRole("region", { name: "Review pipeline" }, opts);
    expect(within(sheet).getByRole("radio", { name: /Fill/ })).toBeChecked();
    const row = (name: string) => within(sheet).getByRole("rowheader", { name }).closest("tr")!;

    await waitFor(() => expect(within(sheet).getByText(/LinkedIn: apply yourself on LinkedIn/)).toBeInTheDocument(), opts);
    const first = api.callsTo("POST /api/batches")[0]!.body as Record<string, unknown>;
    expect(first).toMatchObject({ job_ids: ["pl", "ta", "li", "lg", "fl"], stop_at: "fill", dry_run: true });
    expect(within(row("Linkco")).getByText("Prepare", { selector: "strong" })).toBeInTheDocument();
    expect(within(row("Greenco")).getByText("Fill", { selector: "strong" })).toBeInTheDocument();
    // Tier A is never offered Submit
    const taPick = within(row("Topco")).getByRole("combobox", { name: "Go as far as for Topco" });
    expect(within(taPick).queryByRole("option", { name: "Submit" })).not.toBeInTheDocument();
    // flagged posting: excluded, warning with the matched rule on hover/focus
    const flag = within(row("Flagco")).getByRole("img", { name: /Excluded/ });
    expect(flag).toHaveAttribute("tabindex", "0");
    expect(flag).toHaveAccessibleDescription(FLAG);

    await user.selectOptions(within(row("Plainco")).getByRole("combobox", { name: "Go as far as for Plainco" }), "submit");
    await waitFor(() =>
      expect(api.callsTo("POST /api/batches").at(-1)!.body).toMatchObject({ stops: { pl: "submit" }, dry_run: true }), opts);
    await waitFor(() => expect(within(row("Plainco")).getByText("Submit", { selector: "strong" })).toBeInTheDocument(), opts);

    await user.click(within(sheet).getByRole("button", { name: "Start" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/pipeline/batch/b-1"), opts);
    const create = api.callsTo("POST /api/batches").find((c) => !(c.body as { dry_run?: boolean }).dry_run)!.body;
    expect(create).toMatchObject({ job_ids: ["pl", "ta", "li", "lg", "fl"], stop_at: "fill", stops: { pl: "submit" } });
    expect(api.callsTo("POST /api/batches/b-1/start")).toHaveLength(1);
  });

  it("readiness cap links to Profile", async () => {
    notReady = true;
    setup("/jobs?sel=pl");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start pipeline" }, opts));
    const sheet = await screen.findByRole("region", { name: "Review pipeline" }, opts);
    expect(await within(sheet).findByText(/setup not finished/, {}, opts)).toBeInTheDocument();
    expect(within(sheet).getByRole("link", { name: "Finish your Profile" })).toHaveAttribute("href", "/profile");
  });
});
