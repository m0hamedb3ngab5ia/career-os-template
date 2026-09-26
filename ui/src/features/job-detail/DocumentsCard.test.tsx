import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
import { axeViolations } from "../../test/axe";
import { formatDecimal } from "../../lib/format";
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
    <DocumentsCard jobId="nw01" documents={d.documents} submitted={d.submitted} qa={d.qa} {...over} />,
  );
  return { api, ...utils };
}

describe("DocumentsCard", () => {
  it("lists known documents first, each opening the file in a new tab", () => {
    renderCard();
    const card = screen.getByRole("region", { name: "Documents" });
    const links = within(card).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/api/jobs/nw01/files/resume.pdf",
      "/api/jobs/nw01/files/cover_letter.md",
      "/api/jobs/nw01/files/notes.txt",
    ]);
    expect(links[0]).toHaveAccessibleName("View résumé (resume.pdf, opens in a new tab)");
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
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
    expect(screen.getByText("Specificity")).toBeInTheDocument();
    expect(screen.getByText("Truthfulness")).toBeInTheDocument();
    expect(screen.getByText(formatDecimal(9.5))).toBeInTheDocument();
  });

  it("Re-run QA posts, reads Running… and announces the pass/fail summary", async () => {
    let resolve!: () => void;
    const gate = new Promise<void>((r) => (resolve = r));
    const { api } = renderCard({}, {
      "POST /api/jobs/nw01/qa": async () => {
        await gate;
        return { pass: false, summary: { hard_fail: 1, soft_fail: 2 }, fail_reasons: ["Résumé over one page"] };
      },
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Re-run QA" }));
    expect(await screen.findByRole("button", { name: "Running…" })).toBeDisabled();
    resolve();
    const status = await screen.findByText("QA failed");
    expect(status.closest("[role=status]")).not.toBeNull();
    expect(screen.getByText(/1 hard fails, 2 soft fails/)).toBeInTheDocument();
    expect(screen.getByText("Résumé over one page")).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/nw01/qa")[0]!.headers["x-careeros"]).toBe("1");
  });

  it("Open folder posts", async () => {
    const { api } = renderCard();
    await userEvent.setup().click(screen.getByRole("button", { name: "Open folder" }));
    expect(await screen.findByText("Opened the job folder")).toBeInTheDocument();
    expect(api.callsTo("POST /api/jobs/nw01/open-folder")).toHaveLength(1);
  });

  it("empty: no documents, not reviewed", () => {
    renderCard({ documents: [], qa: null });
    expect(screen.getByText(/No documents yet/)).toBeInTheDocument();
    expect(screen.getByText("Not reviewed")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = renderCard();
    expect(await axeViolations(container)).toEqual([]);
  });
});
