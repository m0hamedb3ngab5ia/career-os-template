import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ActionItem } from "../today/types";
import { NextStepSummary, ReasonDetails, stateSentence } from "./NextStep";
import type { PipelineState } from "./types";

const base: PipelineState = {
  stage: "prepare",
  next_action: "continue",
  next_label: "Continue pipeline",
  next_kind: "prepare",
  force: false,
  blocked_reason: null,
  note: null,
  auto_submit: false,
  review_reasons: [],
  active_run_id: null,
  queued_in_run: null,
  failures: null,
};
const reasons: PipelineState["review_reasons"] = [
  { code: "qa_warning", text: "A document check left a warning", detail: "long letter" },
  { code: "action_review", text: "Review and submit the application", detail: null },
];
const task = { id: "t1", what: "Answer 4 application questions", type: "question", job_id: "j1" } as ActionItem;

describe("stateSentence", () => {
  it("names the one state, most urgent first", () => {
    expect(stateSentence({ ...base, active_run_id: "r1", review_reasons: reasons })).toMatch(/^Working on it/);
    expect(stateSentence({ ...base, blocked_reason: "Tier C is skipped" })).toBe("Tier C is skipped");
    expect(stateSentence({ ...base, review_reasons: reasons }, 1)).toBe("Needs your review: 3 things need attention.");
    expect(stateSentence({ ...base, review_reasons: reasons.slice(0, 1) })).toBe("Needs your review: 1 thing needs attention.");
    expect(stateSentence({ ...base, next_action: null })).toBe("Nothing left to run for this job.");
    expect(stateSentence(base)).toBe("Ready for the next step: Continue pipeline.");
  });
});

describe("NextStepSummary", () => {
  it("lists review reasons and this job's tasks in words, without codes or details", () => {
    render(<NextStepSummary state={{ ...base, review_reasons: reasons }} tasks={[task]} />);
    expect(screen.getByText("Needs your review: 3 things need attention.")).toBeInTheDocument();
    const items = within(screen.getByRole("list", { name: "Needs you" })).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      "A document check left a warning",
      "Review and submit the application",
      "Answer 4 application questions",
    ]);
    expect(screen.queryByText(/qa_warning/)).not.toBeInTheDocument();
    expect(screen.queryByText(/long letter/)).not.toBeInTheDocument();
  });

  it("lists an item once when a review reason and a task say the same thing", () => {
    const dup = { ...task, what: "Review and submit the application" } as ActionItem;
    render(<NextStepSummary state={{ ...base, review_reasons: reasons }} tasks={[dup]} />);
    const items = within(screen.getByRole("list", { name: "Needs you" })).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual(["A document check left a warning", "Review and submit the application"]);
  });

  it("shows no list when nothing needs you", () => {
    render(<NextStepSummary state={base} tasks={[]} />);
    expect(screen.queryByRole("list", { name: "Needs you" })).not.toBeInTheDocument();
  });
});

describe("ReasonDetails", () => {
  it("shows code, text and detail; nothing when there are no reasons", () => {
    const { rerender } = render(<ReasonDetails reasons={reasons} />);
    const items = within(screen.getByRole("list", { name: "Review reasons" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("qa_warning: A document check left a warning (long letter)");
    expect(items[1]).toHaveTextContent("action_review: Review and submit the application");
    rerender(<ReasonDetails reasons={[]} />);
    expect(screen.queryByRole("list", { name: "Review reasons" })).not.toBeInTheDocument();
  });
});
