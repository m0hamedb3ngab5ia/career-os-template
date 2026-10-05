import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
import { renderWithProviders } from "../job-detail/testUtils";
import { CheckJobDialog } from "./CheckJobDialog";

const row = (rid: string, name: string, score: number, missing: string[]) => ({
  rid, name, type: "variant", version: 1, score, missing,
  groups: { required: { hit: ["Python"], missing }, preferred: { hit: [], missing: ["Rust"] }, title: { hit: [], missing: [] } },
});

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

  it("shows the server's refusal inline (no text in file)", async () => {
    mockApi({ "POST /api/jobs/check": { status: 422, body: { detail: "jd.txt: no text found" } } });
    const { user } = open();
    await user.upload(screen.getByLabelText(/Or upload a file/), new File([" "], "jd.txt", { type: "text/plain" }));
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("jd.txt: no text found");
  });

  it("E2E-010-01: pasted JD → fit score + match table, best marked; Prepare application starts the prepare run", async () => {
    const api = mockApi({
      "POST /api/jobs/check": { status: 201, body: CREATED },
      "GET /api/jobs/m01/check": state("ready"),
      "POST /api/jobs/m01/check/tailor": { run_id: "r2", kind: "prepare" },
      "GET /api/jobs/m01": { job: { job_id: "m01" }, score: { fit: 82 } },
    });
    const { user, onClose } = open();
    await user.type(screen.getByLabelText("Job description"), "Backend engineer, Python");
    await user.type(screen.getByLabelText("Company (optional)"), "Acme");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("rowheader")[0]).toHaveTextContent("Backend Best");
    expect(await screen.findByRole("progressbar", { name: "Fit score" })).toHaveAttribute("aria-valuenow", "82");
    const post = api.calls.find((c) => c.method === "POST" && c.path === "/api/jobs/check")!;
    expect(post.body).toBe("Backend engineer, Python");
    expect(post.search.get("company")).toBe("Acme");
    expect(post.search.get("filename")).toBeNull();
    for (const gone of ["Done", "Tailor from master", "Keep job, no résumé"])
      expect(screen.queryByRole("button", { name: gone })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Prepare application" }));
    await vi.waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(api.callsTo("POST /api/jobs/m01/check/tailor")).toHaveLength(1);
  });

  it("Cancel keeps the job unticked: no run, no select", async () => {
    const api = mockApi({ "POST /api/jobs/check": { status: 201, body: CREATED }, "GET /api/jobs/m01/check": state("offer_tailor") });
    const { user, onClose } = open();
    await user.type(screen.getByLabelText("Job description"), "jd");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(await screen.findByRole("button", { name: "Prepare application" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
    expect(api.calls.filter((c) => c.method === "POST")).toHaveLength(1);
  });

  it("Why this score: per-résumé matched ✓ and missing, required vs preferred", async () => {
    mockApi({ "POST /api/jobs/check": { status: 201, body: CREATED }, "GET /api/jobs/m01/check": state("ready") });
    const { user } = open();
    await user.type(screen.getByLabelText("Job description"), "jd");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    const why = (await screen.findAllByText("Why this score"))[1]!;
    await user.click(why);
    const box = why.closest("details")!;
    expect(box).toHaveAttribute("open");
    expect(box).toHaveTextContent("Required: ✓ Python · missing Go");
    expect(box).toHaveTextContent("Preferred: missing Rust");
  });

  it("flagged job: says prepare waits for the flag to be cleared on the job page", async () => {
    mockApi({
      "POST /api/jobs/check": { status: 201, body: { ...CREATED, flagged: true, reasons: ["hidden text"] } },
      "GET /api/jobs/m01/check": state("ready"),
    });
    const { user } = open();
    await user.type(screen.getByLabelText("Job description"), "jd");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(await screen.findByRole("button", { name: "Prepare application" })).toBeInTheDocument();
    expect(screen.getByText(/Mark it checked on the job page before preparing it/)).toBeInTheDocument();
  });

  it("score_error: shows why, stops polling, no stuck 'Scoring…'", async () => {
    const api = mockApi({
      "POST /api/jobs/check": { status: 201, body: { ...CREATED, score_run: null, score_error: "another run is active" } },
      "GET /api/jobs/m01/check": state("scoring"),
    });
    const { user } = open();
    await user.type(screen.getByLabelText("Job description"), "jd");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(await screen.findByText(/Scoring could not start: another run is active/)).toBeInTheDocument();
    await vi.waitFor(() => expect(api.callsTo("GET /api/jobs/m01/check")).toHaveLength(1));
    expect(screen.queryByText(/^Scoring…/)).toBeNull();
    expect(screen.getByRole("link", { name: "Open job" })).toBeInTheDocument();
  });

  it("cannot be closed while the check is being sent; Cancel is disabled", async () => {
    let release!: () => void;
    mockApi({
      "POST /api/jobs/check": () => new Promise((r) => (release = () => r({ status: 201, body: CREATED }))),
      "GET /api/jobs/m01/check": state("ready"),
    });
    const { user, onClose } = open();
    await user.type(screen.getByLabelText("Job description"), "jd");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
    release();
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("not_tailorable: notice plus Cancel, no prepare", async () => {
    mockApi({
      "POST /api/jobs/check": { status: 201, body: CREATED },
      "GET /api/jobs/m01/check": state("not_tailorable", { notice: "No master résumé to tailor from." }),
    });
    const { user, onClose } = open();
    await user.type(screen.getByLabelText("Job description"), "jd");
    await user.click(screen.getByRole("button", { name: "Check job" }));
    expect(await screen.findByText("No master résumé to tailor from.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare application" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("file input points at the error message", async () => {
    mockApi({});
    const { user } = open();
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "jd.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/Or upload a file/), big);
    await user.click(screen.getByRole("button", { name: "Check job" }));
    const err = screen.getByRole("alert");
    expect(screen.getByLabelText(/Or upload a file/)).toHaveAttribute("aria-describedby", err.id);
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
    expect(screen.getByText(/^Scoring…/)).toBeInTheDocument();
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
    await user.click(await screen.findByRole("button", { name: "Prepare application" }));
    expect(await screen.findByText(notice)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create closest match" }));
    expect(await screen.findByText(/Kept, flagged below threshold/)).toBeInTheDocument();
    expect(api.calls.find((c) => c.path.endsWith("/check/decision"))?.body).toEqual({ keep: true });
  });
});
