import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../../test/axe";
import { ACTION_HELP } from "./actionHelp";
import { ContactsCard } from "./ContactsCard";
import { detail } from "./fixtures";
import { ScoreCard } from "./ScoreCard";
import { renderWithProviders } from "./testUtils";

const d = detail();

describe("ScoreCard", () => {
  it("shows fit, tier, reasons, skills and hard filters, and no bars without sub-scores", async () => {
    const { container } = renderWithProviders(<ScoreCard jobId="j1" score={d.score} />);
    const card = screen.getByRole("region", { name: "Fit" });
    expect(within(card).getByText("91").parentElement).toHaveTextContent("Fit 91");
    expect(within(card).getByText("None failed")).toBeInTheDocument();
    const why = within(card).getByRole("list", { name: "Why this score" });
    expect(within(why).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Dream company.",
      "Skills: 2 of 3 required matched; missing Rust.",
    ]);
    expect(within(card).queryByRole("list", { name: "Sub-scores" })).not.toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("draws sub-score bars when score.json has them", () => {
    renderWithProviders(<ScoreCard jobId="j1" score={{ ...d.score!, sub_scores: { skills_match: 94, location: 100 } }} />);
    const bars = screen.getByRole("list", { name: "Sub-scores" });
    expect(within(bars).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Skills match: 94",
      "Location: 100",
    ]);
  });

  it("lists failed hard filters and says when there is no score", () => {
    const { unmount } = renderWithProviders(<ScoreCard jobId="j1" score={{ ...d.score!, hard_filter_fails: ["salary", "visa"] }} />);
    expect(screen.getByText("salary, visa")).toBeInTheDocument();
    unmount();
    renderWithProviders(<ScoreCard jobId="j1" score={null} />);
    expect(screen.getByText(/Not scored yet/)).toBeInTheDocument();
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

describe("action help", () => {
  it("every entry is one plain sentence", () => {
    for (const text of Object.values(ACTION_HELP)) {
      expect(text).toMatch(/^[A-Z].*\.$/);
      expect(text).not.toMatch(/\.\s+[A-Z]/);
    }
  });
});
