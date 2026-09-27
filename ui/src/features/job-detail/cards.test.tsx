import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../../test/axe";
import { formatDateTime } from "../../lib/format";
import { ACTION_HELP } from "./actionHelp";
import { ACTIVITY_PREVIEW, ActivityCard } from "./ActivityCard";
import { ContactsCard } from "./ContactsCard";
import { detail } from "./fixtures";
import { ScoreCard } from "./ScoreCard";
import { renderWithProviders } from "./testUtils";

const d = detail();

describe("ScoreCard", () => {
  it("shows fit, tier, reasons, skills and hard filters, and no bars without sub-scores", async () => {
    const { container } = renderWithProviders(<ScoreCard score={d.score} />);
    const card = screen.getByRole("region", { name: "Score" });
    expect(within(card).getByText("91").parentElement).toHaveTextContent("Fit 91");
    expect(within(card).getByText("None failed")).toBeInTheDocument();
    const why = within(card).getByRole("list", { name: "Why this score" });
    expect(within(why).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Dream company.",
      "Skills: 2 of 3 required matched; missing Rust.",
    ]);
    expect(within(card).getByText("Kubernetes")).toHaveAttribute("data-tone", "green");
    expect(within(card).getByText("Rust")).toBeInTheDocument();
    expect(within(card).queryByRole("list", { name: "Sub-scores" })).not.toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("draws sub-score bars when score.json has them", () => {
    renderWithProviders(<ScoreCard score={{ ...d.score!, sub_scores: { skills_match: 94, location: 100 } }} />);
    const bars = screen.getByRole("list", { name: "Sub-scores" });
    expect(within(bars).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Skills match: 94",
      "Location: 100",
    ]);
  });

  it("lists failed hard filters and says when there is no score", () => {
    const { rerender } = renderWithProviders(<ScoreCard score={{ ...d.score!, hard_filter_fails: ["salary", "visa"] }} />);
    expect(screen.getByText("salary, visa")).toBeInTheDocument();
    rerender(<ScoreCard score={null} />);
  });
});

describe("ContactsCard", () => {
  it("badges people the candidate knows and marks them manual; others show their draft state", async () => {
    const { container } = renderWithProviders(
      <ContactsCard contacts={d.contacts} policy={d.contacts_policy!} outreach={d.outreach} />,
    );
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]!).getByText("4 mutuals")).toHaveAttribute("data-tone", "orange");
    expect(within(rows[0]!).getByText("Manual: tailor it")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("3rd")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Draft ready · you send")).toBeInTheDocument();
    expect(screen.getByText(/Outreach drafted for 2 contacts/)).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows Connected for first-degree contacts, and empty states", () => {
    const { rerender } = renderWithProviders(
      <ContactsCard
        contacts={[{ name: "Sam Park", linkedin_degree: 1 }]}
        policy={[{ name: "Sam Park", role: "", manual: true, reason: "LINKEDIN_CONNECTED", detail: "" }]}
        outreach={null}
      />,
    );
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("No outreach drafted yet.")).toBeInTheDocument();
    rerender(<ContactsCard contacts={[]} policy={[]} outreach={null} />);
  });
});

describe("ActivityCard", () => {
  it("shows the plain-English label of the newest entries, the raw line as a tooltip, and the status history", async () => {
    const { container } = renderWithProviders(<ActivityCard activity={d.activity!} history={d.history} />);
    const card = screen.getByRole("region", { name: "Activity" });
    const recent = within(card).getByRole("list", { name: "Recent activity" });
    const rows = within(recent).getAllByRole("listitem");
    expect(rows).toHaveLength(ACTIVITY_PREVIEW);
    expect(rows[0]).toHaveTextContent("Status changed to needs review: prepare-job: Tier A");
    expect(rows[0]).toHaveAttribute("title", "[store] status -> needs_review: prepare-job: Tier A");
    expect(within(card).getByText("Found by scout on greenhouse")).not.toBeVisible();
    expect(within(card).getAllByText(formatDateTime("2026-09-24T18:04:00")!).length).toBeGreaterThan(0);
    expect(within(card).getByRole("heading", { name: "Status history" })).toBeInTheDocument();
    expect(within(card).getByText("prepare-job: Tier A")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("Show all (N) expands the older entries; no toggle when everything fits", async () => {
    const { rerender } = renderWithProviders(<ActivityCard activity={d.activity!} history={[]} />);
    const toggle = screen.getByText(`Show all (${d.activity!.length})`);
    expect(toggle.closest("details")).not.toHaveAttribute("open");
    await userEvent.setup().click(toggle);
    expect(toggle.closest("details")).toHaveAttribute("open");
    expect(screen.getByText("Found by scout on greenhouse")).toBeVisible();
    rerender(<ActivityCard activity={d.activity!.slice(0, ACTIVITY_PREVIEW)} history={[]} />);
    expect(screen.queryByText(/^Show all/)).not.toBeInTheDocument();
  });

  it("falls back to the raw message when a label is missing", () => {
    renderWithProviders(<ActivityCard activity={[{ at: "2026-09-24T18:04:00", component: "x", message: "odd line", label: "" }]} history={[]} />);
    expect(screen.getByText("odd line")).toBeInTheDocument();
  });

  it("empty states", () => {
    renderWithProviders(<ActivityCard activity={[]} history={[]} />);
    expect(screen.getByText("No activity logged yet.")).toBeInTheDocument();
    expect(screen.getByText("No status changes yet.")).toBeInTheDocument();
  });
});

describe("action help", () => {
  it("every entry is one plain sentence", () => {
    for (const text of Object.values(ACTION_HELP)) {
      expect(text).toMatch(/^[A-Z].*\.$/);
      expect(text).not.toMatch(/\.\s+[A-Z]/);
    }
  });
});
