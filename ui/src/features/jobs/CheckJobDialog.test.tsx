import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
import { renderWithProviders } from "../job-detail/testUtils";
import { CheckJobDialog } from "./CheckJobDialog";

const row = (rid: string, name: string, score: number, missing: string[]) =>
  ({ rid, name, type: "variant", version: 1, score, missing, groups: {} });

const CREATED = { job_id: "m01", flagged: false, reasons: [], score_run: "r1", score_error: null };
const state = (stage: string, extra: Record<string, unknown> = {}) => ({
  job_id: "m01", threshold: 70, scored: stage !== "scoring", best: "be", hint: null, tailor_run: null,
  decision: null, attempt: null, notice: null, stage,
  resumes: [row("be", "Backend", 82, []), row("fe", "Frontend", 55, ["Go"])], ...extra,
});

function open() {
  const onClose = vi.fn();
  renderWithProviders(<CheckJobDialog open onClose={onClose} />);
  return { user: userEvent.setup(), onClose };
}

afterEach(() => vi.unstubAllGlobals());

describe("CheckJobDialog (REQ-114, UC-010)", () => {
  it("asks for text or a file before sending anything", async () => {
    const api = mockApi({});
    const { user } = open();
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Paste the job description or choose a file.");
    expect(api.calls).toHaveLength(0);
  });

  it("rejects a file over 5 MB inline", async () => {
    const api = mockApi({});
    const { user } = open();
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "jd.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/Or upload a file/), big);
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(screen.getByRole("alert")).toHaveTextContent("jd.pdf is larger than 5 MB.");
    expect(api.calls).toHaveLength(0);
  });

  it("shows the server's refusal inline (bad type)", async () => {
    mockApi({ "POST /api/jobs/check": { status: 415, body: { detail: "jd.png: use pdf, docx, txt or md" } } });
    const { user } = open();
    await user.upload(screen.getByLabelText(/Or upload a file/), new File(["x"], "jd.png"));
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("jd.png: use pdf, docx, txt or md");
  });

  it("E2E-010-01: pasted JD → match table, best marked, no tailor; Use this résumé ticks the job", async () => {
    const api = mockApi({
      "POST /api/jobs/check": { status: 201, body: CREATED },
      "GET /api/jobs/m01/check": state("ready"),
      "POST /api/jobs/select": { ids: ["m01"], selected: true },
    });
    const { user, onClose } = open();
    await user.type(screen.getByLabelText("Job description"), "Backend engineer, Python");
    await user.type(screen.getByLabelText("Company (optional)"), "Acme");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("rowheader")[0]).toHaveTextContent("Backend Best");
    const post = api.calls.find((c) => c.method === "POST" && c.path === "/api/jobs/check")!;
    expect(post.body).toBe("Backend engineer, Python");
    expect(post.search.get("company")).toBe("Acme");
    expect(post.search.get("filename")).toBeNull();
    expect(screen.queryByRole("button", { name: "Tailor from master" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Use this résumé" }));
    await vi.waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.calls.find((c) => c.path === "/api/jobs/select")?.body).toEqual({ ids: ["m01"], selected: true });
    expect(api.calls.some((c) => c.path.endsWith("/check/tailor"))).toBe(false);
  });

  it("shows the injection flag with its reasons; scoring continues", async () => {
    mockApi({
      "POST /api/jobs/check": { status: 201, body: { ...CREATED, flagged: true, reasons: ["hidden text"] } },
      "GET /api/jobs/m01/check": state("scoring"),
    });
    const { user } = open();
    await user.type(screen.getByLabelText("Job description"), "jd");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(await screen.findByText(/Possible prompt injection: hidden text/)).toBeInTheDocument();
    expect(screen.getByText(/Scoring/)).toBeInTheDocument();
  });

  it("E2E-010-02: below threshold → one tailor run → notice → Create closest match keeps it", async () => {
    let stage = "offer_tailor";
    const notice = "threshold not met: best 64, needed 70 (64/70); missing: Go. Create closest match anyway?";
    const api = mockApi({
      "POST /api/jobs/check": { status: 201, body: CREATED },
      "GET /api/jobs/m01/check": () => state(stage, stage === "confirm" ? { notice, attempt: { score: 64, missing: ["Go"] } } : {}),
      "POST /api/jobs/m01/check/tailor": () => ((stage = "confirm"), { run_id: "r2", kind: "prepare" }),
      "POST /api/jobs/m01/check/decision": () => state("below_threshold", { decision: "keep" }),
    });
    const { user } = open();
    await user.type(screen.getByLabelText("Job description"), "jd");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    await user.click(await screen.findByRole("button", { name: "Tailor from master" }));
    expect(await screen.findByText(notice)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create closest match" }));
    expect(await screen.findByText(/Kept, flagged below threshold/)).toBeInTheDocument();
    expect(api.calls.find((c) => c.path.endsWith("/check/decision"))?.body).toEqual({ keep: true });
  });
});
