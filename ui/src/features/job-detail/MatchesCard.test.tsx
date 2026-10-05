import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
import { InjectionCard } from "./InjectionCard";
import { MatchesCard } from "./MatchesCard";
import { renderWithProviders } from "./testUtils";

const row = (rid: string, name: string, score: number, missing: string[]) =>
  ({ rid, name, type: "variant", version: 1, score, missing, groups: {} });

afterEach(() => vi.unstubAllGlobals());

describe("MatchesCard (REQ-115)", () => {
  it("lists every résumé best first with the best marked, the threshold and missing skills", async () => {
    mockApi({
      "GET /api/jobs/nw01/matches": { job_id: "nw01", threshold: 70, scored: true, best: "be", hint: null,
        resumes: [row("be", "Backend", 82, []), row("fe", "Frontend", 55, ["Go", "Kafka"])] },
    });
    renderWithProviders(<MatchesCard jobId="nw01" />);
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getByRole("rowheader").textContent)).toEqual(["Backend Best", "Frontend "]);
    expect(rows[1]).toHaveTextContent("55 (below threshold)Go, Kafka");
    expect(screen.getByText("Threshold 70")).toBeInTheDocument();
  });

  it("shows the hint when the job is not scored yet", async () => {
    mockApi({
      "GET /api/jobs/nw01/matches": { job_id: "nw01", threshold: 70, scored: false, best: null, resumes: [],
        hint: "Run score first." },
    });
    renderWithProviders(<MatchesCard jobId="nw01" />);
    expect(await screen.findByText(/Not scored yet\. Run score first\./)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("InjectionCard (REQ-109)", () => {
  it("shows why the job was flagged and clears it on I checked it", async () => {
    const api = mockApi({ "POST /api/jobs/nw01/injection/clear": { job_id: "nw01", cleared: true } });
    renderWithProviders(<InjectionCard jobId="nw01" reasons="hidden text" />);
    expect(screen.getByText(/Flagged because: hidden text/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "I checked it" }));
    await vi.waitFor(() => expect(api.calls.some((c) => c.method === "POST" && c.path === "/api/jobs/nw01/injection/clear")).toBe(true));
  });
});
