import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
import { axeViolations } from "../../test/axe";
import { formatDecimal } from "../../lib/format";
import { ACTION_HELP } from "./actionHelp";
import { DocumentsCard } from "./DocumentsCard";
import { detail } from "./fixtures";
import { renderWithProviders } from "./testUtils";

const d = detail();
afterEach(() => vi.unstubAllGlobals());

function renderCard(over: Partial<Parameters<typeof DocumentsCard>[0]> = {}, routes = {}) {
  const api = mockApi({
    "POST /api/jobs/nw01/qa": { pass: false, summary: { hard_fail: 1, soft_fail: 2 }, fail_reasons: ["Résumé over one page"] },
    "POST /api/jobs/nw01/open-folder": { opened: true },
    ...routes,
  });
  const utils = renderWithProviders(
    <DocumentsCard jobId="nw01" documents={d.documents} otherFiles={d.other_files} submitted={d.submitted} qa={d.qa} {...over} />,
  );
  return { api, ...utils };
}

describe("DocumentsCard", () => {
  it("shows the key documents in the server's order, each opening the file in a new tab", () => {
    renderCard();
    const card = screen.getByRole("region", { name: "Documents" });
    const links = within(card).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/api/jobs/nw01/files/resume.pdf",
      "/api/jobs/nw01/files/cover_letter.pdf",
      "/api/jobs/nw01/files/cover_letter.md",
      "/api/jobs/nw01/files/notes.txt",
      "/api/jobs/nw01/files/resume.json",
    ]);
    expect(links[0]).toHaveAccessibleName("View résumé (resume.pdf, opens in a new tab)");
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("shows each document as a closed title that expands to its details", async () => {
    renderCard();
    const title = screen.getByText("Résumé");
    expect(title.closest("details")).not.toHaveAttribute("open");
    expect(screen.getAllByText("resume.pdf")[0]!).not.toBeVisible();
    await userEvent.setup().click(title);
    expect(screen.getAllByText("resume.pdf")[0]!).toBeVisible();
  });

  it("folds every other file under a closed All files (N) toggle, sorted by name", async () => {
    renderCard();
    const toggle = screen.getByText("All files (3)");
    expect(toggle.closest("details")).not.toHaveAttribute("open");
    await userEvent.setup().click(toggle);
    const list = screen.getByRole("list", { name: "All files" });
    expect(within(list).getAllByRole("link").map((a) => a.textContent)).toEqual([
      "cover_letter.md (opens in a new tab)",
      "notes.txt (opens in a new tab)",
      "resume.json (opens in a new tab)",
    ]);
  });

  it("action buttons carry one-sentence help as their title", () => {
    renderCard();
    expect(screen.getByRole("button", { name: "Re-run QA" })).toHaveAttribute("title", ACTION_HELP.rerunQa);
    expect(screen.getByRole("button", { name: "Open folder" })).toHaveAttribute("title", ACTION_HELP.openFolder);
  });

  it("submitted copy is disabled with a reason until there is one", () => {
    renderCard();
    const btn = screen.getByRole("button", { name: "View submitted copy" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAccessibleDescription(/Available after you submit/);
  });

  it("shows the QA verdict, mean vs threshold and the rubric scores", () => {
    renderCard();
    expect(screen.getByText("Passed")).toHaveAttribute("data-tone", "green");
    expect(screen.getByText(`${formatDecimal(8.6)} of ${formatDecimal(7.5)} needed · next: queue`)).toBeInTheDocument();
    // scores and counts sit in a collapsed Details; the verdict stays in view
    expect(screen.getByText(`${formatDecimal(8.6)} of ${formatDecimal(7.5)} needed · next: queue`).closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("Specificity")).toBeInTheDocument();
    expect(screen.getByText("Truthfulness")).toBeInTheDocument();
    expect(screen.getByText(formatDecimal(9.5))).toBeInTheDocument();
  });

  it("Re-run QA starts a QA run and announces its pass/fail summary", async () => {
    const { api } = renderCard({}, {
      "POST /api/runs/steps/qa": { kind: "qa", started: true, run_id: "r-qa-1" },
      "GET /api/runs/r-qa-1": {
        id: "r-qa-1", kind: "qa", trigger: "manual", status: "done", state: "done", stop_reason: "completed",
        started_at: null, ended_at: null, attempts: [], log: "",
        result: { pass: false, summary: { hard_fail: 1, soft_fail: 2 }, fail_reasons: ["Résumé over one page"] },
      },
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Re-run QA" }));
    const status = await screen.findByText("QA failed");
    expect(status.closest("[role=status]")).not.toBeNull();
    expect(screen.getByText(/1 hard fails, 2 soft fails/)).toBeInTheDocument();
    expect(api.callsTo("POST /api/runs/steps/qa")[0]!.headers["x-careeros"]).toBe("1");
  });

  it("Stop cancels a running QA and returns to Re-run QA with no result", async () => {
    const { api } = renderCard({}, {
      "POST /api/runs/steps/qa": { kind: "qa", started: true, run_id: "r-qa-2" },
      "GET /api/runs/r-qa-2": {
        id: "r-qa-2", kind: "qa", trigger: "manual", status: "running", state: "running", stop_reason: null,
        started_at: null, ended_at: null, attempts: [], log: "",
      },
      "POST /api/runs/cancel": { status: "cancelling", run_id: "r-qa-2" },
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Re-run QA" }));
    await user.click(await screen.findByRole("button", { name: "Stop" }));
    expect(await screen.findByRole("button", { name: "Re-run QA" })).toBeEnabled();
    expect(screen.queryByText(/QA failed|QA passed/)).toBeNull();
    expect(api.callsTo("POST /api/runs/cancel")).toHaveLength(1);
  });


  it("Open folder posts", async () => {
    const { api } = renderCard();
    await userEvent.setup().click(screen.getByRole("button", { name: "Open folder" }));
    expect(await screen.findByText("Opened the job folder")).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/nw01/open-folder")).toHaveLength(1);
  });

  it("empty: no documents, not reviewed", () => {
    renderCard({ documents: [], otherFiles: [], qa: null });
    expect(screen.queryByText(/^All files/)).not.toBeInTheDocument();
    expect(screen.getByText(/No documents yet/)).toBeInTheDocument();
    expect(screen.getByText("Not reviewed")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = renderCard();
    expect(await axeViolations(container)).toEqual([]);
  });
});
