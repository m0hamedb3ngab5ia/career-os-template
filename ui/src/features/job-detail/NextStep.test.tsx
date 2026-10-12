import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ActionItem } from "../today/types";
import { NextStepSummary, ReasonDetails, stateSentence } from "./NextStep";
import { renderWithProviders } from "./testUtils";
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
    expect(stateSentence({ ...base, review_reasons: reasons }, 3)).toBe("Needs your review: 3 things need attention.");
    expect(stateSentence({ ...base, review_reasons: reasons.slice(0, 1) })).toBe("Needs your review: 1 thing needs attention.");
    expect(stateSentence({ ...base, next_action: null })).toBe("Nothing left to run for this job.");
    expect(stateSentence(base)).toBe("Ready for the next step: Continue pipeline.");
  });
});

describe("NextStepSummary", () => {
  it("states the count and links this job's tasks; QA warnings sit behind a click; no codes", () => {
    renderWithProviders(<NextStepSummary state={{ ...base, review_reasons: reasons }} tasks={[task]} />);
    expect(screen.getByText("Needs your review: 1 thing needs attention.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "1 task" })).toHaveAttribute("href", "/actions");
    expect(screen.getByText("1 QA warning")).toBeInTheDocument();
    expect(screen.queryByText(/qa_warning/)).not.toBeInTheDocument();
  });

  it("without tasks, review-action reasons do not count and the job is ready", () => {
    renderWithProviders(<NextStepSummary state={{ ...base, review_reasons: reasons }} tasks={[]} />);
    expect(screen.getByText("Ready for the next step: Continue pipeline.")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
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
